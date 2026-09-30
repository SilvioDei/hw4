"""Campus Customs shop agent: PydanticAI wired to OpenAI through Portkey, plus a reply fact-checker."""

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput, RunContext, capture_run_messages
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage, UsageLimits

from models import (
    AgentReply,
    ChatTurn,
    CurrentProduct,
    CustomerContext,
    FactCheck,
    PageSearch,
    PageSearchSummary,
    ProductDetails,
    ProductNotFound,
    ProductSearchResult,
    ShopDeps,
    StockCheck,
)
from tools import AGENT_TOOLS, load_product

log = logging.getLogger("campus_customs")

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR.parent / ".env")  # hw4/.env

# The one setting to change for a different model (5.6 or 6 series).
MODEL_NAME = "gpt-5.6-luna"

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PROMPT_PATH = BACKEND_DIR / "prompts" / "prompt.md"
# Hard per-chat-message limits, enforced by PydanticAI (UsageLimitExceeded when hit).
# The fact-check retry shares the same RunUsage, so these cover the whole message.
MAX_MODEL_REQUESTS = 8
MAX_TOOL_CALLS = 8
MAX_TOTAL_TOKENS = 60_000
USAGE_LIMITS = UsageLimits(
    request_limit=MAX_MODEL_REQUESTS,
    tool_calls_limit=MAX_TOOL_CALLS,
    total_tokens_limit=MAX_TOTAL_TOKENS,
)
FACT_CHECK_RETRIES = 1  # correction rounds before a reply is replaced
MAX_HISTORY = 20  # earlier turns sent to the model


def _build_model() -> OpenAIChatModel:
    key = os.getenv("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Add it to hw4/.env (copy .env.example).")
    client = AsyncOpenAI(
        api_key=key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": key},
        max_retries=2,
        timeout=60,
    )
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


shop_agent = Agent(
    _build_model(),
    deps_type=ShopDeps,
    # Native structured output: tool-based final answers hung on the Portkey gateway in HW 3.
    output_type=NativeOutput(AgentReply),
    instructions=PROMPT_PATH.read_text(encoding="utf-8"),
    tools=AGENT_TOOLS,
)


@shop_agent.instructions
def who_and_where(ctx: RunContext[ShopDeps]) -> str:
    """Per-message context: who is chatting and which product page they're on."""
    c = ctx.deps.customer
    who = (
        f"You are chatting with a logged-in customer: {c.first_name} {c.last_name} ({c.email})."
        if c
        else "You are chatting with a guest (not logged in)."
    )
    p = ctx.deps.current_product
    where = (
        f"The shopper is viewing the product page for \"{p.name}\" (product_id: {p.product_id}). "
        "If they say \"this\", \"it\", or \"this one\", they mean this product, not the cards in the "
        "results strip. Still look up its details and stock with the tools before answering."
        if p
        else "The shopper is not on a product page."
    )
    return f"{who}\n{where}"


def _history(turns: list[ChatTurn]) -> list[ModelMessage]:
    """Turn earlier chat turns (from the DB or the website) into PydanticAI message history."""
    messages: list[ModelMessage] = []
    turns = turns[-MAX_HISTORY:]
    while turns and turns[0].role == "assistant":  # e.g. the widget's greeting
        turns = turns[1:]
    for t in turns:
        if t.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=t.content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=t.content)]))
    return messages


# ---------------------------------------------------------------- fact check
# After the agent drafts a reply, every "$NN.NN" and every stock count ("15 in stock",
# "only 2 left") is compared with the DB for the products this turn touched. A mismatch
# gets one automatic correction round; if it's still wrong, the reply is replaced.

PRICE_RE = re.compile(r"\$\s?(\d{1,4}(?:\.\d{1,2})?)")
# "$60" after these words is a budget/threshold, not a claimed product price
THRESHOLD_RE = re.compile(r"(under|below|less than|up to|within|over|above|budget of|around)\s*$", re.I)
STOCK_RE = re.compile(
    r"\b(?:only\s+)?(\d{1,4})\s+(?:(?:units?|pieces?)\s+)?(?:left|in stock|available|remaining)\b"
    r"|\bonly\s+(\d{1,4})\b",
    re.I,
)
UNVERIFIED_REPLY = (
    "Sorry, I couldn't double-check those numbers just now. Please open the product page "
    "for the current price and stock, or ask me again."
)


def _product_ids_in(obj: object, found: set[str]) -> None:
    """Collect every product_id mentioned anywhere in a tool result."""
    if isinstance(obj, BaseModel):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        if isinstance(obj.get("product_id"), str):
            found.add(obj["product_id"])
        for v in obj.values():
            _product_ids_in(v, found)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _product_ids_in(v, found)


