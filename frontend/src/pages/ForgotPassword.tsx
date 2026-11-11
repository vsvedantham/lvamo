import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import BrandedPage from '../components/BrandedPage'
import EmailCodeStep from '../components/EmailCodeStep'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useEmailCodesEnabled } from '../hooks/useEmailCodesEnabled'
import { resetPassword, sendEmailCode } from '../api/platform'

/**
 * Password reset by emailed code, for any vertical with passwords (today
 * Applaut and Jobref). Shown only while `otp_verification_enabled` lists the
 * vertical. `branded` wraps it in the LVAMO shell for verticals whose public
 * pages don't have their own layout.
 */
interface Props {
  vertical: string
  productName: string
  loginPath: string
  branded?: boolean
}

const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '0.375rem' }
const labelStyle: React.CSSProperties = { fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-2)' }
const panel: React.CSSProperties = { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '1.75rem' }

type Step = 'email' | 'code' | 'done'

export default function ForgotPassword({ vertical, productName, loginPath, branded = false }: Props) {
  useDocumentTitle(`Reset password | ${productName}`)
  const enabled = useEmailCodesEnabled(vertical)
  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [resendAfter, setResendAfter] = useState(60)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const ask = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const sent = await sendEmailCode(vertical, email.trim(), 'reset_password')
      setResendAfter(sent.resend_after_seconds)
      setStep('code')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send the code.')
    } finally {
      setBusy(false)
    }
  }

  const heading = step === 'done' ? 'Password changed' : 'Reset your password'
  const sub = step === 'email'
    ? `Enter the email of your ${productName} account and we'll send you a code.`
    : step === 'code' ? 'Enter the code and choose a new password.' : 'You can sign in with your new password now.'

  let body
  if (enabled === null) {
    body = null
  } else if (!enabled) {
    body = (
      <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.5 }}>
        Password reset by email isn't available for {productName} right now. Please contact help@lvamo.com.
      </p>
    )
  } else if (step === 'email') {
    body = (
      <form onSubmit={ask} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {error && (
          <div role="alert" style={{ padding: '0.7rem 0.875rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)' }}>
            <p style={{ color: 'var(--danger)', fontSize: '0.825rem', margin: 0 }}>{error}</p>
          </div>
        )}
        <div style={field}>
          <label htmlFor="reset-email" style={labelStyle}>Email</label>
          <input id="reset-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" autoComplete="email" autoFocus />
        </div>
        <button
          type="submit"
          disabled={busy || !email.trim()}
          style={{ marginTop: '0.25rem', padding: '0.625rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.9rem', opacity: busy || !email.trim() ? 0.5 : 1 }}
        >
          {busy ? 'Sending…' : 'Send code'}
        </button>
      </form>
    )
  } else if (step === 'code') {
    body = (
      <>
        <p style={{ margin: '0 0 1rem', fontSize: '0.8rem', color: 'var(--text-3)' }}>
          If there's no {productName} account for this email, no code is sent.
        </p>
        <EmailCodeStep
          vertical={vertical}
          purpose="reset_password"
          email={email.trim()}
          resendAfterSeconds={resendAfter}
          submitLabel="Set new password"
          busyLabel="Saving…"
          canSubmit={password.length >= 8}
          onSubmit={async code => {
            await resetPassword(vertical, email.trim(), code, password)
            setStep('done')
          }}
          errorMessage={err => (err instanceof Error ? err.message : 'Could not reset the password.')}
          onBack={() => { setStep('email'); setError('') }}
        >
          <div style={field}>
            <label htmlFor="new-password" style={labelStyle}>
              New password <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(min. 8 characters)</span>
            </label>
            <input id="new-password" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} placeholder="••••••••" autoComplete="new-password" />
          </div>
        </EmailCodeStep>
      </>
    )
  } else {
    body = (
      <Link to={loginPath} style={{ display: 'block', textAlign: 'center', padding: '0.625rem', background: 'var(--accent)', color: '#fff', borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.9rem' }}>
        Sign in
      </Link>
    )
  }

  const content = (
    <div style={{ width: '100%', maxWidth: '380px' }}>
      <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.35rem' }}>{heading}</h1>
        {enabled && <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>{sub}</p>}
      </div>
      <div style={panel}>{body}</div>
      {step !== 'done' && (
        <p style={{ marginTop: '1.25rem', textAlign: 'center', color: 'var(--text-2)', fontSize: '0.85rem' }}>
          Remembered it?{' '}
          <Link to={loginPath} style={{ color: 'var(--accent)', fontWeight: 500 }}>Sign in</Link>
        </p>
      )}
    </div>
  )
  return branded ? <BrandedPage>{content}</BrandedPage> : content
}
