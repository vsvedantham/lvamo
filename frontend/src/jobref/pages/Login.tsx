import { type FormEvent, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import BrandedPage from '../../components/BrandedPage'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { useJobrefAuth } from '../context/AuthContext'
import { useEmailCodesEnabled } from '../../hooks/useEmailCodesEnabled'

const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '0.375rem' }
const labelStyle: React.CSSProperties = { fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-2)' }

export default function JobrefLogin() {
  useDocumentTitle('Sign in | Jobref')
  const { login, user, loading: authLoading } = useJobrefAuth()
  const navigate = useNavigate()
  const canReset = useEmailCodesEnabled('jobref')
  const [params] = useSearchParams()
  const linkedinExisting = params.get('linkedin') === 'existing'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const formValid = email.trim() !== '' && password.trim() !== ''

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/jobref/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Invalid email or password.')
    } finally {
      setLoading(false)
    }
  }

  // An existing session should persist — landing here already logged in
  // shouldn't ask for a password again, it should just continue on.
  if (authLoading) return null
  if (user) return <Navigate to="/jobref/dashboard" replace />

  return (
    <BrandedPage>
      <div style={{ width: '100%', maxWidth: '380px' }}>
        <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.35rem' }}>Welcome back</h1>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>Sign in to Jobref</p>
        </div>

        <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '1.75rem' }}>
          {linkedinExisting && !error && (
            <div style={{ padding: '0.7rem 0.875rem', background: 'var(--accent-glow)', border: '1px solid var(--accent-border)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
              <p style={{ color: 'var(--text-1)', fontSize: '0.825rem', margin: 0 }}>
                You already have an account with this LinkedIn profile — sign in below.
              </p>
            </div>
          )}
          {error && (
            <div style={{ padding: '0.7rem 0.875rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
              <p style={{ color: 'var(--danger)', fontSize: '0.825rem', margin: 0 }}>{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={field}>
              <label style={labelStyle}>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" autoComplete="email" />
            </div>
            <div style={field}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <label style={labelStyle}>Password</label>
                {canReset && (
                  <Link to="/jobref/forgot-password" style={{ color: 'var(--accent)', fontSize: '0.8rem', fontWeight: 500 }}>Forgot password?</Link>
                )}
              </div>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••" autoComplete="current-password" />
            </div>
            <button
              type="submit"
              disabled={loading || !formValid}
              style={{
                marginTop: '0.25rem', padding: '0.625rem', background: 'var(--accent)', color: '#fff',
                border: 'none', borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.9rem',
                opacity: loading || !formValid ? 0.5 : 1,
                cursor: loading || !formValid ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        <p style={{ marginTop: '1.25rem', textAlign: 'center', color: 'var(--text-2)', fontSize: '0.85rem' }}>
          No account?{' '}
          <Link to="/jobref/register" style={{ color: 'var(--accent)', fontWeight: 500 }}>Create one</Link>
        </p>
      </div>
    </BrandedPage>
  )
}
