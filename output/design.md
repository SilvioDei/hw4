# Design: "The Campus Customs Bookstore"

**Direction:** a vintage campus bookstore on the quad, with cream paper, navy ink, brick-red rubber stamps, brass fittings, and oak shelves. The navy comes from the Bulldog Blue reference. No logos, trademarks, or text were copied from yalebulldogblue.com; the "CC" seal and all wording are our own.

**Why it should help:** the look gives Campus Customs a personality shoppers remember, one that reads as "the store on campus" rather than a generic template. Every styled element also makes something clearer: price, stock, where to click, or where to get help. The goal is for shoppers to stay longer and buy with confidence.

## What changed and why

| Area | What changed | Why it helps customers stay and buy |
|---|---|---|
| **Type** | Three self-hosted fonts (`@fontsource`, no third-party requests): **Fraunces** serif for headings and product names, **Source Sans 3** for body text, **Courier Prime** typewriter for prices, sizes, and labels. | The serif sets the campus-heritage mood. The sans keeps descriptions easy to read on phones. Typewriter prices stand out and line up, so price is always the easiest thing to find. |
| **Color and texture** | Paper `#F5EEDC` with a faint grain (inline SVG, no image files), ink navy `#0E2A47`, brick red `#9E3B2C` for stamps and alerts, brass for thin rules, oak for shelves. | Warm and calm, not stark white. Red is saved for the things shoppers must notice: sold out, errors, and the chat seal. |
| **Nav bar** | A store sign: a "CC" seal, a "Campus Customs" wordmark with the tagline "Outfitters to the Quad · Since Move-In Day", small-caps links, and a double brass rule. The ticker-tape announcement bar mentions free pickup and the Clerk. | It looks like a real store. The announcement bar tells shoppers about free pickup and the chat helper before they scroll. |
| **Home hero** | A letterpress poster: big serif headline with a gold italic accent, a rotated "Game Day Approved" ink stamp, faint pennant stripes, and a torn-paper bottom edge. The three feature boxes are ruled index cards. | A strong first impression, with one clear action ("Shop the collection"). |
| **Product cards** | **Shelf tags:** a punched hole with a string, a white image mat, a red category stamp (HOODIES…), and a perforated price stub typed in Courier ("PRICE $68.00"). | Each card reads as a physical tag, so price and category jump out, and the grid is easy to scan. Cards look clickable, which leads to more product-page visits. |
| **Product page** | A **library card:** a matted image and a ruled info card with "Catalogue No. …". Sizes are rows on a lined card; sold-out sizes are struck through with a red **OUT OF STOCK** stamp, and in-stock counts are green. | Availability is unmistakable, so no one reaches checkout for a size that's gone. The stamp is memorable rather than annoying. |
| **Results strip** | A "**Staff picks from the Clerk**" shelf: a brass shelf label as the heading, and cards standing on an oak shelf edge. | Chat results feel like a clerk pulled items off the shelf for you. This makes the search feature feel personal and worth using again. |
| **Chat** | "**Ask the Clerk**": a wax-seal "Ask" button, a brass nameplate header, a paper message area, clerk replies as typed index cards, shopper messages as italic ink notes, suggestion chips as card-catalog tabs, and the fact-check badge as a green "✓ Checked against inventory" stamp. | The chat has a character and a friendly promise. The stamp makes the database-checked prices visible, which builds trust. |
| **Filters and forms** | The Products filter bar is a parchment catalog drawer with tab-shaped category chips. Log in and Create account are "library card applications": typed labels and underline inputs. | Familiar, low-pressure forms, and filtering that looks like flipping through tabs. |
| **Buttons** | Ink buttons with an offset brass "print" shadow that presses in on click. | Clear, satisfying calls to action. |

## Motion

All motion is off when a visitor's system asks for reduced motion (`prefers-reduced-motion`). That covers CSS animations, transitions, and the JavaScript smooth-scrolling.

- **Product cards:** they fade up in a quick cascade when a grid loads (45 ms apart, capped).
- **Hover:** a shelf tag **swings** a little from its hole.
- **Results strip:** it slides down when the Clerk puts new picks on the page.
- **Chat panel:** it **unfolds** from the seal. The typing indicator is three dots pulsing like a pen at work.
- **Stamps:** OUT OF STOCK and "✓ Checked" land with a small stamp "thunk".

## Readability and phones

**Contrast:** every text/background pair meets WCAG AA (4.5:1) or better. Measured ratios:

| Pair | Contrast |
|---|---|
| Ink on paper | 12.6:1 |
| Muted text | 7.0:1 |
| Brick stamps | 5.8:1 |
| Links | 10.5:1 |
| Shelf label | 7.5:1 |
| Seal | 5.7:1 |

The brass shelf label and nameplate were lightened during testing to pass.

**At phone width (375 px):**
- The nav wraps to two rows and the tagline hides.
- Category chips scroll sideways.
- The grids drop to 1–2 columns and the product page stacks.
- The chat opens as a full-width bottom sheet.
- No page scrolls sideways (all pages checked).

## Checked after the restyle

**Page walk-through:** Home, Products, a product page, About Us, Log in, Create account, and log out all render with the new fonts.

**Features:**

| Feature | Result |
|---|---|
| Log in / log out | Logging in as the test user works; the nav shows "Hi, Test / Log out". Logging out works. |
| Filters (F1) | Jackets → 8 of 102. Hoodies + XXL + price sort → 23 of 102. |
| Chat search | "What hoodies do you have?" chip → 12 cards on the shelf, heading "hoodie: 12 of 27 items", ✓ badge. |
| Chips (F2) | They change on product pages. |
| Alternatives (B1) | "Show me similar items" → "Large please" → "Similar to Boola Boola T Shirt in L: 6 of 40 items". |
| Fact-check (B2) | The badge shows under numeric replies. |

**Bug found and fixed:** during the walk-through, the product page could get stuck on "Loading…" after two quick navigations, because a slow earlier reply overwrote the newer page. It now ignores replies for pages the shopper has already left.
