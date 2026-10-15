import type { CSSProperties, ReactNode } from 'react'
import type { Visibility } from '../api/projects'

export const labelStyle: CSSProperties = { fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-2)' }
export const hintStyle: CSSProperties = { fontSize: '0.75rem', color: 'var(--text-3)', lineHeight: 1.5 }

export function Card({ title, children, aside }: { title?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '1.5rem', marginBottom: '1.25rem' }}>
      {(title || aside) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem', marginBottom: '1.1rem', flexWrap: 'wrap' }}>
          {title && <h2 style={{ fontSize: '1rem', fontWeight: 700 }}>{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
      <span style={labelStyle}>{label}</span>
      {children}
      {hint && <span style={hintStyle}>{hint}</span>}
    </label>
  )
}

export function Button({ children, disabled, variant = 'primary', type = 'button', onClick }: {
  children: ReactNode
  disabled?: boolean
  variant?: 'primary' | 'secondary'
  type?: 'button' | 'submit'
  onClick?: () => void
}) {
  const primary = variant === 'primary'
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      style={{
        padding: '0.6rem 1.1rem', borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.875rem',
        background: primary ? 'var(--accent)' : 'transparent', color: primary ? '#fff' : 'var(--text-1)',
        border: primary ? 'none' : '1px solid var(--border-strong)',
        opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {children}
    </button>
  )
}

export function Banner({ kind, children }: { kind: 'error' | 'success' | 'info'; children: ReactNode }) {
  const c = {
    error: ['var(--danger-bg)', 'var(--danger-border)', 'var(--danger)'],
    success: ['var(--success-bg)', 'var(--success-border)', 'var(--success)'],
    info: ['var(--accent-glow)', 'var(--accent-border)', 'var(--text-1)'],
  }[kind]
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} style={{ padding: '0.7rem 0.875rem', background: c[0], border: `1px solid ${c[1]}`, borderRadius: 'var(--radius-xs)', marginBottom: '1rem' }}>
      <p style={{ color: c[2], fontSize: '0.825rem', margin: 0, lineHeight: 1.5 }}>{children}</p>
    </div>
  )
}

const VISIBILITY_STYLE: Record<Visibility, [string, string, string]> = {
  private: ['transparent', 'var(--border-strong)', 'var(--text-2)'],
  unlisted: ['var(--blue-bg)', 'var(--blue-border)', 'var(--blue)'],
  public: ['var(--success-bg)', 'var(--success-border)', 'var(--success)'],
}

export function VisibilityPill({ visibility }: { visibility: Visibility }) {
  const [bg, border, color] = VISIBILITY_STYLE[visibility]
  return (
    <span style={{ padding: '0.15rem 0.55rem', borderRadius: '999px', fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', background: bg, border: `1px solid ${border}`, color }}>
      {visibility}
    </span>
  )
}

export const publicPagePath = (slug: string) => `/prosho/${slug}`
export const publicPageUrl = (slug: string) => `lvamo.com/prosho/${slug}`
