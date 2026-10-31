import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { deleteAccount, GITHUB_INSTALLATIONS_URL } from '../api/auth'
import { apiErrorMessage, listProjects, PROJECT_TYPE_LABEL, type Project } from '../api/projects'
import DeleteCard from '../components/DeleteCard'
import ProshoShell from '../components/ProshoShell'
import { Banner, publicPageUrl, VisibilityPill } from '../components/ui'
import { useProshoAuth } from '../context/AuthContext'

export default function ProshoDashboard() {
  useDocumentTitle('Your projects | ProSho')
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    listProjects().then(setProjects).catch(err => setError(apiErrorMessage(err)))
  }, [])

  const owned = projects?.filter(p => p.access === 'owner') ?? []
  const mentored = projects?.filter(p => p.access === 'mentor') ?? []

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
      {projects !== null && owned.length === 0 && (
        <div style={{ padding: '2.5rem 1.5rem', textAlign: 'center', border: '1px dashed var(--border-strong)', borderRadius: 'var(--radius)' }}>
          <p style={{ color: 'var(--text-1)', fontWeight: 600, marginBottom: '0.4rem' }}>No projects yet</p>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>Create one, then connect its GitHub repo to build the page.</p>
        </div>
      )}
      <ProjectGrid projects={owned} />

      {mentored.length > 0 && (
        <>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, margin: '2.5rem 0 1rem' }}>Projects you mentor</h2>
          <ProjectGrid projects={mentored} />
        </>
      )}

      {projects !== null && <div style={{ marginTop: '3rem' }}><AccountCard projectCount={owned.length} /></div>}
    </ProshoShell>
  )
}

function AccountCard({ projectCount }: { projectCount: number }) {
  const { user, logout } = useProshoAuth()
  const navigate = useNavigate()
  if (!user) return null
  if (user.role === 'admin') {
    return (
      <p style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>
        Admins can&apos;t delete their own account — ask another admin to change your role first. <Link to="/prosho/privacy" style={{ color: 'var(--text-2)' }}>Privacy</Link>
      </p>
    )
  }
  return (
    <DeleteCard title="Delete your account" confirmWord={user.github_login} action="Delete account"
      onDelete={async () => {
        await deleteAccount(user.github_login)
        logout()
        navigate('/prosho?deleted=1', { replace: true })
      }}>
      <p>
        Removes your ProSho account{projectCount ? <> and your {projectCount === 1 ? 'project' : `${projectCount} projects`} with everything on {projectCount === 1 ? 'it' : 'them'}</> : null}.
        Shared page addresses stay retired. Notes you left on other students&apos; projects stay, signed &ldquo;Former member&rdquo;.
        Nothing on GitHub changes — remove ProSho&apos;s GitHub App in <a href={GITHUB_INSTALLATIONS_URL} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>GitHub settings</a> too.
        {' '}<Link to="/prosho/privacy" style={{ color: 'var(--accent)' }}>How ProSho handles your data</Link>
      </p>
    </DeleteCard>
  )
}

function ProjectGrid({ projects }: { projects: Project[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(280px, 100%), 1fr))', gap: '1rem' }}>
      {projects.map(p => (
        <Link key={p.id} to={`/prosho/projects/${p.id}`} style={{ display: 'block', padding: '1.25rem', background: 'var(--bg-surface)', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius)', textDecoration: 'none' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '0.6rem' }}>
            <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-1)', overflowWrap: 'anywhere' }}>{p.title}</h2>
            <VisibilityPill visibility={p.visibility} />
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--accent)', marginBottom: '0.6rem', overflowWrap: 'anywhere' }}>{publicPageUrl(p.slug)}</p>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-2)' }}>
            {PROJECT_TYPE_LABEL[p.project_type]} · {p.repo_full_name ? p.repo_full_name : 'No repo connected'}
          </p>
          {p.open_feedback > 0 && (
            <p style={{ marginTop: '0.6rem', fontSize: '0.78rem', fontWeight: 600, color: 'var(--blue)' }}>
              {p.open_feedback} open feedback thread{p.open_feedback === 1 ? '' : 's'}
            </p>
          )}
        </Link>
      ))}
    </div>
  )
}
