import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import client from '../api/client'
import { apiErrorMessage } from '../api/errors'
import EmailCodeStep from '../../components/EmailCodeStep'
import { useEmailCodesEnabled } from '../../hooks/useEmailCodesEnabled'
import { PlatformApiError, sendEmailCode } from '../../api/platform'

const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '0.375rem' }
const labelStyle: React.CSSProperties = { fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-2)' }

export default function Register() {
  const { register, user, loading: checking } = useAuth()
  const submitted = useRef(false)  // this form signed them up: it goes on to onboarding itself
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [registrationOpen, setRegistrationOpen] = useState<boolean | null>(null)
  // Emailed code before the account is made, while the platform setting
  // `otp_verification_enabled` lists applaut. null = not at that step.
  const codesOn = useEmailCodesEnabled('applaut')
  const [codeStep, setCodeStep] = useState<{ resendAfter: number } | null>(null)

  useEffect(() => {
    client
      .get('/settings/allow_new_registrations')
      .then(res => setRegistrationOpen(res.data.value === '1'))
      .catch(() => setRegistrationOpen(false))
  }, [])

  const createAccount = async (code?: string) => {
    submitted.current = true
    try {
      await register(name, email.trim(), password, code)
      navigate('/applaut/onboarding')
    } catch (err) {
      submitted.current = false
      throw err
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!registrationOpen || codesOn === null) return
    setError('')
    setLoading(true)
    try {
      if (codesOn) {
        const sent = await sendEmailCode('applaut', email.trim(), 'register')
        setCodeStep({ resendAfter: sent.resend_after_seconds })
      } else {
        await createAccount()
      }
    } catch (err) {
      setError(err instanceof PlatformApiError ? err.message : apiErrorMessage(err, 'Registration failed. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  if (checking) return null  // still checking a saved login
  if (user && !submitted.current) return <Navigate to="/applaut/dashboard" replace />  // signed in already

  return (
    <div style={{ width: '100%', maxWidth: '380px' }}>
      <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.35rem' }}>{codeStep ? 'Check your email' : 'Create account'}</h1>
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>{codeStep ? 'One last step to confirm your email' : 'Start automating your job search'}</p>
      </div>

      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '1.75rem' }}>
        {registrationOpen === false && (
          <div style={{ padding: '0.75rem 0.875rem', background: 'var(--bg-elevated)', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
            <p style={{ color: 'var(--text-2)', fontSize: '0.825rem', margin: 0 }}>
              Registration is currently invite-only while we finish building. Check back soon.
            </p>
          </div>
        )}

        {codeStep ? (
          <EmailCodeStep
            vertical="applaut"
            purpose="register"
            email={email.trim()}
            resendAfterSeconds={codeStep.resendAfter}
            submitLabel="Create account"
            busyLabel="Creating account…"
            onSubmit={code => createAccount(code)}
            errorMessage={err => apiErrorMessage(err, 'Registration failed. Please try again.')}
            onBack={() => setCodeStep(null)}
            backLabel="Back"
          />
        ) : (<>
        {error && (
          <div style={{ padding: '0.7rem 0.875rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
            <p style={{ color: 'var(--danger)', fontSize: '0.825rem', margin: 0 }}>{error}</p>
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          style={{ display: 'flex', flexDirection: 'column', gap: '1rem', opacity: registrationOpen ? 1 : 0.4, pointerEvents: registrationOpen ? 'auto' : 'none' }}
        >
          <div style={field}>
            <label style={labelStyle}>Full name</label>
            <input type="text" value={name} onChange={e => setName(e.target.value)} required placeholder="Ada Lovelace" />
          </div>
          <div style={field}>
            <label style={labelStyle}>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" autoComplete="email" />
          </div>
          <div style={field}>
            <label style={labelStyle}>
              Password{' '}
              <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(min. 8 characters)</span>
            </label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} placeholder="••••••••" autoComplete="new-password" />
          </div>
          <button
            type={registrationOpen ? 'submit' : 'button'}
            disabled={loading || !registrationOpen || codesOn === null}
            style={{
              marginTop: '0.25rem',
              padding: '0.625rem',
              background: registrationOpen ? 'var(--accent)' : 'var(--bg-elevated)',
              color: registrationOpen ? '#fff' : 'var(--text-3)',
              border: 'none',
              borderRadius: 'var(--radius-xs)',
              fontWeight: 600,
              fontSize: '0.9rem',
              opacity: loading ? 0.7 : 1,
              cursor: registrationOpen ? 'pointer' : 'not-allowed',
            }}
          >
            {loading ? (codesOn ? 'Sending code…' : 'Creating account…') : registrationOpen ? (codesOn ? 'Continue' : 'Create account') : 'Registration closed'}
          </button>
        </form>
        </>)}
      </div>

      <p style={{ marginTop: '1.25rem', textAlign: 'center', color: 'var(--text-2)', fontSize: '0.85rem' }}>
        Already have an account?{' '}
        <Link to="/applaut/login" style={{ color: 'var(--accent)', fontWeight: 500 }}>Sign in</Link>
      </p>
    </div>
  )
}
