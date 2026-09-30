import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchProduct, formatPrice, imageSrc, type ProductDetail } from '../api'

export default function ProductPage() {
  const { productId = '' } = useParams()
  // Results are tagged with the id they belong to, so a stale result shows as loading.
  const [result, setResult] = useState<{ id: string; product?: ProductDetail; error?: string }>()

  useEffect(() => {
    let cancelled = false // ignore a slow reply for a page the shopper already left
    fetchProduct(productId)
      .then((product) => !cancelled && setResult({ id: productId, product }))
      .catch(() => !cancelled && setResult({ id: productId, error: 'We could not find that product.' }))
    return () => {
      cancelled = true
    }
  }, [productId])

  const current = result?.id === productId ? result : undefined
  if (current?.error) return <p className="status error">{current.error}</p>
  const product = current?.product
  if (!product) return <p className="status">Loading…</p>

  return (
    <section className="section">
      <Link to="/products" className="back-link">
        ← Back to products
      </Link>
      <div className="product-detail">
        <div className="product-detail-image">
          <img src={imageSrc(product)} alt={product.name} />
        </div>
        <div className="product-detail-info library-card">
          <p className="catalogue-no">Catalogue No. {product.product_id}</p>
          <p className="eyebrow">{product.garment_type}</p>
          <h1>{product.name}</h1>
          <p className="price price-large">{formatPrice(product.price)}</p>
          <p>{product.description}</p>
          <p className="muted">Colors: {product.colors.join(', ')}</p>

          <h3>Sizes on the shelf</h3>
          <ul className="size-list">
            {product.inventory.map((s) => (
              <li key={s.size} className={s.quantity === 0 ? 'size out' : 'size'}>
                <span className="size-name">{s.size}</span>
                {s.quantity === 0 ? (
                  <span className="stamp">Out of stock</span>
                ) : (
                  <span className="size-qty">{s.quantity} in stock</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
