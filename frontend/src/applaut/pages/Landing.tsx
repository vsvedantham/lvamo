import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'

export default function Landing() {
  useDocumentTitle('Applaut — by LVAMO')
  const { user, loading } = useAuth()
  if (loading) return null  // still checking a saved login
  if (user) return <Navigate to="/applaut/dashboard" replace />  // signed in already
  return (
    <div style={{ textAlign: 'center', maxWidth: '560px' }}>
      <div style={{
        display: 'inline-block',
        padding: '0.3rem 0.8rem',
        background: 'var(--accent-glow)',
        border: '1px solid var(--accent-border)',
        borderRadius: '999px',
        fontSize: '0.75rem',
        fontWeight: 500,
        color: 'var(--accent)',
        letterSpacing: '0.04em',
        marginBottom: '1.75rem',
      }}>
        AI-powered job automation
      </div>

      <h1 style={{
        fontSize: 'clamp(2.25rem, 5vw, 3.25rem)',
        fontWeight: 700,
        lineHeight: 1.1,
        marginBottom: '1.25rem',
        background: 'linear-gradient(135deg, var(--text-1) 0%, var(--accent) 100%)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        backgroundClip: 'text',
      }}>
        Apply smarter.<br />Get hired faster.
      </h1>

      <p style={{ fontSize: '1.0625rem', color: 'var(--text-2)', lineHeight: 1.65, marginBottom: '2.25rem', maxWidth: '420px', margin: '0 auto 2.25rem' }}>
        Applaut discovers jobs, scores them against your profile, and generates tailored applications — reducing hours of effort to 10 minutes a day.
      </p>

      <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', flexWrap: 'wrap' }}>
        <Link
          to="/applaut/register"
          style={{
            padding: '0.7rem 1.75rem',
            background: 'var(--accent)',
            color: '#fff',
            borderRadius: 'var(--radius-sm)',
            fontWeight: 600,
            fontSize: '0.9rem',
            textDecoration: 'none',
            transition: 'opacity 0.15s',
          }}
          onMouseEnter={e => e.currentTarget.style.opacity = '0.88'}
          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
        >
          Get started
        </Link>
        <Link
          to="/applaut/login"
          style={{
            padding: '0.7rem 1.75rem',
            background: 'transparent',
            color: 'var(--text-1)',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-sm)',
            fontWeight: 500,
            fontSize: '0.9rem',
            textDecoration: 'none',
            transition: 'border-color 0.15s, color 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--text-2)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-strong)' }}
        >
          Log in
        </Link>
      </div>

      <div style={{ marginTop: '4rem', display: 'flex', justifyContent: 'center', gap: '2.5rem', flexWrap: 'wrap' }}>
        {[
          { value: '4+', label: 'Job boards' },
          { value: '0–100', label: 'Match score' },
          { value: '< 10 min', label: 'Per day' },
        ].map(stat => (
          <div key={stat.label} style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-1)', lineHeight: 1 }}>{stat.value}</p>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginTop: '0.3rem' }}>{stat.label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
