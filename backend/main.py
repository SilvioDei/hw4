"""Campus Customs API.

FastAPI app that serves the product catalogue, per-size inventory, and product
images from data/, account sign-up and login, and the shop chatbot (a PydanticAI
agent in agent.py). Price and stock always come from the database.

Run from the backend/ folder:
    uvicorn main:app --reload --port 8000
"""

import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import time

from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded

from agent import run_shop_agent
from models import (
    ChatHistory,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    CurrentProduct,
    CustomerContext,
    HistoryMessage,
    LoginRequest,
    PageContext,
    PageResults,
    ProductCard,
    SignupRequest,
    UserOut,
)
from tools import (
    IMAGES_DIR,
    MAX_PAGE_RESULTS,
    get_db,
    load_product,
    product_summary,
    short_text,
    stock_for,
)

log = logging.getLogger("campus_customs")

app = FastAPI(title="Campus Customs API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,  # needed for the session cookie
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI's default echoes the request body back, which would include
    # passwords. Return only the message and field location.
    errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


# ---------------------------------------------------------------- products

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/products")
def list_products() -> list[dict]:
    """All products, with the sizes currently in stock (used by the Products page filters)."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM catalogue ORDER BY name").fetchall()
        stock = stock_for(conn, [r["product_id"] for r in rows])
    return [
        {
            **product_summary(r),
            "in_stock_sizes": [s["size"] for s in stock[r["product_id"]] if s["quantity"] > 0],
        }
        for r in rows
    ]


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict:
    product = load_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.get("/images/{filename}")
def get_image(filename: str) -> FileResponse:
    path = (IMAGES_DIR / filename).resolve()
    # Block path traversal: the file must sit directly inside data/products/.
    if path.parent != IMAGES_DIR or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


# ---------------------------------------------------------------- passwords
# Matches the seed accounts: "pbkdf2_sha256$<salt>$<hex digest>", where the
# salt string is used as UTF-8 text and the iteration count is fixed at 120,000.

HASH_ALGO = "pbkdf2_sha256"
HASH_ITERATIONS = 120_000


def _pbkdf2(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), HASH_ITERATIONS
    ).hex()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)  # 128-bit random salt, unique per user
    return f"{HASH_ALGO}${salt}${_pbkdf2(password, salt)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != HASH_ALGO:
        return False
    return hmac.compare_digest(_pbkdf2(password, salt), digest)


# Used when the email doesn't exist, so a login takes the same time either way.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# ---------------------------------------------------------------- sessions
# Random session IDs live only in server memory and reach the browser in an
# HttpOnly cookie, so page scripts can't read them. Restarting the server
# logs everyone out.

SESSION_COOKIE = "cc_session"
SESSION_TTL = 7 * 24 * 3600
_sessions: dict[str, tuple[int, float]] = {}  # session id -> (user id, expiry)

LOGIN_ERROR = "Incorrect email or password."
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 15 * 60
_failed_logins: dict[str, list[float]] = {}  # "ip|email" -> failure times


def _user_out(row: sqlite3.Row) -> UserOut:
    return UserOut(
        id=row["id"],
        first_name=row["first_name"] or row["name"].split(" ")[0],
        last_name=row["last_name"] or "",
        email=row["email"],
    )


def _start_session(response: Response, user_id: int) -> None:
    sid = secrets.token_urlsafe(32)
    _sessions[sid] = (user_id, time.time() + SESSION_TTL)
    response.set_cookie(
        SESSION_COOKIE, sid, max_age=SESSION_TTL, httponly=True, samesite="lax",
        secure=False,  # localhost is plain http; set True when served over https
    )


def current_user_id(session_id: str | None) -> int | None:
    entry = _sessions.get(session_id or "")
    if entry is None:
        return None
    user_id, expires = entry
    if time.time() > expires:
        _sessions.pop(session_id, None)
        return None
    return user_id


def _too_many_failures(key: str) -> bool:
    now = time.time()
    recent = [t for t in _failed_logins.get(key, []) if now - t < LOCKOUT_SECONDS]
    _failed_logins[key] = recent
    return len(recent) >= MAX_FAILED_LOGINS


# ---------------------------------------------------------------- auth API

@app.post("/api/auth/signup", status_code=201)
def signup(body: SignupRequest, response: Response) -> UserOut:
    with get_db(write=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = ?", (body.email,)
        ).fetchone()
        if exists:
            raise HTTPException(
                status_code=409, detail="An account with this email already exists."
            )
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, first_name, last_name)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                f"{body.first_name} {body.last_name}",
                body.email,
                hash_password(body.password),
                body.first_name,
                body.last_name,
            ),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    _start_session(response, row["id"])
    return _user_out(row)


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response) -> UserOut:
    key = f"{request.client.host if request.client else ''}|{body.email}"
    if _too_many_failures(key):
        raise HTTPException(
            status_code=429, detail="Too many attempts. Please try again in 15 minutes."
        )
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email) = ?", (body.email,)
        ).fetchone()
    # Always run one hash check so unknown emails aren't faster to reject.
    ok = verify_password(body.password, row["password_hash"] if row else _DUMMY_HASH)
    if not (row and ok):
        _failed_logins.setdefault(key, []).append(time.time())
        raise HTTPException(status_code=401, detail=LOGIN_ERROR)
    _failed_logins.pop(key, None)
    _start_session(response, row["id"])
    return _user_out(row)


@app.post("/api/auth/logout")
def logout(response: Response, cc_session: str | None = Cookie(default=None)) -> dict:
    _sessions.pop(cc_session or "", None)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(cc_session: str | None = Cookie(default=None)) -> UserOut:
    user_id = current_user_id(cc_session)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return _user_out(row)


# ---------------------------------------------------------------- chat

MAX_CARDS = 6
HISTORY_LIMIT = 50  # messages returned to the chat panel
AGENT_HISTORY_LIMIT = 20  # earlier messages given to the agent
CHAT_ERROR = "Sorry, I'm having trouble answering right now. Please try again in a moment."
CHAT_TOO_LONG = (
    "Sorry, that question needed more lookups than I'm allowed for one message. "
    "Could you ask about one item or category at a time?"
)
CHAT_BLOCKED = (
    "Sorry, I can't help with that. I'm here to help you find Campus Customs gear. "
    "Ask me about products, sizes, prices, or stock!"
)


def _cards(product_ids: list[str], limit: int = MAX_CARDS) -> list[ProductCard]:
    """Build product cards from the DB. Unknown IDs are dropped, so the model can't invent items."""
    cards: list[ProductCard] = []
    for pid in dict.fromkeys(product_ids):  # de-duplicate, keep order
        product = load_product(pid)
        if product:
            cards.append(ProductCard(**product, short_description=short_text(product["description"])))
        if len(cards) == limit:
            break
    return cards


def _customer(user_id: int | None) -> CustomerContext | None:
    """Just the fields the agent may see. The password hash is never selected."""
    if user_id is None:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT name, first_name, last_name, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None:
        return None
    return CustomerContext(
        first_name=row["first_name"] or row["name"].split(" ")[0],
        last_name=row["last_name"] or "",
        email=row["email"],
    )


def _current_product(page: PageContext | None) -> CurrentProduct | None:
    """The product page the shopper is on, if the id is real. Name comes from the DB."""
    if page is None or not page.product_id:
        return None
    product = load_product(page.product_id)
    return CurrentProduct(product_id=product["product_id"], name=product["name"]) if product else None


def _saved_rows(user_id: int, limit: int) -> list[sqlite3.Row]:
    """The newest `limit` messages for this user only, oldest first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content, products_json, created_at FROM chat_messages"
            " WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return list(reversed(rows))


def _chat_card_ids(products_json: str | None) -> list[str]:
    """Product IDs that were shown in the chat bubble.

    New rows store [{"product_id", "shown_on"}]; older seed rows store full product
    snapshots. Either way only the id is used, and cards are rebuilt from the live DB.
    """
    try:
        items = json.loads(products_json or "[]")
    except json.JSONDecodeError:
        return []
    return [
        i["product_id"]
        for i in items
        if isinstance(i, dict) and "product_id" in i and i.get("shown_on", "chat") == "chat"
    ]


def _save_exchange(user_id: int, user_text: str, reply: ChatResponse) -> None:
    """Save the user's message and the reply together, linked to the logged-in user."""
    shown = [{"product_id": p.product_id, "shown_on": "chat"} for p in reply.products]
    if reply.page_results:
        shown += [{"product_id": p.product_id, "shown_on": "page"} for p in reply.page_results.products]
    with get_db(write=True) as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (?, 'user', ?)",
            (user_id, user_text),
        )
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, 'assistant', ?, ?)",
            (user_id, reply.content, json.dumps(shown)),
        )