def _turn_context(messages: list[ModelMessage], deps: ShopDeps) -> tuple[set[str], set[float]]:
    """Products this turn looked at, plus any max_price the agent searched with."""
    ids: set[str] = set()
    thresholds: set[float] = set()
    for m in messages:
        for part in m.parts:
            if isinstance(part, ToolReturnPart):
                _product_ids_in(part.content, ids)
            elif isinstance(part, ToolCallPart):
                mp = part.args_as_dict().get("max_price")
                if isinstance(mp, (int, float)):
                    thresholds.add(round(float(mp), 2))
    if deps.current_product:
        ids.add(deps.current_product.product_id)
    if deps.page_search:
        ids.update(deps.page_search.product_ids)
    return ids, thresholds


def fact_check(reply: str, user_text: str, messages: list[ModelMessage], deps: ShopDeps) -> FactCheck:
    """Compare each price and stock number in `reply` with the DB. Pure read-only check."""
    ids, thresholds = _turn_context(messages, deps)
    valid_prices, valid_stock = set(thresholds), set()
    for pid in ids:
        product = load_product(pid)
        if product:
            valid_prices.add(round(product["price"], 2))
            valid_stock.update(s["quantity"] for s in product["inventory"])
            valid_stock.add(product["total_stock"])
    # numbers the shopper typed themselves (e.g. "under $60") are fine to repeat
    valid_prices.update(round(float(x), 2) for x in PRICE_RE.findall(user_text))
    valid_stock.update(int(x) for x in re.findall(r"\b\d{1,4}\b", user_text))

    issues: list[str] = []
    prices = [
        m for m in PRICE_RE.finditer(reply) if not THRESHOLD_RE.search(reply[max(0, m.start() - 15): m.start()])
    ]
    for m in prices:
        value = round(float(m.group(1)), 2)
        if value not in valid_prices:
            issues.append(f"price ${value:.2f} is not the database price of any product discussed")
    stock = [int(a or b) for a, b in STOCK_RE.findall(reply)]
    for n in dict.fromkeys(stock):
        if n not in valid_stock:
            issues.append(f"stock count {n} does not match the database")

    if not prices and not stock:
        status = "no_facts"
    else:
        status = "unverified" if issues else "verified"
    return FactCheck(status=status, prices_checked=len(prices), stock_checked=len(stock), issues=issues)


# ---------------------------------------------------------------- audit trail
# output/audit_trail.json is a JSON array that only ever grows: each chat message
# appends one entry. It goes to a public repo, so it never holds message text,
# names, emails, passwords, hashes, or keys: only "logged-in user"/"guest",
# tool names, short scrubbed args/results, counts, and the stop reason.

AUDIT_PATH = BACKEND_DIR.parent / "output" / "audit_trail.json"
AUDIT_TEXT_CAP = 80  # max characters for any logged arg/result
_audit_lock = threading.Lock()
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _clip(value: object) -> str:
    text = EMAIL_RE.sub("[email]", str(value)).replace("\n", " ")
    return text if len(text) <= AUDIT_TEXT_CAP else text[: AUDIT_TEXT_CAP - 1] + "…"


def _summarize(content: object) -> str:
    """A short, non-personal summary of a tool result."""
    if isinstance(content, ProductSearchResult):
        extra = f"; unmatched {content.unmatched_terms}" if content.unmatched_terms else ""
        return _clip(f"{content.match_count} matches{extra}")
    if isinstance(content, PageSearchSummary):
        return _clip(f"{content.shown_on_page} cards on page ({content.total_matches} matches)")
    if isinstance(content, ProductDetails):
        return _clip(f"{content.product_id} ${content.price:.2f}; sold out {content.sold_out_sizes or 'none'}")
    if isinstance(content, StockCheck):
        return _clip(f"{content.product_id}: {content.message}")
    if isinstance(content, ProductNotFound):
        return "not found"
    return _clip(content)


def _steps(messages: list[ModelMessage]) -> list[dict]:
    """Tool calls in this run, each paired with a short summary of its result."""
    results = {
        p.tool_call_id: p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)
    }
    steps = []
    for m in messages:
        for p in m.parts:
            if isinstance(p, ToolCallPart) and p.tool_name != "final_result":
                args = {k: _clip(v) for k, v in p.args_as_dict().items() if v not in (None, "")}
                result = results.get(p.tool_call_id)
                steps.append(
                    {"tool": p.tool_name, "args": args, "result": _summarize(result) if result is not None else "(no result)"}
                )
    return steps


