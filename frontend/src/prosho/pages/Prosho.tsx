import { Link, useSearchParams } from 'react-router-dom'
import BrandedPage from '../../components/BrandedPage'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { Banner } from '../components/ui'

// Closed-beta landing: what ProSho is, sign-in, and the guide and privacy
// notice a pilot student needs before starting. A gallery comes later.
export default function Prosho() {
  useDocumentTitle('ProSho — project showcase | LVAMO')
  const [params] = useSearchParams()

  return (
    <BrandedPage>
      <div style={{ textAlign: 'center', maxWidth: '560px' }}>
        {params.get('deleted') && <div style={{ textAlign: 'left' }}><Banner kind="success">Your account and projects have been deleted.</Banner></div>}
        <div style={{
          display: 'inline-block',
          padding: '0.3rem 0.8rem',
          background: 'var(--warn-bg)',
          border: '1px solid var(--warn-border)',
          borderRadius: '999px',
          fontSize: '0.75rem',
          fontWeight: 500,
          color: 'var(--warn)',
          letterSpacing: '0.04em',
          marginBottom: '1.75rem',
        }}>
          Project Showcase · Closed beta
        </div>

        <h1 style={{
          fontSize: 'clamp(2.25rem, 5vw, 3.25rem)',
          fontWeight: 700,
          lineHeight: 1.1,
          marginBottom: '1.25rem',
          color: 'var(--text-1)',
        }}>
          Show the work, not just the slides.
        </h1>

        <p style={{ fontSize: '1.0625rem', color: 'var(--text-2)', lineHeight: 1.65, maxWidth: '440px', margin: '0 auto 2.25rem' }}>
          ProSho turns a capstone project&apos;s repository into a page that
          backs up what it claims — the problem, the targets, live evidence
          and how the work came together over time.
        </p>

        <Link
          to="/prosho/login"
          style={{
            display: 'inline-block', padding: '0.7rem 1.75rem', background: 'var(--accent)', color: '#fff',
            borderRadius: 'var(--radius-sm)', fontWeight: 600, fontSize: '0.9rem', textDecoration: 'none',
          }}
        >
          Sign in with GitHub
        </Link>
        <p style={{ marginTop: '0.9rem', fontSize: '0.82rem', color: 'var(--text-3)' }}>
          Closed beta — invited students only for now.
        </p>

        <p style={{ marginTop: '1.75rem', display: 'flex', gap: '1.25rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link to="/prosho/help" style={{ color: 'var(--accent)', fontSize: '0.85rem' }}>Set up in 15 minutes</Link>
          <Link to="/prosho/privacy" style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>Privacy</Link>
          <Link to="/" style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>Back to LVAMO</Link>
        </p>
      </div>
    </BrandedPage>
  )
}
