"""Read-only database helpers and the tools the shop agent can call.

Every price and stock number the agent quotes must come from these tools,
which read data/campus_customs.db directly.
"""

import difflib
import json
import re
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pydantic_ai import RunContext

from models import (
    PageItem,
    PageSearch,
    PageSearchSummary,
    ProductDetails,
    ProductMatch,
    ProductNotFound,
    ProductSearchResult,
    ShopDeps,
    SizeAvailability,
    StockCheck,
    stock_status,
)

# Paths are resolved from this file, so they work when run from backend/.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "campus_customs.db"
BACKUP_PATH = DATA_DIR / "campus_customs.backup.db"
IMAGES_DIR = (DATA_DIR / "products").resolve()
SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]
MAX_RESULTS = 8  # search_products (agent-only lookup)
MAX_PAGE_RESULTS = 12  # cards shown on the page

STOPWORDS = {
    "a", "an", "and", "any", "do", "does", "for", "have", "i", "in", "is", "it",
    "me", "my", "of", "on", "or", "show", "some", "the", "you", "your", "with",
    "what", "which", "want", "looking", "need", "get", "got", "there", "size",
    "all", "can", "cool", "cute", "gear", "good", "item", "items", "merch", "nice", "option",
    "options", "please", "sell", "carry", "stuff", "thing", "things", "cozy", "clothes",
    "clothing", "apparel", "product", "products",
}


@contextmanager
def get_db(write: bool = False) -> Iterator[sqlite3.Connection]:
    """Read-only by default; write=True backs up the DB first (once)."""
    if write:
        if not BACKUP_PATH.exists():
            shutil.copy2(DB_PATH, BACKUP_PATH)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        if write:
            conn.commit()
    finally:
        conn.close()


# Tidy shop categories for the messy garment_type values (22 spellings in the DB).
CATEGORIES = ["Hoodies", "Crewnecks & sweatshirts", "Quarter-zips", "Tees & tops", "Jackets"]


def category(garment_type: str) -> str:
    g = garment_type.lower()
    if "hood" in g:
        return "Hoodies"
    if "quarter-zip" in g or "1/4" in g:
        return "Quarter-zips"
    if "jacket" in g:
        return "Jackets"
    if "crewneck" in g or "mockneck" in g or "sweatshirt" in g:
        return "Crewnecks & sweatshirts"
    return "Tees & tops"


def image_url(image_file_path: str) -> str:
    # catalogue stores paths like "products/x.jpg", relative to data/
    return f"/images/{Path(image_file_path).name}"


def product_summary(row: sqlite3.Row) -> dict:
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "garment_type": row["garment_type"],
        "category": category(row["garment_type"]),
        "description": row["description"],
        "colors": json.loads(row["colors"]),
        "price": row["price"],
        "image_url": image_url(row["image_file_path"]),
    }


def stock_for(conn: sqlite3.Connection, product_ids: list[str]) -> dict[str, list[dict]]:
    """Per-size stock for each product, in XS→XXL order."""
    if not product_ids:
        return {}
    marks = ",".join("?" * len(product_ids))
    rows = conn.execute(
        f"SELECT product_id, size, quantity FROM inventory WHERE product_id IN ({marks})",
        product_ids,
    ).fetchall()
    out: dict[str, list[dict]] = {pid: [] for pid in product_ids}
    for r in rows:
        out[r["product_id"]].append({"size": r["size"], "quantity": r["quantity"]})
    for sizes in out.values():
        sizes.sort(key=lambda s: SIZE_ORDER.index(s["size"]) if s["size"] in SIZE_ORDER else 99)
    return out


def load_product(product_id: str) -> dict | None:
    """Full product record with stock, or None if the ID doesn't exist."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM catalogue WHERE product_id = ?", (product_id,)
        ).fetchone()
        if row is None:
            return None
        sizes = stock_for(conn, [product_id])[product_id]
    return {
        **product_summary(row),
        "search_tags": json.loads(row["search_tags"]),
        "inventory": sizes,
        "total_stock": sum(s["quantity"] for s in sizes),
    }


def _words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    # crude singular form so "hoodies" matches "hoodie"
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in STOPWORDS]


SIZE_ALIASES = {
    "xs": "XS", "extra small": "XS", "x-small": "XS", "xsmall": "XS",
    "s": "S", "small": "S", "sm": "S",
    "m": "M", "medium": "M", "med": "M",
    "l": "L", "large": "L", "lg": "L",
    "xl": "XL", "extra large": "XL", "x-large": "XL", "xlarge": "XL",
    "xxl": "XXL", "2xl": "XXL", "xx-large": "XXL", "xxlarge": "XXL", "extra extra large": "XXL",
}


def normalize_size(size: str) -> str | None:
    """'large' -> 'L', '2XL' -> 'XXL'. None if it isn't one of our sizes."""
    return SIZE_ALIASES.get(size.strip().lower())


