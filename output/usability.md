# Usability improvements

Four improvements were added after the core shop worked: two on the front end and two in the agent/backend. Each one is visible in the running app. Start the backend (`uvicorn main:app --reload --port 8000` from `backend/`) and the frontend (`npm run dev` from `frontend/`), then open http://localhost:5173.

---

## F1. Filter and sort bar on the Products page

**What was added**

- A filter bar at the top of **Products** (`frontend/src/pages/Products.tsx`):
  - **Category buttons:** All · Hoodies · Crewnecks & sweatshirts · Quarter-zips · Tees & tops · Jackets. These come from a new `category` field that the backend (`tools.category()`) derives from the 22 inconsistent `garment_type` spellings in the database.
  - **Color dropdown:** the main colors, meaning those used by 3 or more products.
  - **"In stock in" size dropdown:** hides items that are sold out in that size. It uses the live `in_stock_sizes` that `GET /api/products` now returns from the `inventory` table.
  - **Sort:** name, price low → high, or price high → low.
  - **Live count** ("23 of 102 items") and a **Clear filters** button.
- **Friendly empty state:** if nothing matches, the page says so and points to the chat assistant.
- **Shareable views:** filters are saved in the URL (e.g. `/products?category=Hoodies&size=XXL&sort=price-desc`), so a view can be bookmarked or shared.

**Why it helps**

102 products in one long grid is hard to browse. A shopper who wants "a hoodie I can actually get in XXL" finds it in two clicks, with no scrolling and no clicking into sold-out items. For the business, that means fewer shoppers giving up, and the size filter stops people falling for items they can't buy.

**How a grader can see it**

On **Products**, click **Hoodies**, choose **In stock in → XXL**, then **Sort → Price: high to low**. The count updates, and the URL changes.

---

## F2. Suggested-question chips in the chat

**What was added**

- A row of one-tap question chips above the chat input (`frontend/src/components/ChatWidget.tsx`).
- **They change with the page:**
  - **Anywhere else:** "What hoodies do you have?", "Gifts under $40", "Harvard–Yale game gear", "Navy crewnecks in M".
  - **On a product page:** "What sizes are in stock?", "What colors does this come in?", "Show me similar items", "How much is this?"
- Tapping a chip sends it like a typed message.
- The product-page chips use the page context from Problem 8, so "this" means the item being viewed. "Show me similar items" leads straight into B1.

**Why it helps**

Many shoppers don't know what a shop bot can do, or don't want to type on a phone. Chips show the assistant's main skills (browse, gifts, sizes, colors, alternatives) and get a useful answer in one tap. That drives chat engagement, which drives product views.

**How a grader can see it**

Open the chat bubble (bottom right) on Home and the four general chips appear. Open any product page and the chips change to the "this item" questions. Tap one.

---

## B1. "Similar items in your size" tool (`find_alternatives`)

**What was added**

- A new read-only agent tool in `backend/tools.py`: `find_alternatives(product_id, size)`.
- It returns **only** items that have stock in that size, ranked by similarity:
  - same category (+3)
  - shared colors (+1 each)
  - shared tags (+0.5 each)
  - a closer price scores higher
- It puts up to 6 of them in the page's results strip, using the same "cards built from the DB" contract as Problem 7. The heading reads "Similar to Boola Boola T Shirt in L".
- `prompt.md` tells the agent to use it whenever an item is sold out in the shopper's size, or they ask for something similar.

**Why it helps**

"Sold out in L" used to be a dead end. Now the shopper immediately sees real items they *can* buy in their size, and the model can't recommend anything that's actually sold out. That turns a lost sale into a likely sale.

**How a grader can see or test it**

1. Open the **Boola Boola T Shirt** product page. Size L shows "Out of stock".
2. In the chat, type **"I really need a large in this. What else could I get?"** (or tap **Show me similar items**).
3. The results strip fills with similar T-shirts, and each one's product page shows L in stock.

---

## B2. Price and stock fact-checker on every reply

**What was added**

- **The check:** after the agent drafts a reply, `fact_check()` in `backend/agent.py` finds every dollar amount (`$32.00`) and stock count ("15 in stock", "only 2 left") in the text.
  - Each one is compared with the **live database** values for the products this turn actually touched: tool results, the current product page, and the cards on the page.
  - Budgets the shopper typed ("under $40") and search thresholds are allowed.
