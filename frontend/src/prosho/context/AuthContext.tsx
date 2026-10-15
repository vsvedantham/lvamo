import { createContext, useContext, useEffect, useState } from 'react'
import { TOKEN_KEY, UNAUTHORIZED_EVENT } from '../api/client'
import { exchangeLoginCode, getMe, type ProshoUser } from '../api/auth'

interface AuthContextType {
  user: ProshoUser | null
  loading: boolean
  signInWithCode: (code: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function ProshoAuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<ProshoUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!localStorage.getItem(TOKEN_KEY)) {
      setLoading(false)
      return
    }
    getMe()
      .then(setUser)
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false))
  }, [])

  // An expired token anywhere in the app signs the user out; the protected
  // route then sends them to the login page.
  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  const signInWithCode = async (code: string) => {
    const token = await exchangeLoginCode(code)
    localStorage.setItem(TOKEN_KEY, token)
    setUser(await getMe())
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, signInWithCode, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useProshoAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useProshoAuth must be used inside ProshoAuthProvider')
  return ctx
}
