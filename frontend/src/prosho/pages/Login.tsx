import { Link, Navigate, useSearchParams } from 'react-router-dom'
import BrandedPage from '../../components/BrandedPage'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { githubSignInUrl } from '../api/auth'
import GitHubIcon from '../components/GitHubIcon'
import { useProshoAuth } from '../context/AuthContext'

// Short codes the backend's /auth/github/callback redirects back with.
const ERRORS: Record<string, string> = {
  denied: 'GitHub sign-in was cancelled.',
  not_invited: 'ProSho is in a closed beta. Your GitHub account isn’t on the invite list yet.',
  inactive: 'This ProSho account has been deactivated.',
  failed: 'Something went wrong signing in with GitHub. Please try again.',
}

export default function ProshoLogin() {
  useDocumentTitle('Sign in | ProSho')
  const { user, loading } = useProshoAuth()
  const [params] = useSearchParams()
  const errorCode = params.get('error')
  const error = errorCode ? ERRORS[errorCode] ?? ERRORS.failed : null

  if (loading) return null
  if (user) return <Navigate to="/prosho/dashboard" replace />

  return (
    <BrandedPage>
      <div style={{ width: '100%', maxWidth: '380px' }}>
        <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.35rem' }}>Sign in to ProSho</h1>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>Your project page starts from your GitHub repo.</p>
        </div>

        <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '1.75rem' }}>
          {error && (
            <div role="alert" style={{ padding: '0.7rem 0.875rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
              <p style={{ color: 'var(--danger)', fontSize: '0.825rem', margin: 0 }}>{error}</p>
            </div>
          )}

          <a
            href={githubSignInUrl}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.6rem',
              padding: '0.75rem', background: 'var(--text-1)', color: 'var(--bg)',
              borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.9rem', textDecoration: 'none',
            }}
          >
            <GitHubIcon />
            Continue with GitHub
          </a>

          <p style={{ marginTop: '1.1rem', color: 'var(--text-2)', fontSize: '0.78rem', lineHeight: 1.55 }}>
            We only read your GitHub name, username, avatar and primary email.
            Nothing is posted to GitHub on your behalf.
          </p>
        </div>

        <p style={{ marginTop: '1.25rem', textAlign: 'center' }}>
          <Link to="/prosho" style={{ color: 'var(--text-3)', fontSize: '0.85rem' }}>Back to ProSho</Link>
        </p>
      </div>
    </BrandedPage>
  )
}
