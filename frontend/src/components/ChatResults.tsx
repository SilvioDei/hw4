import ProductCard from './ProductCard'
import { useChatResults } from '../chatResults'

// Results strip under the nav bar, shown on every page after a chat search.
// Styled as a "staff picks" shelf; re-keyed per search so the slide-in replays.
export default function ChatResults() {
  const { results, setResults } = useChatResults()
  if (!results) return null

  const count = results.products.length
  const searchKey = `${results.query}|${results.products.map((p) => p.product_id).join(',')}`
  return (
    <section key={searchKey} className="chat-results" aria-live="polite" aria-label="Products found by the chat assistant">
      <div className="chat-results-head">
        <div className="shelf-label">
          <p className="eyebrow">Staff picks from the Clerk</p>
          <h2>
            {count > 0
              ? `${results.query}: ${count}${results.total_matches > count ? ` of ${results.total_matches}` : ''} ${count === 1 ? 'item' : 'items'}`
              : `No products matched "${results.query}"`}
          </h2>
        </div>
        <button className="btn btn-small btn-outline" onClick={() => setResults(null)}>
          Clear
        </button>
      </div>
      {count > 0 && (
        <div className="product-grid shelf">
          {results.products.map((p, i) => (
            <ProductCard key={p.product_id} product={p} index={i} />
          ))}
        </div>
      )}
    </section>
  )
}
