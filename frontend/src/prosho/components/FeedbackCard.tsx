import { type FormEvent, useEffect, useState } from 'react'
import type { Claim } from '../api/github'
import { timeAgo } from '../api/evidence'
import { apiErrorMessage, type Project } from '../api/projects'
import {
  listFeedback, listMilestones, postFeedback, setFeedbackResolved,
  type FeedbackCreate, type FeedbackMessage, type FeedbackThread, type Milestone,
} from '../api/team'
import { SmallButton } from './MilestonesCard'
import { Banner, Button, Card, hintStyle } from './ui'

// Mentor <-> student threads. Private to the two of them — never on the
// public page (BETA_PLAN §8).
export default function FeedbackCard({ project, claims }: { project: Project; claims: Claim[] }) {
  const [threads, setThreads] = useState<FeedbackThread[] | null>(null)
  const [milestones, setMilestones] = useState<Milestone[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    listFeedback(project.id).then(setThreads).catch(err => setError(apiErrorMessage(err)))
    listMilestones(project.id).then(setMilestones).catch(() => {})
  }, [project.id])

  const run = async (fn: () => Promise<FeedbackThread[]>) => {
    setError('')
    try {
      setThreads(await fn())
      return true
    } catch (err) {
      setError(apiErrorMessage(err))
      return false
    }
  }

  // Nobody to talk to yet, and nothing said: keep the page uncluttered.
  if (!threads || (!project.has_mentor && threads.length === 0)) return null
  const isMentor = project.access === 'mentor'

  return (
    <Card title="Mentor feedback" aside={<span style={hintStyle}>Only you and {isMentor ? 'the student' : 'your mentor'} can see this</span>}>
      {error && <Banner kind="error">{error}</Banner>}
      <NewThread
        isMentor={isMentor}
        milestones={milestones}
        claims={claims}
        onPost={body => run(() => postFeedback(project.id, body))}
      />
      {threads.length === 0 && (
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', marginTop: '1rem' }}>
          {isMentor ? 'No feedback yet.' : 'No feedback yet — your mentor’s notes will appear here. You can also ask them something.'}
        </p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', marginTop: threads.length ? '1.25rem' : 0 }}>
        {threads.map(t => (
          <Thread key={t.id} thread={t}
            onReply={body => run(() => postFeedback(project.id, { body, parent_id: t.id }))}
            onResolve={resolved => run(() => setFeedbackResolved(project.id, t.id, resolved))} />
        ))}
      </div>
    </Card>
  )
}

function NewThread({ isMentor, milestones, claims, onPost }: {
  isMentor: boolean
  milestones: Milestone[]
  claims: Claim[]
  onPost: (body: FeedbackCreate) => Promise<boolean>
}) {
  const [body, setBody] = useState('')
  const [about, setAbout] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    const [kind, id] = about.split(':')
    const ok = await onPost({
      body: body.trim(),
      ...(kind === 'm' ? { milestone_id: id } : kind === 'c' ? { claim_id: id } : {}),
    })
    setBusy(false)
    if (ok) { setBody(''); setAbout('') }
  }

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
      <textarea value={body} onChange={e => setBody(e.target.value)} maxLength={4000} rows={3}
        placeholder={isMentor ? 'Leave feedback for the student…' : 'Ask your mentor something…'} aria-label="New feedback" />
      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {(milestones.length > 0 || claims.length > 0) && (
          <select value={about} onChange={e => setAbout(e.target.value)} aria-label="About" style={{ width: 'auto', maxWidth: '100%' }}>
            <option value="">About the whole project</option>
            {milestones.length > 0 && (
              <optgroup label="Milestone">
                {milestones.map(m => <option key={m.id} value={`m:${m.id}`}>{m.title}</option>)}
              </optgroup>
            )}
            {claims.length > 0 && (
              <optgroup label="Claim">
                {claims.map(c => <option key={c.id} value={`c:${c.id}`}>{c.text}</option>)}
              </optgroup>
            )}
          </select>
        )}
        <Button type="submit" disabled={!body.trim() || busy}>{busy ? 'Posting…' : 'Post'}</Button>
      </div>
    </form>
  )
}

function Message({ m }: { m: FeedbackMessage }) {
  const who = m.author ? (m.author.name ?? `@${m.author.github_login}`) : 'Former member'
  const role = m.author_role === 'mentor' ? 'Mentor' : m.author_role === 'owner' ? 'Student' : null
  return (
    <div>
      <p style={{ fontSize: '0.78rem', color: 'var(--text-2)', marginBottom: '0.2rem' }}>
        <strong style={{ color: 'var(--text-1)', fontWeight: 600 }}>{who}</strong>
        {role && <> · {role}</>} · {timeAgo(m.created_at)}
      </p>
      <p style={{ fontSize: '0.875rem', lineHeight: 1.6, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{m.body}</p>
    </div>
  )
}

function Thread({ thread, onReply, onResolve }: {
  thread: FeedbackThread
  onReply: (body: string) => Promise<boolean>
  onResolve: (resolved: boolean) => Promise<boolean>
}) {
  const [replying, setReplying] = useState(false)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const resolved = thread.resolved_at !== null
  const about = thread.milestone_title ? `Milestone: ${thread.milestone_title}` : thread.claim_text ? `Claim: ${thread.claim_text}` : null

  const send = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    if (await onReply(body.trim())) { setBody(''); setReplying(false) }
    setBusy(false)
  }

  return (
    <article style={{ padding: '0.9rem 1rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', opacity: resolved ? 0.7 : 1 }}>
      {(about || resolved) && (
        <p style={{ ...hintStyle, marginBottom: '0.5rem', overflowWrap: 'anywhere' }}>
          {about}{about && resolved ? ' · ' : ''}{resolved && <span style={{ color: 'var(--success)' }}>✓ Resolved</span>}
        </p>
      )}
      <Message m={thread} />
      {thread.replies.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem', marginTop: '0.75rem', paddingLeft: '0.9rem', borderLeft: '2px solid var(--border-strong)' }}>
          {thread.replies.map(r => <Message key={r.id} m={r} />)}
        </div>
      )}
      {replying ? (
        <form onSubmit={send} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.75rem' }}>
          <textarea value={body} onChange={e => setBody(e.target.value)} maxLength={4000} rows={2} autoFocus aria-label="Reply" placeholder="Reply…" />
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Button type="submit" disabled={!body.trim() || busy}>{busy ? 'Sending…' : 'Reply'}</Button>
            <Button variant="secondary" onClick={() => { setReplying(false); setBody('') }}>Cancel</Button>
          </div>
        </form>
      ) : (
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
          <SmallButton onClick={() => setReplying(true)}>Reply</SmallButton>
          <SmallButton onClick={() => onResolve(!resolved)}>{resolved ? 'Reopen' : 'Mark resolved'}</SmallButton>
        </div>
      )}
    </article>
  )
}