@app.get("/api/chat/history")
def chat_history(cc_session: str | None = Cookie(default=None)) -> ChatHistory:
    """The logged-in user's own saved chat. Guests get an empty list."""
    user_id = current_user_id(cc_session)  # from the session cookie, never from the request
    if user_id is None:
        return ChatHistory(messages=[])
    return ChatHistory(
        messages=[
            HistoryMessage(
                role=r["role"],
                content=r["content"],
                products=_cards(_chat_card_ids(r["products_json"])) if r["role"] == "assistant" else [],
                created_at=r["created_at"],
            )
            for r in _saved_rows(user_id, HISTORY_LIMIT)
        ]
    )


@app.post("/api/chat")
async def chat(body: ChatRequest, cc_session: str | None = Cookie(default=None)) -> ChatResponse:
    latest = body.messages[-1]
    if latest.role != "user":
        raise HTTPException(status_code=422, detail="The last message must be from the user.")

    user_id = current_user_id(cc_session)
    customer = _customer(user_id)
    if customer is None:
        user_id = None
    if user_id is not None:
        # Logged in: the agent's memory is the user's saved history, not what the browser sent.
        earlier = [
            ChatTurn(role=r["role"], content=r["content"])
            for r in _saved_rows(user_id, AGENT_HISTORY_LIMIT)
        ]
    else:
        earlier = body.messages[:-1]  # guest: only the conversation on screen

    try:
        output, page_search, check = await run_shop_agent(
            earlier, latest.content, customer, _current_product(body.page)
        )
    except UsageLimitExceeded:
        # Hit the per-message loop limit (model requests / tool calls / tokens) in agent.py
        log.warning("Chat message hit the agent loop limit")
        return ChatResponse(content=CHAT_TOO_LONG)
    except ModelHTTPError as exc:
        # The model host's content filter blocks some messages (e.g. jailbreak attempts).
        if "content_filter" in str(exc.body):
            log.warning("Chat message blocked by content filter")
            return ChatResponse(content=CHAT_BLOCKED)
        log.exception("Agent call failed")
        return ChatResponse(content=CHAT_ERROR)
    except Exception:
        log.exception("Agent call failed")
        return ChatResponse(content=CHAT_ERROR)

    if page_search is None:
        # Not a browse search: leave the page's results strip as it is.
        response = ChatResponse(content=output.reply, products=_cards(output.product_ids), fact_check=check)
    else:
        # Browse search: cards go to the page (from the tool's IDs, not the model's), not the chat bubble.
        response = ChatResponse(
            content=output.reply,
            fact_check=check,
            page_results=PageResults(
                query=page_search.label,
                total_matches=page_search.total_matches,
                products=_cards(page_search.product_ids, limit=MAX_PAGE_RESULTS),
            ),
        )

    if user_id is not None:  # guests' chats are never saved
        _save_exchange(user_id, latest.content, response)
    return response
