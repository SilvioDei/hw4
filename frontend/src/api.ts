// All calls to the Campus Customs backend live here.
export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Product = {
  product_id: string
  name: string
  garment_type: string
  description: string
  colors: string[]
  price: number
  image_url: string
  category: string
  in_stock_sizes?: string[] // only on the product list
}

export type SizeStock = { size: string; quantity: number }

export type ProductDetail = Product & {
  search_tags: string[]
  inventory: SizeStock[]
  total_stock: number
}

// Product card attached to a chat reply (price/stock filled in by the backend from the DB)
export type ChatProduct = Pick<Product, 'product_id' | 'name' | 'price' | 'image_url'> & {
  short_description: string
  inventory: SizeStock[]
}

// Search results the chat puts on the page (cards built by the backend from the DB)
export type PageResults = { query: string; total_matches: number; products: ChatProduct[] }

// Backend check of every price/stock number in a reply against the database
export type FactCheck = {
  status: 'verified' | 'corrected' | 'unverified' | 'no_facts'
  prices_checked: number
  stock_checked: number
  issues: string[]
}

export type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  products?: ChatProduct[]
  fact_check?: FactCheck | null
}

// page_results: null/absent = not a search, leave the page alone; object = replace the results strip
export type ChatReply = ChatMessage & { page_results?: PageResults | null }

export const imageSrc = (p: { image_url: string }) => `${API_URL}${p.image_url}`

export const formatPrice = (price: number) => `$${price.toFixed(2)}`

export function shortDescription(text: string, max = 90): string {
  if (text.length <= max) return text
  return text.slice(0, text.lastIndexOf(' ', max)) + '…'
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`)
  if (!res.ok) throw new Error(`Request failed (${res.status})`)
  return res.json() as Promise<T>
}

export const fetchProducts = () => getJson<Product[]>('/api/products')

// ---- accounts (session lives in an HttpOnly cookie, so send credentials)

export type User = { id: number; first_name: string; last_name: string; email: string }

export type SignupData = {
  first_name: string
  last_name: string
  email: string
  password: string
  confirm_password: string
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
    // FastAPI validation errors come back as a list
    const first = Array.isArray(body.detail) ? body.detail[0] : null
    if (first?.msg) return String(first.msg).replace(/^Value error, /, '')
  } catch {
    // not JSON
  }
  return 'Something went wrong. Please try again.'
}

async function postAuth(path: string, data?: object): Promise<Response> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res
}

export const login = async (email: string, password: string) =>
  (await (await postAuth('/api/auth/login', { email, password })).json()) as User

export const signup = async (data: SignupData) =>
  (await (await postAuth('/api/auth/signup', data)).json()) as User

export const logout = async () => {
  await postAuth('/api/auth/logout')
}

export async function fetchMe(): Promise<User | null> {
  const res = await fetch(`${API_URL}/api/auth/me`, { credentials: 'include' })
  return res.ok ? ((await res.json()) as User) : null
}

export const fetchProduct = (id: string) =>
  getJson<ProductDetail>(`/api/products/${encodeURIComponent(id)}`)

// Where the shopper is; product_id is set only on a product page (/products/:id)
export type PageContext = { path: string; product_id: string | null }

// The logged-in user's own saved chat (empty for guests)
export async function fetchChatHistory(): Promise<ChatMessage[]> {
  try {
    const res = await fetch(`${API_URL}/api/chat/history`, { credentials: 'include' })
    if (!res.ok) return []
    const body = (await res.json()) as { messages: ChatMessage[] }
    return body.messages.map(({ role, content, products }) => ({ role, content, products }))
  } catch {
    return []
  }
}

// Sends the conversation plus page context to the shop agent (POST /api/chat).
export async function sendChatMessage(history: ChatMessage[], page: PageContext): Promise<ChatReply> {
  try {
    const res = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      // only role + content go to the backend; product cards are display-only
      body: JSON.stringify({ messages: history.map(({ role, content }) => ({ role, content })), page }),
    })
    if (res.ok) return (await res.json()) as ChatReply
  } catch {
    // backend not reachable
  }
  return {
    role: 'assistant',
    content: "Sorry, I can't reach the shop right now. Please make sure the backend is running and try again.",
  }
}
