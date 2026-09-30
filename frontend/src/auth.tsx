import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import * as api from './api'

type AuthState = {
  user: api.User | null
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (data: api.SignupData) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    api
      .fetchMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true))
  }, [])

  const value: AuthState = {
    user,
    ready,
    login: async (email, password) => setUser(await api.login(email, password)),
    signup: async (data) => setUser(await api.signup(data)),
    logout: async () => {
      await api.logout().catch(() => undefined)
      setUser(null)
    },
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
