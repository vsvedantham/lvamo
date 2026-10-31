import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../../components/Logo'

export const PRIVACY_EMAIL = 'privacy@lvamo.com'

// Long-form reading pages (the guide, the privacy notice): ProSho mark,
// a narrow text column, and the same small footer everywhere.
export default function DocPage({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)' }}>
        <Link to="/prosho" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', textDecoration: 'none' }}>
          <Logo />
          <span style={{ fontWeight: 700, color: 'var(--text-1)' }}>ProSho</span>
        </Link>
        <Link to="/prosho/login" style={{ fontSize: '0.85rem', color: 'var(--text-2)' }}>Sign in</Link>
      </header>
      <main style={{ flex: 1, width: '100%', maxWidth: '720px', margin: '0 auto', padding: '2.5rem 1.25rem 4rem' }}>
        {children}
      </main>
      <DocFooter />
    </div>
  )
}

export function DocFooter() {
  const link = { color: 'var(--text-3)', fontSize: '0.8rem' }
  return (
    <footer style={{ borderTop: '1px solid var(--border)', padding: '1.25rem', display: 'flex', justifyContent: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
      <Link to="/prosho/help" style={link}>Setup guide</Link>
      <Link to="/prosho/privacy" style={link}>Privacy</Link>
      <Link to="/" style={link}>LVAMO</Link>
    </footer>
  )
}

export function H2({ id, children }: { id?: string; children: ReactNode }) {
  return <h2 id={id} style={{ fontSize: '1.15rem', fontWeight: 700, margin: '2.25rem 0 0.75rem', scrollMarginTop: '1rem' }}>{children}</h2>
}

export function P({ children }: { children: ReactNode }) {
  return <p style={{ fontSize: '0.925rem', lineHeight: 1.7, color: 'var(--text-2)', marginBottom: '0.75rem' }}>{children}</p>
}

export function List({ children }: { children: ReactNode }) {
  return <ul style={{ fontSize: '0.925rem', lineHeight: 1.7, color: 'var(--text-2)', margin: '0 0 0.75rem', paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>{children}</ul>
}

export const strong = { color: 'var(--text-1)', fontWeight: 600 } as const
