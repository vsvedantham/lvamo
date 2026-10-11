import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../components/Logo'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

// Which vertical cards show here is driven by the `verticals_enabled` row in
// `platform.settings` (comma-separated, lowercase names) rather than
// hardcoded — lets a vertical be hidden from casual browsing (e.g. kept
// private while still used directly by URL) without a code deploy. This is
// display-only: it never affects whether a vertical's own routes work, only
// whether its card appears here. The hub belongs to LVAMO itself, not any
// vertical, so it reads from the platform API (see CLAUDE.md).
const PLATFORM_API_BASE = (import.meta.env.VITE_PLATFORM_API_BASE_URL ?? 'http://localhost:8000') + '/api/v1/platform'

async function fetchEnabledVerticals(): Promise<string[]> {
  try {
    const res = await fetch(`${PLATFORM_API_BASE}/settings/verticals_enabled`)
    if (!res.ok) throw new Error(`settings fetch failed: ${res.status}`)
    const data: { value: string } = await res.json()
    return data.value.split(',').map(v => v.trim().toLowerCase()).filter(Boolean)
  } catch (err) {
    // Fail closed: if the setting can't be read, show nothing rather than
    // risk exposing a vertical that was deliberately hidden.
    console.error('Failed to load verticals_enabled setting', err)
    return []
  }
}

const IconApplaut = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <path d="M9 15l2 2 4-4" />
  </svg>
)

const IconJobref = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
)

const IconArrow = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
  </svg>
)

type Vertical = {
  to: string
  icon: React.ReactNode
  name: string
  tagline: string
  description: string
  status: 'live' | 'soon'
}

const verticals: Vertical[] = [
  {
    to: '/applaut',
    icon: <IconApplaut />,
    name: 'Applaut',
    tagline: 'Apply smarter, get hired faster',
    description: 'AI discovers jobs, scores them against your profile, and generates tailored resumes and cover letters — automatically.',
    status: 'live',
  },
  {
    to: '/jobref',
    icon: <IconJobref />,
    name: 'Jobref',
    tagline: 'Referrals from people who already work there',
    description: 'Connecting job seekers with employees willing to refer them — because a referral beats a cold application.',
    status: 'live',
  },
]

function VerticalCard({ v }: { v: Vertical }) {
  return (
    <Link
      to={v.to}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        padding: '1.75rem',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius)',
        textAlign: 'left',
        transition: 'border-color 0.2s, transform 0.2s, box-shadow 0.2s',
        position: 'relative',
        overflow: 'hidden',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--accent-border)'
        e.currentTarget.style.transform = 'translateY(-3px)'
        e.currentTarget.style.boxShadow = '0 16px 40px rgba(0,0,0,0.35)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--border-strong)'
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{
          width: '44px',
          height: '44px',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--accent-glow)',
          color: 'var(--accent)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          {v.icon}
        </div>
        <span style={{
          padding: '0.2rem 0.6rem',
          borderRadius: '999px',
          fontSize: '0.68rem',
          fontWeight: 700,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          ...(v.status === 'live'
            ? { background: 'var(--success-bg)', color: 'var(--success)', border: '1px solid var(--success-border)' }
            : { background: 'var(--warn-bg)', color: 'var(--warn)', border: '1px solid var(--warn-border)' }),
        }}>
          {v.status === 'live' ? 'Live' : 'Coming soon'}
        </span>
      </div>

      <div>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-1)', marginBottom: '0.3rem' }}>{v.name}</h2>
        <p style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--accent)', marginBottom: '0.6rem' }}>{v.tagline}</p>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.6 }}>{v.description}</p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-1)', marginTop: 'auto' }}>
        {v.status === 'live' ? `Open ${v.name}` : 'Learn more'}
        <IconArrow />
      </div>
    </Link>
  )
}

export default function Hub() {
  useDocumentTitle('LVAMO — a suite of tools to get you hired')

  // null = not loaded yet; render no cards until then to avoid a flash of a
  // hidden vertical before the setting comes back.
  const [enabled, setEnabled] = useState<string[] | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchEnabledVerticals().then(v => { if (!cancelled) setEnabled(v) })
    return () => { cancelled = true }
  }, [])

  const visibleVerticals = verticals.filter(v => enabled?.includes(v.to.slice(1).toLowerCase()))

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '4rem 1.5rem 3rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '2.25rem' }}>
        <Logo size={34} />
        <span style={{ fontSize: '0.95rem', fontWeight: 700, letterSpacing: '0.14em', color: 'var(--text-1)', textTransform: 'uppercase' }}>LVAMO</span>
      </div>

      <div style={{ textAlign: 'center', maxWidth: '640px', marginBottom: '3.5rem' }}>
        <h1 style={{
          fontSize: 'clamp(2rem, 4.5vw, 2.9rem)',
          fontWeight: 700,
          lineHeight: 1.15,
          marginBottom: '1.1rem',
          background: 'linear-gradient(135deg, var(--text-1) 0%, var(--accent) 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
        }}>
          A suite of tools to get you hired
        </h1>
        <p style={{ fontSize: '1.0625rem', color: 'var(--text-2)', lineHeight: 1.65, maxWidth: '480px', margin: '0 auto' }}>
          One account, multiple ways to work smarter on your job search. Pick where you want to start.
        </p>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '1.25rem',
        width: '100%',
        maxWidth: '760px',
      }}>
        {visibleVerticals.map(v => <VerticalCard key={v.to} v={v} />)}
      </div>

      <p style={{ marginTop: '3.5rem', fontSize: '0.75rem', color: 'var(--text-3)' }}>
        More LVAMO tools are on the way.
      </p>
    </div>
  )
}
