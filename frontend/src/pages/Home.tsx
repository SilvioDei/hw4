import { Link } from 'react-router-dom'
import ProductCard from '../components/ProductCard'
import { useProducts } from '../useProducts'

const FEATURED = [
  '2025-yale-vs-harvard-t-shirt',
  'basic-hoodie-big-yale',
  'boola-boola-t-shirt',
  'baseball-left-chest-crewneck',
]

export default function Home() {
  const { products, loading, error } = useProducts()
  const featured = products.filter((p) => FEATURED.includes(p.product_id))

  return (
    <>
      <section className="hero">
        <div className="hero-stamp" aria-hidden="true">
          <span>Game Day</span>
          <strong>Approved</strong>
          <span>★ ★ ★</span>
        </div>
        <div className="hero-text">
          <p className="eyebrow">Fall term · New on the shelves</p>
          <h1>
            Show your colors, <em>all season long.</em>
          </h1>
          <p>
            Cozy crewnecks for late-night study sessions, bold tees for the big game, and hoodies you'll
            keep long after graduation. Everything here is made for the people who make campus home.
          </p>
          <Link to="/products" className="btn btn-light">
            Shop the collection
          </Link>
        </div>
      </section>

      <section className="value-row">
        <div className="index-card">
          <h3>Game-day ready</h3>
          <p>Rivalry tees and spirited layers built for the stands.</p>
        </div>
        <div className="index-card">
          <h3>Sizes XS–XXL</h3>
          <p>Live stock for every size, straight from our shelves.</p>
        </div>
        <div className="index-card">
          <h3>Ask the Clerk</h3>
          <p>Not sure what fits? Tap the seal in the corner for help.</p>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>From the front table</h2>
          <Link to="/products">View all →</Link>
        </div>
        {loading && <p className="status">Loading…</p>}
        {error && <p className="status error">{error}</p>}
        <div className="product-grid">
          {featured.map((p, i) => (
            <ProductCard key={p.product_id} product={p} index={i} />
          ))}
        </div>
      </section>
    </>
  )
}
