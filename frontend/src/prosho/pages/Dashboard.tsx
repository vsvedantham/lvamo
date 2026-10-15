import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { apiErrorMessage, listProjects, PROJECT_TYPE_LABEL, type Project } from '../api/projects'
import ProshoShell from '../components/ProshoShell'
import { Banner, publicPageUrl, VisibilityPill } from '../components/ui'

export default function ProshoDashboard() {
  useDocumentTitle('Your projects | ProSho')
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    listProjects().then(setProjects).catch(err => setError(apiErrorMessage(err)))
  }, [])

  return (
    <ProshoShell>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Your projects</h1>
        <Link to="/prosho/projects/new" style={{ padding: '0.6rem 1.1rem', background: 'var(--accent)', color: '#fff', borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.875rem', textDecoration: 'none' }}>
          New project
        </Link>
      </div>

      {error && <Banner kind="error">{error}</Banner>}
      {projects === null && !error && <p style={{ color: 'var(--text-2)' }}>Loading…</p>}
      {projects?.length === 0 && (
        <div style={{ padding: '2.5rem 1.5rem', textAlign: 'center', border: '1px dashed var(--border-strong)', borderRadius: 'var(--radius)' }}>
          <p style={{ color: 'var(--text-1)', fontWeight: 600, marginBottom: '0.4rem' }}>No projects yet</p>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>Create one, then connect its GitHub repo to build the page.</p>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
        {projects?.map(p => (
          <Link key={p.id} to={`/prosho/projects/${p.id}`} style={{ display: 'block', padding: '1.25rem', background: 'var(--bg-surface)', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius)', textDecoration: 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '0.6rem' }}>
              <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-1)', overflowWrap: 'anywhere' }}>{p.title}</h2>
              <VisibilityPill visibility={p.visibility} />
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--accent)', marginBottom: '0.6rem', overflowWrap: 'anywhere' }}>{publicPageUrl(p.slug)}</p>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-2)' }}>
              {PROJECT_TYPE_LABEL[p.project_type]} · {p.repo_full_name ? p.repo_full_name : 'No repo connected'}
            </p>
          </Link>
        ))}
      </div>
    </ProshoShell>
  )
}
