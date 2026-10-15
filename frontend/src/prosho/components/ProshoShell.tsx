import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../../components/Logo'
import { useProshoAuth } from '../context/AuthContext'

// Signed-in page frame: LVAMO/ProSho mark on the left, the user and sign-out
// on the right, content in a centred column below.
export default function ProshoShell({ children }: { children: ReactNode }) {
  const { user, logout } = useProshoAuth()

  return (
    <div style={{ minHeight: '100vh' }}>
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem',
        padding: '1rem 1.25rem', borderBottom: '1px solid var(--border)',
      }}>
        <Link to="/prosho/dashboard" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', textDecoration: 'none' }}>
          <Logo />
          <span style={{ fontWeight: 700, color: 'var(--text-1)' }}>ProSho</span>
        </Link>
        {user && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
            {user.avatar_url && (
              <img src={user.avatar_url} alt="" width={28} height={28} style={{ borderRadius: '50%' }} />
            )}
            <span style={{ fontSize: '0.85rem', color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              @{user.github_login}
            </span>
            <button
              onClick={logout}
              style={{
                padding: '0.4rem 0.75rem', background: 'transparent', color: 'var(--text-2)',
                border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-xs)', fontSize: '0.8rem', cursor: 'pointer', whiteSpace: 'nowrap',
              }}
            >
              Sign out
            </button>
          </div>
        )}
      </header>
      <main style={{ maxWidth: '960px', margin: '0 auto', padding: '2rem 1.25rem 4rem' }}>
        {children}
      </main>
    </div>
  )
}
