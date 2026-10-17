import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Logo from '../../components/Logo'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { describeTarget } from '../api/github'
import { PROJECT_TYPE_LABEL } from '../api/projects'
import { getPublicProject, type PublicClaim, type PublicProject } from '../api/public'
import { formatValue, timeAgo } from '../api/evidence'
import DataModulePanels from '../components/DataModulePanels'
import StatusPill from '../components/StatusPill'

// The public project page (BETA_PLAN §10): the student's work first, LVAMO
// branding kept to the small footer.

const sectionTitle: React.CSSProperties = {
  fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-2)', marginBottom: '0.9rem',
}

function useNoIndex(active: boolean) {
  useEffect(() => {
    if (!active) return
    const meta = document.createElement('meta')
    meta.name = 'robots'
    meta.content = 'noindex, nofollow'
    document.head.appendChild(meta)
    return () => { meta.remove() }
  }, [active])
}

export default function ProshoProjectPage() {
  const { slug = '' } = useParams()
  const [page, setPage] = useState<PublicProject | null>(null)
  const [missing, setMissing] = useState(false)
  useDocumentTitle(page ? `${page.title} | ProSho` : 'ProSho')
  // Only public pages may be indexed; unlisted means "anyone with the link".
  useNoIndex(page?.visibility !== 'public')

  useEffect(() => {
    setPage(null)
    setMissing(false)
    getPublicProject(slug).then(setPage).catch(() => setMissing(true))
  }, [slug])

  if (missing) return <NotFound />
  if (!page) return <div style={{ padding: '2rem', color: 'var(--text-2)' }}>Loading…</div>

  const byline = [page.programme, page.university].filter(Boolean).join(' · ')

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {page.preview && (
        <div role="status" style={{ padding: '0.7rem 1.25rem', background: 'var(--warn-bg)', borderBottom: '1px solid var(--warn-border)', fontSize: '0.85rem', color: 'var(--warn)', textAlign: 'center' }}>
          Preview — this page is private, so only you can see it.{' '}
          <Link to="/prosho/dashboard" style={{ color: 'var(--warn)', textDecoration: 'underline' }}>Change who can see it</Link>
        </div>
      )}

      <main style={{ flex: 1, width: '100%', maxWidth: '860px', margin: '0 auto', padding: '2.5rem 1.25rem 3rem' }}>
        <header style={{ marginBottom: '2.5rem' }}>
          <span style={{ display: 'inline-block', padding: '0.2rem 0.65rem', borderRadius: '999px', fontSize: '0.72rem', fontWeight: 600, background: 'var(--accent-glow)', border: '1px solid var(--accent-border)', color: 'var(--accent)', marginBottom: '1rem' }}>
            {PROJECT_TYPE_LABEL[page.project_type]}
          </span>
          <h1 style={{ fontSize: 'clamp(2rem, 6vw, 2.9rem)', fontWeight: 700, lineHeight: 1.1, marginBottom: '0.75rem', overflowWrap: 'anywhere' }}>{page.title}</h1>
          {page.summary && <p style={{ fontSize: '1.1rem', color: 'var(--text-2)', lineHeight: 1.6, marginBottom: '1.25rem' }}>{page.summary}</p>}
          <a href={`https://github.com/${page.owner.github_login}`} target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.6rem', textDecoration: 'none' }}>
            {page.owner.avatar_url && <img src={page.owner.avatar_url} alt="" width={36} height={36} style={{ borderRadius: '50%' }} />}
            <span>
              <span style={{ display: 'block', fontWeight: 600, color: 'var(--text-1)', fontSize: '0.95rem' }}>{page.owner.name ?? `@${page.owner.github_login}`}</span>
              {byline && <span style={{ display: 'block', color: 'var(--text-2)', fontSize: '0.82rem' }}>{byline}</span>}
            </span>
          </a>
        </header>

        {page.problem && (
          <section style={{ marginBottom: '2.5rem' }}>
            <h2 style={sectionTitle}>The problem</h2>
            <p style={{ fontSize: '1rem', lineHeight: 1.75, color: 'var(--text-1)', whiteSpace: 'pre-line' }}>{page.problem}</p>
          </section>
        )}

        {page.claims.length > 0 && (
          <section style={{ marginBottom: '2.5rem' }}>
            <h2 style={sectionTitle}>Claims</h2>
            <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {page.claims.map((c, i) => <ClaimRow key={c.key} claim={c} n={i + 1} />)}
            </ol>
            <p style={{ marginTop: '0.75rem', fontSize: '0.78rem', color: 'var(--text-3)', lineHeight: 1.5 }}>
              Measured claims get their status from evidence the project reports automatically. Self-reported ones are set by the student.
            </p>
          </section>
        )}

        {page.data_module && <DataModulePanels data={page.data_module} />}

        {page.demo_kind && page.demo_url && <Demo kind={page.demo_kind} url={page.demo_url} />}

        <p style={{ fontSize: '0.78rem', color: 'var(--text-3)' }}>Last updated {new Date(page.updated_at).toLocaleDateString()}</p>
      </main>

      <Footer />
    </div>
  )
}

