import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import ProductCard from '../components/ProductCard'
import { useProducts } from '../useProducts'

const CATEGORIES = ['Hoodies', 'Crewnecks & sweatshirts', 'Quarter-zips', 'Tees & tops', 'Jackets']
const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
const SORTS = {
  name: 'Name (A–Z)',
  'price-asc': 'Price: low to high',
  'price-desc': 'Price: high to low',
} as const
type SortKey = keyof typeof SORTS

export default function Products() {
  const { products, loading, error } = useProducts()
  // Filters live in the URL (?category=Hoodies&size=M…) so a filtered view can be shared or bookmarked.
  const [params, setParams] = useSearchParams()
  const cat = params.get('category') ?? ''
  const color = params.get('color') ?? ''
  const size = params.get('size') ?? ''
  const sort = (params.get('sort') ?? 'name') as SortKey

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  // Main colors only (used by 3+ products), so the dropdown stays short
  const colors = useMemo(() => {
    const counts = new Map<string, number>()
    products.forEach((p) => p.colors.forEach((c) => counts.set(c, (counts.get(c) ?? 0) + 1)))
    return [...counts].filter(([, n]) => n >= 3).map(([c]) => c).sort()
  }, [products])

  const shown = useMemo(() => {
    const list = products.filter(
      (p) =>
        (!cat || p.category === cat) &&
        (!color || p.colors.includes(color)) &&
        (!size || p.in_stock_sizes?.includes(size)),
    )
    if (sort === 'price-asc') return [...list].sort((a, b) => a.price - b.price || a.name.localeCompare(b.name))
    if (sort === 'price-desc') return [...list].sort((a, b) => b.price - a.price || a.name.localeCompare(b.name))
    return list
  }, [products, cat, color, size, sort])

  const filtered = Boolean(cat || color || size)

  return (
    <section className="section">
      <div className="section-head">
        <h1>All products</h1>
        {!loading && !error && (
          <span className="muted">
            {filtered ? `${shown.length} of ${products.length} items` : `${products.length} items`}
          </span>
        )}
      </div>

      <div className="filter-bar" role="search" aria-label="Filter products">
        <div className="filter-chips" role="group" aria-label="Category">
          <button className={!cat ? 'chip active' : 'chip'} onClick={() => setParam('category', '')}>
            All
          </button>
          {CATEGORIES.map((c) => (
            <button key={c} className={cat === c ? 'chip active' : 'chip'} onClick={() => setParam('category', c)}>
              {c}
            </button>
          ))}
        </div>
        <div className="filter-selects">
          <label>
            Color
            <select value={color} onChange={(e) => setParam('color', e.target.value)}>
              <option value="">Any color</option>
              {colors.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label>
            In stock in
            <select value={size} onChange={(e) => setParam('size', e.target.value)}>
              <option value="">Any size</option>
              {SIZES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sort
            <select value={sort} onChange={(e) => setParam('sort', e.target.value === 'name' ? '' : e.target.value)}>
              {Object.entries(SORTS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {filtered && (
            <button className="btn btn-small btn-outline" onClick={() => setParams({}, { replace: true })}>
              Clear filters
            </button>
          )}
        </div>
      </div>

      {loading && <p className="status">Loading…</p>}
      {error && <p className="status error">{error}</p>}
      {!loading && !error && shown.length === 0 && (
        <p className="status">No products match these filters. Try another size or color, or ask our chat assistant.</p>
      )}
      <div className="product-grid">
        {shown.map((p, i) => (
          <ProductCard key={p.product_id} product={p} index={i} />
        ))}
      </div>
    </section>
  )
}
