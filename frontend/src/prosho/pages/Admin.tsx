import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import {
  assignMentor, getAuditLog, listAllProjects, listUsers, removeMentor, setProjectActive, updateUser,
  type AdminProject, type AdminUser, type AuditEntry,
} from '../api/admin'
import type { ProshoRole } from '../api/auth'
import { timeAgo } from '../api/evidence'
import { apiErrorMessage } from '../api/projects'
import { SmallButton } from '../components/MilestonesCard'
import ProshoShell from '../components/ProshoShell'
import { Banner, Card, hintStyle, publicPagePath, VisibilityPill } from '../components/ui'
import { useProshoAuth } from '../context/AuthContext'

// BETA_PLAN §5: assign mentors, deactivate users and projects, read the
// audit log. The backend enforces admin-only; this page just hides itself.
export default function ProshoAdmin() {
  useDocumentTitle('Admin | ProSho')
  const { user } = useProshoAuth()
  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [projects, setProjects] = useState<AdminProject[] | null>(null)
  const [error, setError] = useState('')
  const [auditKey, setAuditKey] = useState(0)

  useEffect(() => {
    if (user?.role !== 'admin') return
    listUsers().then(setUsers).catch(err => setError(apiErrorMessage(err)))
    listAllProjects().then(setProjects).catch(err => setError(apiErrorMessage(err)))
  }, [user?.role])

  if (user && user.role !== 'admin') return <Navigate to="/prosho/dashboard" replace />

  // Every change returns the fresh list; the audit log reloads after it.
  const run = async <T,>(fn: () => Promise<T>, apply: (v: T) => void) => {
    setError('')
    try {
      apply(await fn())
      setAuditKey(k => k + 1)
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  const mentors = (users ?? []).filter(u => u.is_active && (u.role === 'mentor' || u.role === 'admin'))

  return (
    <ProshoShell>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '1.5rem' }}>Admin</h1>
      {error && <Banner kind="error">{error}</Banner>}

      <Card title="Projects" aside={<span style={hintStyle}>{projects?.length ?? '…'} total</span>}>
        {projects?.length === 0 && <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>No projects yet.</p>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {projects?.map(p => (
            <ProjectRow key={p.id} p={p} mentors={mentors}
              onAssign={mid => run(() => assignMentor(p.id, mid), setProjects)}
              onRemove={mid => run(() => removeMentor(p.id, mid), setProjects)}
              onToggleActive={() => run(() => setProjectActive(p.id, !p.is_active), setProjects)} />
          ))}
        </div>
      </Card>

      <Card title="People" aside={<span style={hintStyle}>Mentors and admins can be assigned to projects</span>}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          {users?.map(u => (
            <div key={u.id} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', padding: '0.7rem 0.85rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', opacity: u.is_active ? 1 : 0.6 }}>
              {u.avatar_url && <img src={u.avatar_url} alt="" width={28} height={28} style={{ borderRadius: '50%' }} />}
              <div style={{ flex: '1 1 160px', minWidth: 0 }}>
                <p style={{ fontSize: '0.9rem', fontWeight: 600, overflowWrap: 'anywhere' }}>{u.name ?? `@${u.github_login}`}</p>
                <p style={hintStyle}>@{u.github_login} · {u.projects_owned} project{u.projects_owned === 1 ? '' : 's'} · joined {new Date(u.created_at).toLocaleDateString()}{u.is_active ? '' : ' · deactivated'}</p>
              </div>
              {u.id === user?.id ? (
                <span style={hintStyle}>You ({u.role})</span>
              ) : (
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <select value={u.role} aria-label={`Role of @${u.github_login}`} style={{ width: 'auto' }}
                    onChange={e => run(() => updateUser(u.id, { role: e.target.value as ProshoRole }), setUsers)}>
                    <option value="student">Student</option>
                    <option value="mentor">Mentor</option>
                    <option value="admin">Admin</option>
                  </select>
                  <SmallButton onClick={() => {
                    if (!u.is_active || window.confirm(`Deactivate @${u.github_login}? They're signed out and their pages disappear.`)) {
                      run(() => updateUser(u.id, { is_active: !u.is_active }), setUsers)
                    }
                  }}>{u.is_active ? 'Deactivate' : 'Reactivate'}</SmallButton>
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      <AuditLog key={auditKey} />
    </ProshoShell>
  )
}

function ProjectRow({ p, mentors, onAssign, onRemove, onToggleActive }: {
  p: AdminProject
  mentors: AdminUser[]
  onAssign: (mentorId: string) => void
  onRemove: (mentorId: string) => void
  onToggleActive: () => void
}) {
  const assignable = mentors.filter(m => m.id !== p.owner.id && !p.mentors.some(x => x.id === m.id))
  return (
    <div style={{ padding: '0.85rem 0.95rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', opacity: p.is_active ? 1 : 0.6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <Link to={publicPagePath(p.slug)} style={{ fontWeight: 600, color: 'var(--text-1)', overflowWrap: 'anywhere' }}>{p.title}</Link>
            <VisibilityPill visibility={p.visibility} />
            {!p.is_active && <span style={{ ...hintStyle, color: 'var(--danger)' }}>Deactivated</span>}
          </div>
          <p style={{ ...hintStyle, marginTop: '0.2rem', overflowWrap: 'anywhere' }}>
            by @{p.owner.github_login}{p.repo_full_name ? ` · ${p.repo_full_name}` : ''} · created {new Date(p.created_at).toLocaleDateString()}
          </p>
        </div>
        <SmallButton onClick={() => {
          if (!p.is_active || window.confirm(`Deactivate "${p.title}"? Its page disappears for everyone, including the student.`)) onToggleActive()
        }}>{p.is_active ? 'Deactivate' : 'Reactivate'}</SmallButton>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.7rem' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-2)' }}>Mentors:</span>
        {p.mentors.length === 0 && <span style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>none</span>}
        {p.mentors.map(m => (
          <span key={m.id} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', padding: '0.15rem 0.3rem 0.15rem 0.6rem', borderRadius: '999px', border: '1px solid var(--border-strong)', fontSize: '0.78rem' }}>
            @{m.github_login}
            <button type="button" onClick={() => onRemove(m.id)} aria-label={`Remove @${m.github_login} as mentor`}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-2)', cursor: 'pointer', padding: '0 0.3rem', fontSize: '0.9rem', lineHeight: 1 }}>×</button>
          </span>
        ))}
        {assignable.length > 0 && (
          <select value="" onChange={e => e.target.value && onAssign(e.target.value)} aria-label={`Add a mentor to ${p.title}`} style={{ width: 'auto', fontSize: '0.8rem' }}>
            <option value="">+ Add mentor</option>
            {assignable.map(m => <option key={m.id} value={m.id}>@{m.github_login}</option>)}
          </select>
        )}
      </div>
    </div>
  )
}

function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null)
  const [more, setMore] = useState(true)
  useEffect(() => { getAuditLog().then(e => { setEntries(e); setMore(e.length === 100) }).catch(() => setEntries([])) }, [])

  const loadMore = async () => {
    if (!entries?.length) return
    const older = await getAuditLog(entries[entries.length - 1].created_at)
    setEntries([...entries, ...older])
    setMore(older.length === 100)
  }

  return (
    <Card title="Audit log" aside={<span style={hintStyle}>Every change, newest first</span>}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--text-2)' }}>
              {['When', 'Who', 'What', 'Change'].map(h => <th key={h} style={{ padding: '0.4rem 0.6rem 0.4rem 0', fontWeight: 500 }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {entries?.map(e => (
              <tr key={e.id} style={{ borderTop: '1px solid var(--border)', verticalAlign: 'top' }}>
                <td style={{ padding: '0.45rem 0.6rem 0.45rem 0', whiteSpace: 'nowrap' }} title={new Date(e.created_at).toLocaleString()}>{timeAgo(e.created_at)}</td>
                <td style={{ padding: '0.45rem 0.6rem 0.45rem 0', whiteSpace: 'nowrap' }}>{e.actor_login ? `@${e.actor_login}` : <span style={{ color: 'var(--text-3)' }}>system</span>}</td>
                <td style={{ padding: '0.45rem 0.6rem 0.45rem 0', whiteSpace: 'nowrap' }}><code>{e.action}</code></td>
                <td style={{ padding: '0.45rem 0', color: 'var(--text-2)', minWidth: '220px', overflowWrap: 'anywhere' }}><code style={{ fontSize: '0.72rem' }}>{JSON.stringify(e.after ?? e.before)}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {more && entries && entries.length > 0 && <div style={{ marginTop: '0.75rem' }}><SmallButton onClick={loadMore}>Load older</SmallButton></div>}
    </Card>
  )
}