def short_text(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: text.rfind(" ", 0, limit)] + "…"


def _availability(sizes: list[dict]) -> list[SizeAvailability]:
    return [
        SizeAvailability(size=s["size"], quantity=s["quantity"], status=stock_status(s["quantity"]))
        for s in sizes
    ]


def _resolve(conn: sqlite3.Connection, product: str) -> sqlite3.Row | None:
    """Find a product by exact id, or by its exact name (any case)."""
    key = product.strip()
    slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")
    return conn.execute(
        "SELECT * FROM catalogue WHERE product_id = ? OR product_id = ? OR lower(name) = ?",
        (key, slug, key.lower()),
    ).fetchone()


def _not_found(conn: sqlite3.Connection, product: str) -> ProductNotFound:
    rows = conn.execute("SELECT product_id, name FROM catalogue").fetchall()
    by_name = {r["name"].lower(): r for r in rows}
    close = difflib.get_close_matches(product.lower(), list(by_name), n=3, cutoff=0.6)
    return ProductNotFound(
        message=(
            f"No product matches '{product}'. Do not guess: tell the shopper we couldn't find it "
            "and ask which item they mean, or use search_products with keywords."
        ),
        did_you_mean=[f"{by_name[n]['name']} (id: {by_name[n]['product_id']})" for n in close],
    )


# ---------------------------------------------------------------- agent tools

def _search(
    query: str,
    garment_type: str | None,
    color: str | None,
    size: str | None,
    max_price: float | None,
) -> tuple[list[ProductMatch], list[str], str | None]:
    """Shared search engine. Returns (all matches ranked, unmatched query words, normalized size)."""
    wanted_size = normalize_size(size) if size else None
    q_words = _words(query)
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM catalogue").fetchall()
        haystacks = {
            r["product_id"]: " ".join(
                [r["name"], r["garment_type"], r["description"], r["colors"], r["search_tags"]]
            ).lower()
            for r in rows
        }
        unmatched = [w for w in q_words if not any(w in h for h in haystacks.values())]
        scored = []
        for r in rows:
            hay = haystacks[r["product_id"]]
            if garment_type and not all(w in hay for w in _words(garment_type)):
                continue
            if color and color.lower().strip() not in r["colors"].lower():
                continue
            if max_price is not None and r["price"] > max_price:
                continue
            score = sum(w in hay for w in q_words)
            if q_words and score == 0:
                continue
            scored.append((score, r))
        scored.sort(key=lambda x: (-x[0], x[1]["name"]))
        stock = stock_for(conn, [r["product_id"] for _, r in scored])

    results = []
    for _, r in scored:
        sizes = stock[r["product_id"]]
        if wanted_size and not any(s["size"] == wanted_size and s["quantity"] > 0 for s in sizes):
            continue
        results.append(
            ProductMatch(
                product_id=r["product_id"],
                name=r["name"],
                garment_type=r["garment_type"],
                price=r["price"],
                colors=json.loads(r["colors"]),
                short_description=short_text(r["description"]),
                in_stock_sizes=[s["size"] for s in sizes if s["quantity"] > 0],
                sold_out_sizes=[s["size"] for s in sizes if s["quantity"] == 0],
            )
        )
    return results, unmatched, wanted_size


