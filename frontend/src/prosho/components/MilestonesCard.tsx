import { type FormEvent, useEffect, useState } from 'react'
import { apiErrorMessage, type Project } from '../api/projects'
import {
  createMilestone, deleteMilestone, formatDay, listMilestones, updateMilestone,
  type Milestone, type MilestoneUpdate,
} from '../api/team'
import { Banner, Button, Card, hintStyle } from './ui'

// Owner: plan, edit, complete, delete. Mentor: mark completed ones reviewed.
// The public page shows title, due date, done and "reviewed" — never who
// reviewed or what they said.
export default function MilestonesCard({ project }: { project: Project }) {
  const [items, setItems] = useState<Milestone[] | null>(null)
  const [error, setError] = useState('')
  const isOwner = project.access === 'owner'

  useEffect(() => {
    listMilestones(project.id).then(setItems).catch(err => setError(apiErrorMessage(err)))
  }, [project.id])

  const run = async (fn: () => Promise<unknown>) => {
    setError('')
    try {
      await fn()
      setItems(await listMilestones(project.id))
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  if (!items) return null
  if (!isOwner && items.length === 0) {
    return <Card title="Milestones"><p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>The student hasn&apos;t added any milestones yet.</p></Card>
  }

  return (
    <Card title="Milestones" aside={<span style={hintStyle}>Shown on the page</span>}>
      {error && <Banner kind="error">{error}</Banner>}
      {items.length === 0 && (
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', marginBottom: '1rem', lineHeight: 1.6 }}>
          Break the project into steps with dates. Visitors see your progress; your mentor can review each step you complete.
        </p>
      )}
      <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {items.map(m => (
          <MilestoneRow key={m.id} m={m} isOwner={isOwner}
            onUpdate={body => run(() => updateMilestone(project.id, m.id, body))}
            onDelete={() => run(() => deleteMilestone(project.id, m.id))} />
        ))}
      </ol>
      {isOwner && <AddMilestone onAdd={(title, due) => run(() => createMilestone(project.id, { title, due_on: due || null }))} />}
    </Card>
  )
}

function MilestoneRow({ m, isOwner, onUpdate, onDelete }: {
  m: Milestone
  isOwner: boolean
  onUpdate: (body: MilestoneUpdate) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(m.title)
  const [due, setDue] = useState(m.due_on ?? '')
  const done = m.completed_at !== null
  const overdue = !done && m.due_on !== null && m.due_on < new Date().toISOString().slice(0, 10)

  const save = async (e: FormEvent) => {
    e.preventDefault()
    const body: MilestoneUpdate = {}
    if (title.trim() !== m.title) body.title = title.trim()
    if ((due || null) !== m.due_on) body.due_on = due || null
    if (Object.keys(body).length) await onUpdate(body)
    setEditing(false)
  }

  if (editing) {
    return (
      <li style={{ padding: '0.75rem 0.9rem', border: '1px solid var(--accent-border)', borderRadius: 'var(--radius-xs)' }}>
        <form onSubmit={save} style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input value={title} onChange={e => setTitle(e.target.value)} maxLength={200} aria-label="Milestone title" style={{ flex: '1 1 220px' }} />
          <input type="date" value={due} onChange={e => setDue(e.target.value)} aria-label="Due date" style={{ width: 'auto' }} />
          <Button type="submit" disabled={!title.trim()}>Save</Button>
          <Button variant="secondary" onClick={() => { setEditing(false); setTitle(m.title); setDue(m.due_on ?? '') }}>Cancel</Button>
        </form>
        {m.reviewed_at && title.trim() !== m.title && <p style={{ ...hintStyle, marginTop: '0.4rem' }}>Renaming takes away the mentor&apos;s review.</p>}
      </li>
    )
  }

  return (
    <li style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', padding: '0.75rem 0.9rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)' }}>
      {isOwner ? (
        <input type="checkbox" checked={done} onChange={() => onUpdate({ completed: !done })} aria-label={`Mark "${m.title}" ${done ? 'not done' : 'done'}`} />
      ) : (
        <span aria-hidden="true" style={{ width: '1rem', textAlign: 'center', color: done ? 'var(--success)' : 'var(--text-3)' }}>{done ? '✓' : '○'}</span>
      )}
      <div style={{ flex: '1 1 200px', minWidth: 0 }}>
        <p style={{ fontSize: '0.9rem', overflowWrap: 'anywhere', textDecoration: done ? 'line-through' : 'none', color: done ? 'var(--text-2)' : 'var(--text-1)' }}>{m.title}</p>
        <p style={{ ...hintStyle, marginTop: '0.15rem' }}>
          {m.due_on ? <span style={overdue ? { color: 'var(--warn)' } : undefined}>Due {formatDay(m.due_on)}{overdue ? ' · overdue' : ''}</span> : 'No date'}
          {done && <> · done {formatDay(m.completed_at!.slice(0, 10))}</>}
          {m.reviewed_at && <> · <span style={{ color: 'var(--success)' }}>reviewed{m.reviewed_by ? ` by @${m.reviewed_by.github_login}` : ''}</span></>}
        </p>
      </div>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        {isOwner ? (
          <>
            <SmallButton onClick={() => setEditing(true)}>Edit</SmallButton>
            <SmallButton onClick={() => { if (window.confirm(`Delete "${m.title}"?`)) onDelete() }}>Delete</SmallButton>
          </>
        ) : done ? (
          <SmallButton onClick={() => onUpdate({ reviewed: !m.reviewed_at })}>{m.reviewed_at ? 'Undo review' : 'Mark reviewed'}</SmallButton>
        ) : null}
      </div>
    </li>
  )
}

function AddMilestone({ onAdd }: { onAdd: (title: string, due: string) => Promise<void> }) {
  const [title, setTitle] = useState('')
  const [due, setDue] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    await onAdd(title.trim(), due)
    setBusy(false)
    setTitle(''); setDue('')
  }
  return (
    <form onSubmit={submit} style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', marginTop: '1rem' }}>
      <input value={title} onChange={e => setTitle(e.target.value)} maxLength={200} placeholder="New milestone, e.g. Data pipeline for 5 countries" aria-label="New milestone" style={{ flex: '1 1 260px' }} />
      <input type="date" value={due} onChange={e => setDue(e.target.value)} aria-label="Due date (optional)" style={{ width: 'auto' }} />
      <Button type="submit" disabled={!title.trim() || busy}>{busy ? 'Adding…' : 'Add'}</Button>
    </form>
  )
}

export function SmallButton({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} style={{
      padding: '0.3rem 0.65rem', background: 'transparent', color: 'var(--text-2)', border: '1px solid var(--border-strong)',
      borderRadius: 'var(--radius-xs)', fontSize: '0.78rem', cursor: disabled ? 'not-allowed' : 'pointer', whiteSpace: 'nowrap', opacity: disabled ? 0.5 : 1,
    }}>
      {children}
    </button>
  )
}
