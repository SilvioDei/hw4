"""Request/response models for the Campus Customs API and the agent's structured types."""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address.")
    return value


class SignupRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(max_length=128)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be blank.")
        return v

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return normalize_email(v)

    @model_validator(mode="after")
    def passwords_match(self) -> "SignupRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        # No format check here: a bad email just fails like any wrong login.
        return v.strip().lower()


class UserOut(BaseModel):
    """What the frontend is allowed to see about a user (never the hash)."""

    id: int
    first_name: str
    last_name: str
    email: str


# ---------------------------------------------------------------- chat / agent

class AgentReply(BaseModel):
    """Structured output the agent must return."""

    reply: str = Field(max_length=2000, description="Message to show the shopper (plain text).")
    product_ids: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="product_id of each item recommended or discussed (max 6), from tool results only.",
    )


@dataclass
class PageSearch:
    """What show_matching_products found. Recorded by the tool, not written by the model."""

    label: str
    product_ids: list[str]
    total_matches: int


class CustomerContext(BaseModel):
    """The only customer fields the agent sees. Never the password hash, user id, or sign-up date."""

    first_name: str
    last_name: str
    email: str


@dataclass
class CurrentProduct:
    """The product page the shopper is on. Checked against the DB; the name comes from the DB."""

    product_id: str
    name: str


@dataclass
class ShopDeps:
    """Per-request context passed to the agent."""

    customer: CustomerContext | None = None  # None = guest
    current_product: CurrentProduct | None = None  # None = not on a product page
    # Set by show_matching_products; None means this reply shouldn't change the page.
    page_search: PageSearch | None = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class PageContext(BaseModel):
    """Where the shopper is on the site when they send a message."""

    path: str = Field(default="/", max_length=200)
    product_id: str | None = Field(default=None, max_length=100)  # set on /products/{id} only


class ChatRequest(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=50)
    page: PageContext | None = None


class SizeStock(BaseModel):
    size: str
    quantity: int


class ProductCard(BaseModel):
    """Product shown in the chat. Built by the backend from the DB, never by the model."""

    product_id: str
    name: str
    price: float
    image_url: str
    short_description: str
    inventory: list[SizeStock]


class PageResults(BaseModel):
    """Search results for the page's results strip. Cards are built from the DB."""

    query: str = Field(description="Label for the heading, e.g. 'hoodie'.")
    total_matches: int
    products: list[ProductCard] = Field(description="Empty means nothing matched: show no cards.")


class ChatResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    products: list[ProductCard] = []  # small cards inside the chat bubble
    # None = not a search, leave the page as it is. PageResults = replace the results strip.
    page_results: PageResults | None = None
    fact_check: "FactCheck | None" = None  # shown as a small badge under the reply


# ---------------------------------------------------------------- tool results
# What the agent's lookup tools return. Every number here is read from the DB.

StockStatus = Literal["in_stock", "low_stock", "sold_out"]
LOW_STOCK_MAX = 5


def stock_status(quantity: int) -> StockStatus:
    if quantity == 0:
        return "sold_out"
    return "low_stock" if quantity <= LOW_STOCK_MAX else "in_stock"


class SizeAvailability(BaseModel):
    size: str
    quantity: int = Field(description="Units in stock right now. 0 = sold out.")
    status: StockStatus


class ProductMatch(BaseModel):
    """One search hit: enough to pick the right item and answer price questions."""

    product_id: str
    name: str
    garment_type: str
    price: float = Field(description="USD, from the catalogue.")
    colors: list[str]
    short_description: str
    in_stock_sizes: list[str]
    sold_out_sizes: list[str]


class ProductSearchResult(BaseModel):
    query: str
    match_count: int
    results: list[ProductMatch]
    unmatched_terms: list[str] = Field(
        description="Words from the query that match no product at all, e.g. a school or item we don't carry."
    )
    message: str


class ProductDetails(BaseModel):
    """Full record for one product: description, price, and stock for every size."""

    product_id: str
    name: str
    garment_type: str
    description: str
    colors: list[str]
    price: float = Field(description="USD, from the catalogue.")
    sizes: list[SizeAvailability]
    total_in_stock: int
    sold_out_sizes: list[str]


class StockCheck(BaseModel):
    """Stock for one product, for a single size or all sizes."""

    product_id: str
    name: str
    requested_size: str | None
    sizes: list[SizeAvailability]
    message: str


class ProductNotFound(BaseModel):
    """Returned instead of guessing when an ID or size can't be matched."""

    found: Literal[False] = False
    message: str
    did_you_mean: list[str] = Field(default_factory=list, description="Closest product names, if any.")


class PageItem(BaseModel):
    product_id: str
    name: str
    price: float


class PageSearchSummary(BaseModel):
    """What show_matching_products tells the agent about the cards it put on the page."""

    shown_on_page: int
    total_matches: int
    items: list[PageItem]
    unmatched_terms: list[str]
    message: str


class HistoryMessage(BaseModel):
    """One saved chat message, as sent back to the logged-in user who wrote it."""

    role: Literal["user", "assistant"]
    content: str
    products: list[ProductCard] = []  # rebuilt from the live DB, not the saved snapshot
    created_at: str


class ChatHistory(BaseModel):
    messages: list[HistoryMessage]


class FactCheck(BaseModel):
    """Result of checking every price and stock number in a reply against the DB."""

    status: Literal["verified", "corrected", "unverified", "no_facts"] = Field(
        description="verified = all numbers matched; corrected = agent fixed a mismatch on retry; "
        "unverified = still wrong after retry, reply replaced; no_facts = no prices/stock in reply."
    )
    prices_checked: int = 0
    stock_checked: int = 0
    issues: list[str] = []  # mismatches found on the first draft


ChatResponse.model_rebuild()