def search_products(
    query: str = "",
    garment_type: str | None = None,
    color: str | None = None,
    size: str | None = None,
    max_price: float | None = None,
) -> ProductSearchResult:
    """Behind-the-scenes catalogue lookup (does NOT change the web page). Use it to find product_ids.

    Returns price, colors, a short description, and which sizes are in stock or sold out.

    Args:
        query: Free-text keywords, e.g. "Harvard game shirt" or "navy hoodie".
        garment_type: Optional garment filter, e.g. "hoodie", "crewneck", "t-shirt".
        color: Optional color filter, e.g. "navy", "gray".
        size: Optional size (XS, S, M, L, XL, XXL, or words like "large"). Only items in stock in that size are returned.
        max_price: Optional highest price in dollars.
    """
    results, unmatched, wanted_size = _search(query, garment_type, color, size, max_price)
    if size and not wanted_size:
        message = f"'{size}' is not a size we carry (sizes are XS, S, M, L, XL, XXL); the size filter was ignored."
    elif not results:
        message = "No products matched. Tell the shopper, and ask what they're looking for. Do not guess."
    elif unmatched:
        message = (
            f"No product mentions {', '.join(repr(w) for w in unmatched)}. Tell the shopper we don't carry "
            "that; these results only match the other words."
        )
    else:
        message = f"Showing {min(len(results), MAX_RESULTS)} of {len(results)} matches."
    return ProductSearchResult(
        query=query,
        match_count=len(results),
        results=results[:MAX_RESULTS],
        unmatched_terms=unmatched,
        message=message,
    )


def show_matching_products(
    ctx: RunContext[ShopDeps],
    query: str = "",
    garment_type: str | None = None,
    color: str | None = None,
    size: str | None = None,
    max_price: float | None = None,
) -> PageSearchSummary:
    """Search the catalogue AND show the matching items as product cards on the shopper's web page.

    Use this when the shopper wants to browse a type of item ("what hoodies do you have?",
    "show me navy crewnecks under $60"). Don't use it for single-item price/stock/description questions.
    Put only concrete product words in `query` (school, team, design, garment); leave out filler like
    "cool" or "some". If nothing matches, the page shows no cards.

    Args:
        query: Product keywords, e.g. "hoodie", "Harvard Yale game", "Branford". Can be empty if filters are used.
        garment_type: Optional garment filter, e.g. "hoodie", "crewneck", "t-shirt".
        color: Optional color filter, e.g. "navy", "gray".
        size: Optional size (XS–XXL or words like "large"). Only items in stock in that size are shown.
        max_price: Optional highest price in dollars.
    """
    results, unmatched, wanted_size = _search(query, garment_type, color, size, max_price)
    # A query word no product mentions (e.g. "Princeton") means we don't carry what was asked for:
    # show nothing rather than passing off partial matches as the real thing.
    shown = [] if unmatched else results[:MAX_PAGE_RESULTS]
    # Heading for the results strip, e.g. "navy hoodie in M under $60.00" (repeated words dropped)
    words = " ".join(x for x in [color, query, garment_type] if x).split()
    label = " ".join(dict.fromkeys(w.lower() for w in words)) or "all products"
    if size and wanted_size:
        label += f" in {wanted_size}"
    if max_price is not None:
        label += f" under ${max_price:.2f}"
    ctx.deps.page_search = PageSearch(
        label=label,
        product_ids=[p.product_id for p in shown],
        total_matches=0 if unmatched else len(results),
    )

    if size and not wanted_size:
        message = f"'{size}' is not a size we carry (XS–XXL); the size filter was ignored."
    elif unmatched:
        message = (
            f"No product mentions {', '.join(repr(w) for w in unmatched)}, so the page shows no cards. "
            "Tell the shopper we don't carry that. If those words were just filler, call this tool again without them."
        )
    elif not shown:
        message = "Nothing matched, so the page shows no cards. Say so honestly and ask what else they'd like."
    else:
        message = (
            f"The page now shows {len(shown)} of {len(results)} matching products as cards. "
            "Give a short summary; don't list every item."
        )
    return PageSearchSummary(
        shown_on_page=len(shown),
        total_matches=0 if unmatched else len(results),
        items=[PageItem(product_id=p.product_id, name=p.name, price=p.price) for p in shown],
        unmatched_terms=unmatched,
        message=message,
    )


def get_product_details(product_id: str) -> ProductDetails | ProductNotFound:
    """Get one product's full description, price, and stock for every size.

    Args:
        product_id: The product_id from search_products (an exact product name also works).
    """
    with get_db() as conn:
        row = _resolve(conn, product_id)
        if row is None:
            return _not_found(conn, product_id)
        sizes = stock_for(conn, [row["product_id"]])[row["product_id"]]
    return ProductDetails(
        product_id=row["product_id"],
        name=row["name"],
        garment_type=row["garment_type"],
        description=row["description"],
        colors=json.loads(row["colors"]),
        price=row["price"],
        sizes=_availability(sizes),
        total_in_stock=sum(s["quantity"] for s in sizes),
        sold_out_sizes=[s["size"] for s in sizes if s["quantity"] == 0],
    )