function ClaimRow({ claim, n }: { claim: PublicClaim; n: number }) {
  return (
    <li style={{ display: 'flex', gap: '0.9rem', alignItems: 'flex-start', padding: '1rem 1.1rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
      <span aria-hidden="true" style={{ flexShrink: 0, width: '1.6rem', height: '1.6rem', borderRadius: '50%', background: 'var(--bg-elevated)', color: 'var(--text-2)', fontSize: '0.8rem', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{n}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: '0.95rem', lineHeight: 1.5, overflowWrap: 'anywhere' }}>{claim.text}</p>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-3)', marginTop: '0.25rem' }}>
          {claim.self_reported ? 'Self-reported' : <>Measured · <code>{claim.metric_key}</code> {describeTarget(claim)}</>}
          {claim.latest_at && <> · latest <strong style={{ color: 'var(--text-2)' }}>{formatValue(claim.latest_value, claim.latest_unit)}</strong> ({timeAgo(claim.latest_at)})</>}
        </p>
      </div>
      <StatusPill status={claim.status} />
    </li>
  )
}

function Demo({ kind, url }: { kind: 'streamlit' | 'url' | 'video'; url: string }) {
  const openLink = (label: string) => (
    <a href={url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', padding: '0.6rem 1.1rem', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-xs)', color: 'var(--text-1)', fontWeight: 600, fontSize: '0.875rem', textDecoration: 'none' }}>
      {label} ↗
    </a>
  )

  let embed: string | null = null
  if (kind === 'streamlit') {
    try {
      const u = new URL(url)
      u.searchParams.set('embed', 'true')
      embed = u.toString()
    } catch { /* invalid URL — fall back to the link only */ }
  }

  return (
    <section style={{ marginBottom: '2.5rem' }}>
      <h2 style={sectionTitle}>Demo</h2>
      {embed && (
        <>
          <div style={{ border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', background: '#fff', marginBottom: '0.75rem' }}>
            <iframe
              src={embed}
              title="Project dashboard"
              loading="lazy"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
              style={{ display: 'block', width: '100%', height: 'min(70vh, 640px)', border: 0 }}
            />
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-3)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
            Free Streamlit apps sleep when nobody&apos;s using them — if it shows a wake-up screen, give it about 30 seconds or open it directly.
          </p>
        </>
      )}
      {openLink(kind === 'video' ? 'Watch the video' : kind === 'streamlit' ? 'Open the dashboard' : 'Open the live site')}
    </section>
  )
}

function Footer() {
  return (
    <footer style={{ borderTop: '1px solid var(--border)', padding: '1.25rem', display: 'flex', justifyContent: 'center' }}>
      <Link to="/" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', color: 'var(--text-3)', fontSize: '0.78rem', textDecoration: 'none' }}>
        <Logo size={16} />
        Built with LVAMO ProSho
      </Link>
    </footer>
  )
}

function NotFound() {
  useDocumentTitle('Page not found | ProSho')
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem 1.25rem', textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>This project page isn&apos;t available</h1>
        <p style={{ color: 'var(--text-2)', fontSize: '0.9rem', maxWidth: '380px', lineHeight: 1.6 }}>
          It may not exist, or its owner hasn&apos;t shared it yet.
        </p>
      </main>
      <Footer />
    </div>
  )
}
