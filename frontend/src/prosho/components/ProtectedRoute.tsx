import { Navigate } from 'react-router-dom'
import { useProshoAuth } from '../context/AuthContext'

export default function ProshoProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useProshoAuth()
  if (loading) return <div style={{ padding: '2rem' }}>Loading…</div>
  if (!user) return <Navigate to="/prosho/login" replace />
  return <>{children}</>
}
