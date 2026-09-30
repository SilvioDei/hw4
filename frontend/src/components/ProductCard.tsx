import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { formatPrice, imageSrc, shortDescription } from '../api'

// Works for catalogue products (full description) and chat results (short_description from the API).
type CardProduct = {
  product_id: string
  name: string
  price: number
  image_url: string
  description?: string
  short_description?: string
  category?: string
}

// Styled as a shelf tag: punched hole + string, perforation, category stamp, typed price stub.
export default function ProductCard({ product, index = 0 }: { product: CardProduct; index?: number }) {
  const info = product.short_description ?? shortDescription(product.description ?? '')
  const style = { '--i': Math.min(index, 11) } as CSSProperties // cascade delay, capped
  return (
    <Link to={`/products/${product.product_id}`} className="product-card" style={style}>
      <span className="tag-hole" aria-hidden="true" />
      <div className="product-card-image">
        <img src={imageSrc(product)} alt={product.name} loading="lazy" />
        {product.category && <span className="tag-stamp">{product.category}</span>}
      </div>
      <div className="product-card-body">
        <h3>{product.name}</h3>
        <p className="muted">{info}</p>
        <p className="price-stub">
          <span className="price-label">Price</span>
          <span className="price">{formatPrice(product.price)}</span>
        </p>
      </div>
    </Link>
  )
}
