import { type FormEvent, type ReactNode, useEffect, useState } from 'react'
import { type EmailCodePurpose, sendEmailCode } from '../api/platform'

/**
 * The "enter the code we emailed you" step, for any vertical's sign-up or
 * password reset. The caller sends the first code (so it can show errors on
 * its own form, e.g. "Email already registered"); this step offers resends.
 * `children` go between the code box and the button (e.g. a new password).
 */
interface Props {
  vertical: string
  purpose: EmailCodePurpose
  email: string
  resendAfterSeconds: number
  submitLabel: string
  busyLabel: string
  canSubmit?: boolean
  onSubmit: (code: string) => Promise<void>
  errorMessage: (err: unknown) => string
  onBack: () => void
  backLabel?: string
  children?: ReactNode
}

const labelStyle: React.CSSProperties = { fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-2)' }

export default function EmailCodeStep({
  vertical, purpose, email, resendAfterSeconds, submitLabel, busyLabel, canSubmit = true,
  onSubmit, errorMessage, onBack, backLabel = 'Change email', children,
}: Props) {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [wait, setWait] = useState(resendAfterSeconds)

  useEffect(() => {
    if (wait <= 0) return
    const t = setTimeout(() => setWait(w => w - 1), 1000)
    return () => clearTimeout(t)
  }, [wait])

  const ready = /^\d{6}$/.test(code) && canSubmit && !busy

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!ready) return
    setError('')
    setNotice('')
    setBusy(true)
    try {
      await onSubmit(code)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    setError('')
    setNotice('')
    try {
      const sent = await sendEmailCode(vertical, email, purpose)
      setCode('')
      setWait(sent.resend_after_seconds)
      setNotice('A new code is on its way. Only the newest code works.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send a new code.')
    }
  }

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.5 }}>
        We sent a 6-digit code to <strong style={{ color: 'var(--text-1)', wordBreak: 'break-all' }}>{email}</strong>.
        It works for 10 minutes. Check your spam folder if it doesn't arrive.
      </p>

      {error && (
        <div role="alert" style={{ padding: '0.7rem 0.875rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)' }}>
          <p style={{ color: 'var(--danger)', fontSize: '0.825rem', margin: 0 }}>{error}</p>
        </div>
      )}
      {notice && !error && (
        <p role="status" style={{ margin: 0, fontSize: '0.825rem', color: 'var(--text-2)' }}>{notice}</p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
        <label htmlFor="email-code" style={labelStyle}>Code</label>
        <input
          id="email-code"
          value={code}
          onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="123456"
          autoFocus
          required
          style={{ fontSize: '1.25rem', letterSpacing: '0.35em', fontFamily: 'ui-monospace, Menlo, Consolas, monospace', textAlign: 'center' }}
        />
      </div>

      {children}

      <button
        type="submit"
        disabled={!ready}
        style={{
          marginTop: '0.25rem', padding: '0.625rem', background: 'var(--accent)', color: '#fff', border: 'none',
          borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.9rem',
          opacity: ready ? 1 : 0.5, cursor: ready ? 'pointer' : 'not-allowed',
        }}
      >
        {busy ? busyLabel : submitLabel}
      </button>

      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', fontSize: '0.825rem' }}>
        <button type="button" onClick={onBack} style={linkButton}>{backLabel}</button>
        <button type="button" onClick={resend} disabled={wait > 0} style={{ ...linkButton, color: wait > 0 ? 'var(--text-3)' : 'var(--accent)', cursor: wait > 0 ? 'default' : 'pointer' }}>
          {wait > 0 ? `Send a new code in ${wait}s` : 'Send a new code'}
        </button>
      </div>
    </form>
  )
}

const linkButton: React.CSSProperties = {
  background: 'none', border: 'none', padding: 0, color: 'var(--accent)', fontWeight: 500, fontSize: '0.825rem', cursor: 'pointer',
}
