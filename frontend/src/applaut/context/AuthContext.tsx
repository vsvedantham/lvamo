import { createContext, useContext, useEffect, useState } from 'react'
import { TOKEN_KEY } from '../api/client'
import {
  getMe,
  login as apiLogin,
  register as apiRegister,
  type User,
} from '../api/auth'

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string, emailCode?: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      setLoading(false)
      return
    }
    getMe()
      .then(setUser)
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const { access_token } = await apiLogin(email, password)
    localStorage.setItem(TOKEN_KEY, access_token)
    const me = await getMe()
    setUser(me)
  }

  const register = async (name: string, email: string, password: string, emailCode?: string) => {
    const { access_token } = await apiRegister(name, email, password, emailCode)
    localStorage.setItem(TOKEN_KEY, access_token)
    const me = await getMe()
    setUser(me)
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
