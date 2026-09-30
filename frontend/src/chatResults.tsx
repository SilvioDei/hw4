import { createContext, useContext, useState, type ReactNode } from 'react'
import type { PageResults } from './api'

// Latest search results the chat put on the page. Lives above the router,
// so the results survive moving between pages (e.g. open a card, then go back).
type ChatResultsState = {
  results: PageResults | null
  setResults: (r: PageResults | null) => void
}

const ChatResultsContext = createContext<ChatResultsState | null>(null)

export function ChatResultsProvider({ children }: { children: ReactNode }) {
  const [results, setResults] = useState<PageResults | null>(null)
  return <ChatResultsContext.Provider value={{ results, setResults }}>{children}</ChatResultsContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useChatResults(): ChatResultsState {
  const ctx = useContext(ChatResultsContext)
  if (!ctx) throw new Error('useChatResults must be used inside ChatResultsProvider')
  return ctx
}
