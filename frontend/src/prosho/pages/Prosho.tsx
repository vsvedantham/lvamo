import { Link } from 'react-router-dom'
import BrandedPage from '../../components/BrandedPage'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'

// Phase 0 placeholder (docs/prosho/BETA_PLAN.md §12): sign-in, the project
// dashboard and the public gallery replace this in later phases.
export default function Prosho() {
  useDocumentTitle('ProSho — project showcase | LVAMO')

  return (
    <BrandedPage>
      <div style={{ textAlign: 'center', maxWidth: '560px' }}>
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
          Project Showcase · In development
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

        <p style={{ fontSize: '0.9rem', color: 'var(--text-3)' }}>
          Not open for sign-ups yet.
        </p>

        <p style={{ marginTop: '1.75rem' }}>
          <Link to="/" style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>Back to LVAMO</Link>
        </p>
      </div>
    </BrandedPage>
  )
}