def check_stock(product_id: str, size: str | None = None) -> StockCheck | ProductNotFound:
    """Check how many of a product are in stock, for one size or for every size.

    Args:
        product_id: The product_id from search_products (an exact product name also works).
        size: Optional size such as "M", "large", or "2XL". Leave empty for all sizes.
    """
    with get_db() as conn:
        row = _resolve(conn, product_id)
        if row is None:
            return _not_found(conn, product_id)
        sizes = _availability(stock_for(conn, [row["product_id"]])[row["product_id"]])

    base = {"product_id": row["product_id"], "name": row["name"]}
    if size is None:
        sold_out = [s.size for s in sizes if s.status == "sold_out"]
        message = f"Sold out in: {', '.join(sold_out)}." if sold_out else "In stock in every size."
        return StockCheck(**base, requested_size=None, sizes=sizes, message=message)

    wanted = normalize_size(size)
    if wanted is None:
        return StockCheck(
            **base, requested_size=size, sizes=sizes,
            message=f"'{size}' is not a size we carry. Sizes are XS, S, M, L, XL, XXL.",
        )
    match = [s for s in sizes if s.size == wanted]
    if not match:
        message = f"No {wanted} stock record for this item."
    elif match[0].status == "sold_out":
        others = [s.size for s in sizes if s.status != "sold_out"]
        message = f"Sold out in {wanted}. In stock in: {', '.join(others) or 'no sizes'}."
    else:
        message = f"{match[0].quantity} in stock in {wanted}."
    return StockCheck(**base, requested_size=wanted, sizes=match, message=message)


MAX_ALTERNATIVES = 6


def find_alternatives(ctx: RunContext[ShopDeps], product_id: str, size: str) -> PageSearchSummary | ProductNotFound:
    """Find similar items that ARE in stock in the shopper's size, and show them as cards on the page.

    Use this when an item is sold out (or low) in the size the shopper wants, or when they ask for
    "something similar" to a product. Similar = same kind of garment, shared colors, shared tags.

    Args:
        product_id: The product they wanted (product_id or exact name).
        size: The size they need, e.g. "M" or "large".
    """
    wanted = normalize_size(size)
    with get_db() as conn:
        base = _resolve(conn, product_id)
        if base is None:
            return _not_found(conn, product_id)
        if wanted is None:
            return ProductNotFound(message=f"'{size}' is not a size we carry. Sizes are XS, S, M, L, XL, XXL.")
        rows = conn.execute("SELECT * FROM catalogue WHERE product_id != ?", (base["product_id"],)).fetchall()
        stock = stock_for(conn, [r["product_id"] for r in rows])

    base_cat = category(base["garment_type"])
    base_colors = set(json.loads(base["colors"]))
    base_tags = {t.lower() for t in json.loads(base["search_tags"])}
    scored = []
    for r in rows:
        qty = next((x["quantity"] for x in stock[r["product_id"]] if x["size"] == wanted), 0)
        if qty == 0:
            continue  # only suggest things they can actually buy in their size
        score = 0.0
        if category(r["garment_type"]) == base_cat:
            score += 3
        score += len(base_colors & set(json.loads(r["colors"])))
        score += 0.5 * len(base_tags & {t.lower() for t in json.loads(r["search_tags"])})
        score -= abs(r["price"] - base["price"]) / 50  # prefer similar price
        if score > 1:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    picks = [r for _, r in scored[:MAX_ALTERNATIVES]]

    ctx.deps.page_search = PageSearch(
        label=f"similar to {base['name']} in {wanted}",
        product_ids=[r["product_id"] for r in picks],
        total_matches=len(scored),
    )
    if picks:
        message = (
            f"The page now shows {len(picks)} similar items in stock in {wanted}. "
            "Mention one or two by name and price; the shopper can see all the cards."
        )
    else:
        message = f"No similar items are in stock in {wanted}. Say so honestly."
    return PageSearchSummary(
        shown_on_page=len(picks),
        total_matches=len(scored),
        items=[PageItem(product_id=r["product_id"], name=r["name"], price=r["price"]) for r in picks],
        unmatched_terms=[],
        message=message,
    )


AGENT_TOOLS = [search_products, show_matching_products, get_product_details, check_stock, find_alternatives]