def append_audit(entry: dict) -> None:
    """Append one entry, keeping the file a valid JSON array. Never wipes old entries."""
    with _audit_lock:
        entries: list = []
        if AUDIT_PATH.exists():
            try:
                entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
                if not isinstance(entries, list):
                    raise ValueError("audit trail is not a JSON array")
            except ValueError:
                # Don't destroy a damaged file: set it aside and start a new array.
                AUDIT_PATH.rename(AUDIT_PATH.with_suffix(f".corrupt-{int(time.time())}.json"))
                entries = []
        entries.append(entry)
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = AUDIT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, AUDIT_PATH)  # atomic: readers never see half a file


def _audit(
    deps: ShopDeps, messages: list[ModelMessage], usage, stop_reason: str, started: float, check: FactCheck | None
) -> None:
    try:
        append_audit(
            {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "user": "logged-in user" if deps.customer else "guest",
                "page_product": deps.current_product.product_id if deps.current_product else None,
                "model": MODEL_NAME,
                "steps": _steps(messages),
                "model_requests": usage.requests if usage else None,
                "tool_calls": usage.tool_calls if usage else None,
                "tokens": usage.total_tokens if usage else None,
                "fact_check": check.status if check else None,
                "stop_reason": stop_reason,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        )
    except Exception:  # auditing must never break the chat
        log.exception("Could not write audit trail")


# ---------------------------------------------------------------- run

async def run_shop_agent(
    earlier: list[ChatTurn],
    message: str,
    customer: CustomerContext | None,
    current_product: CurrentProduct | None,
) -> tuple[AgentReply, PageSearch | None, FactCheck]:
    """Answer `message`, given the earlier conversation and who/where the shopper is.

    Returns the agent's reply, what show_matching_products/find_alternatives put on the page
    (if anything), and the fact-check result. Every call appends one audit-trail entry.
    """
    deps = ShopDeps(customer=customer, current_product=current_product)
    started = time.monotonic()
    usage = RunUsage()
    with capture_run_messages() as captured:
        try:
            result = await shop_agent.run(
                message, message_history=_history(earlier), deps=deps, usage_limits=USAGE_LIMITS, usage=usage
            )
            check = fact_check(result.output.reply, message, result.new_messages(), deps)
            if check.status != "unverified":
                _audit(deps, result.new_messages(), usage, "answered", started, check)
                return result.output, deps.page_search, check

            # Correction rounds: tell the agent what didn't match and let it re-check with its tools.
            first_new = result.new_messages()
            reply, recheck, retry_new = result.output, check, []
            for _ in range(FACT_CHECK_RETRIES):
                log.warning("Fact check failed, asking agent to correct: %s", recheck.issues)
                retry = await shop_agent.run(
                    "INTERNAL FACT CHECK (not from the shopper): your last reply had numbers that don't match "
                    f"the database: {'; '.join(recheck.issues)}. Look them up again with the tools and rewrite "
                    "the reply for the shopper using only prices and stock numbers the tools return.",
                    message_history=result.all_messages() + retry_new,
                    deps=deps,
                    usage_limits=USAGE_LIMITS,
                    usage=usage,  # the retry counts toward the same per-message limits
                )
                retry_new = retry_new + retry.new_messages()
                reply = retry.output
                recheck = fact_check(reply.reply, message, first_new + retry_new, deps)
                if recheck.status in ("verified", "no_facts"):
                    fixed = FactCheck(
                        status="corrected",
                        prices_checked=recheck.prices_checked,
                        stock_checked=recheck.stock_checked,
                        issues=check.issues,
                    )
                    _audit(deps, first_new + retry_new, usage, "answered_after_fact_fix", started, fixed)
                    return reply, deps.page_search, fixed

            log.warning("Fact check still failing after retry: %s", recheck.issues)
            _audit(deps, first_new + retry_new, usage, "reply_replaced_unverified", started, recheck)
            return AgentReply(reply=UNVERIFIED_REPLY, product_ids=reply.product_ids), deps.page_search, recheck
        except UsageLimitExceeded:
            _audit(deps, captured, usage, "loop_limit_reached", started, None)
            raise
        except ModelHTTPError as exc:
            reason = "blocked_by_content_filter" if "content_filter" in str(exc.body) else "model_error"
            _audit(deps, captured, usage, reason, started, None)
            raise
        except Exception:
            _audit(deps, captured, usage, "error", started, None)
            raise