- **Outcomes:**
  - **All numbers match:** the reply goes out marked `verified`.
  - **A mismatch:** the agent gets one automatic correction round ("INTERNAL FACT CHECK: your reply said $24.99, which doesn't match the database…"). It looks the numbers up again and rewrites the reply, which is marked `corrected`.
  - **Still wrong after the retry:** the reply is replaced with a safe "please check the product page" message (`unverified`). A wrong number never reaches the shopper.
- **Where the result appears:**
  - `/api/chat` returns `fact_check { status, prices_checked, stock_checked, issues }`.
  - The chat shows a small green badge under checked replies: **"✓ Prices & stock checked against inventory"**. An amber **"✓ Numbers corrected against inventory"** appears if a fix was needed; hover it to see what was fixed.
  - Mismatches are also logged on the server.

**Why it helps**

The assignment's core rule is that price and stock must come from the database, never be guessed. The prompt asks for that; this check *enforces* it on the finished text. Shoppers never see a wrong price, and the store avoids complaints and the cost of honoring a price the bot made up. The badge also builds shopper trust. It costs nothing extra on normal replies: the second model call only happens when a mismatch is found.

**How a grader can see or test it**

1. **In the app:** ask any price or stock question, e.g. tap **What sizes are in stock?** on a product page. The green badge appears under the reply. Replies with no numbers get no badge.
2. **Force a mismatch (no API cost).** From `backend/` with the venv active, run the snippet below. It swaps in a scripted fake model that misquotes the Boola Boola price as $24.99 on its first draft.

```python
import asyncio, json
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from agent import run_shop_agent, shop_agent
from models import CurrentProduct

def scripted(messages, info):
    fixed = "INTERNAL FACT CHECK" in str(messages[-1].parts[-1].content)
    reply = "The Boola Boola T Shirt is $32.00." if fixed else "The Boola Boola T Shirt is $24.99!"
    return ModelResponse(parts=[TextPart(json.dumps({"reply": reply, "product_ids": []}))])

async def main():
    page = CurrentProduct(product_id="boola-boola-t-shirt", name="Boola Boola T Shirt")
    with shop_agent.override(model=FunctionModel(scripted)):
        out, _, check = await run_shop_agent([], "How much is this?", None, page)
    print(out.reply, check.model_dump())

asyncio.run(main())
```

Expected output: `The Boola Boola T Shirt is $32.00.` with `status: 'corrected'` and `issues: ['price $24.99 is not the database price of any product discussed']`.

---

## Test results

| Improvement | Test | Result |
|---|---|---|
| **F1** | Products → Hoodies → In stock in XXL → Price high to low | 102 → **27** → **23** items. Top result Brooks Brothers Double Knit Full Zip Hoodie Yale **$88.00**. URL `?category=Hoodies&size=XXL&sort=price-desc`. The color list has no "pink", since no product is pink. |
| **F2** | Open the chat on Home, then on the Boola Boola page; tap "What sizes are in stock?" | Home shows the 4 general chips; the product page shows the 4 "this item" chips. Reply: "…in stock in XS, S, M, XL, and XXL. Size L is currently sold out, and there are only 2 left in XL." ✓ badge. |
| **F2** | Tap "Gifts under $40" | "I found 25 options, with 12 now displayed… priced at $32.00." Results strip: "All products under $40.00: 12 of 25 items". ✓ badge; the $40 budget was correctly not flagged. |
| **B1** | Boola Boola page (L sold out): "I really need a large in this. What else could I get?" | "…sold out in L, but these similar T-shirts are available in that size: District Tri Blend T Shirt Vintage Shield and Football Left Chest T Shirt, both $32.00." The strip shows 6 T-shirts; the DB confirms each has L stock (8, 2, 2, 15, 25, 8). |
| **B2** | Offline checks on 5 sample replies | Correct numbers → `verified`. Wrong price $29.99 → flagged. Wrong stock "40 in stock" → flagged. Budget "under $60" → not flagged. No numbers → `no_facts`. |
| **B2** | Scripted fake model misquotes $24.99 (snippet above) | Mismatch caught, agent corrected to **$32.00**, status `corrected`. |
| **B2** | Live replies above | Every numeric reply returned `verified`, and the badge showed in the chat. |
