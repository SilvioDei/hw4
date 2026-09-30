import { Fragment, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, matchPath, useLocation } from 'react-router-dom'
import { fetchChatHistory, formatPrice, imageSrc, sendChatMessage, type ChatMessage } from '../api'
import { useAuth } from '../auth'
import { useChatResults } from '../chatResults'

const greeting: ChatMessage = {
  role: 'assistant',
  content: "Hi! I'm the Clerk at Campus Customs. Ask me about hoodies, tees, sizes, or gift ideas.",
}

type Chat = { owner: number | null; messages: ChatMessage[] }

// Respect the visitor's reduced-motion setting for JS scrolling too
const scrollBehavior = (): ScrollBehavior =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'

// One-tap questions. On a product page they're about "this" item (uses page context).
const GENERAL_CHIPS = ['What hoodies do you have?', 'Gifts under $40', 'Harvard–Yale game gear', 'Navy crewnecks in M']
const PRODUCT_CHIPS = ['What sizes are in stock?', 'What colors does this come in?', 'Show me similar items', 'How much is this?']

// Badge under replies whose prices/stock were checked against the database
const FACT_BADGE: Record<string, string> = {
  verified: '✓ Checked against inventory',
  corrected: '✓ Corrected against inventory',
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const { setResults } = useChatResults()
  const { user } = useAuth()
  const location = useLocation()
  const endRef = useRef<HTMLDivElement>(null)

  // The conversation belongs to whoever is logged in (null = guest). When the user
  // changes (log in / log out), the old conversation is hidden straight away.
  const owner = user?.id ?? null
  const [chat, setChat] = useState<Chat>({ owner: null, messages: [greeting] })
  const messages = chat.owner === owner ? chat.messages : [greeting]

  // Logged in: reload this user's saved history from the backend.
  useEffect(() => {
    if (owner === null) return
    let cancelled = false
    fetchChatHistory().then((saved) => {
      if (!cancelled) setChat({ owner, messages: [greeting, ...saved] })
    })
    return () => {
      cancelled = true
    }
  }, [owner])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: scrollBehavior() })
  }, [chat, owner, open])

  // Page context: which product page (if any) the shopper is on, so "this" has a meaning.
  const match = matchPath('/products/:productId', location.pathname)
  const productId = match?.params.productId ?? null
  const chips = productId ? PRODUCT_CHIPS : GENERAL_CHIPS

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    send(input)
  }

  async function send(raw: string) {
    const text = raw.trim()
    if (!text || sending) return
    const history: ChatMessage[] = [...messages, { role: 'user', content: text }]
    setChat({ owner, messages: history })
    setInput('')
    setSending(true)
    const page = { path: location.pathname, product_id: productId }
    const { page_results, ...reply } = await sendChatMessage(history, page)
    // Only a search reply replaces the page's results; other replies leave them alone.
    if (page_results) {
      setResults(page_results)
      window.scrollTo({ top: 0, behavior: scrollBehavior() })
    }
    setChat((c) => ({ owner, messages: [...(c.owner === owner ? c.messages : [greeting]), reply] }))
    setSending(false)
  }

  return (
    <div className="chat">
      {open && (
        <section className="chat-panel" aria-label="Chat with Campus Customs">
          <div className="chat-header">
            <span className="nameplate">
              <small>Campus Customs</small>
              Ask the Clerk
            </span>
            <button onClick={() => setOpen(false)} aria-label="Close chat">
              ×
            </button>
          </div>
          <div className="chat-messages">
            {messages.map((m, i) => (
              <Fragment key={i}>
                <div className={`chat-bubble ${m.role}`}>{m.content}</div>
                {m.fact_check && FACT_BADGE[m.fact_check.status] && (
                  <div
                    className={`fact-badge ${m.fact_check.status}`}
                    title={m.fact_check.issues.length ? `Fixed: ${m.fact_check.issues.join('; ')}` : undefined}
                  >
                    {FACT_BADGE[m.fact_check.status]}
                  </div>
                )}
                {m.products && m.products.length > 0 && (
                  <div className="chat-products">
                    {m.products.map((p) => (
                      <Link key={p.product_id} to={`/products/${p.product_id}`} className="chat-product">
                        <img src={imageSrc(p)} alt={p.name} />
                        <div>
                          <strong>{p.name}</strong>
                          <span className="price">{formatPrice(p.price)}</span>
                          <span className="chat-sizes">
                            {p.inventory.map((s) => (
                              <span key={s.size} className={s.quantity === 0 ? 'out' : ''}>
                                {s.size}
                              </span>
                            ))}
                          </span>
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </Fragment>
            ))}
            {sending && (
              <div className="chat-bubble assistant muted typing" aria-label="The Clerk is typing">
                <span />
                <span />
                <span />
              </div>
            )}
            <div ref={endRef} />
          </div>
          <div className="chat-chips" aria-label="Suggested questions">
            {chips.map((c) => (
              <button key={c} type="button" className="chip" onClick={() => send(c)} disabled={sending}>
                {c}
              </button>
            ))}
          </div>
          <form className="chat-input" onSubmit={handleSubmit}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about merch…"
              aria-label="Chat message"
            />
            <button type="submit" className="btn" disabled={sending || !input.trim()}>
              Send
            </button>
          </form>
        </section>
      )}
      <button
        className={open ? 'chat-toggle open' : 'chat-toggle'}
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close chat' : 'Ask the Clerk'}
      >
        {open ? '×' : 'Ask'}
      </button>
    </div>
  )
}
