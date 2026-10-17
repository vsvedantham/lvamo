import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage, syncRoutineNow, type CardState, type EngineCard } from '../api/jobEngine'

// Everything in the card comes from the user's own routine output, so it is
// rendered as plain text only.

const TONE: Record<CardState, { color: string; border: string; bg: string }> = {
  healthy: { color: 'var(--success)', border: 'var(--success-border)', bg: 'var(--success-bg)' },
  running: { color: 'var(--blue)', border: 'var(--blue-border)', bg: 'var(--blue-bg)' },
  waiting: { color: 'var(--text-2)', border: 'var(--border)', bg: 'transparent' },
  no_run_details: { color: 'var(--text-2)', border: 'var(--border)', bg: 'transparent' },
  setup_incomplete: { color: 'var(--warn)', border: 'var(--warn-border)', bg: 'var(--warn-bg)' },
  problems: { color: 'var(--warn)', border: 'var(--warn-border)', bg: 'var(--warn-bg)' },
  failed: { color: 'var(--danger)', border: 'var(--danger-border)', bg: 'var(--danger-bg)' },
  stopped: { color: 'var(--danger)', border: 'var(--danger-border)', bg: 'var(--danger-bg)' },
  didnt_run: { color: 'var(--danger)', border: 'var(--danger-border)', bg: 'var(--danger-bg)' },
  cant_connect: { color: 'var(--danger)', border: 'var(--danger-border)', bg: 'var(--danger-bg)' },
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const now = new Date()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const sameDay = d.toDateString() === now.toDateString()
  const tomorrow = new Date(now.getTime() + 86400000).toDateString() === d.toDateString()
  const yesterday = new Date(now.getTime() - 86400000).toDateString() === d.toDateString()
  if (sameDay) return `Today ${time}`
  if (tomorrow) return `Tomorrow ${time}`
  if (yesterday) return `Yesterday ${time}`
  return `${d.toLocaleDateString([], { day: 'numeric', month: 'short' })} ${time}`
}

function plural(n: number | null | undefined, word: string): string {
  const v = n ?? 0
  return `${v} ${word}${v === 1 ? '' : 's'}`
}

const row: React.CSSProperties = { display: 'flex', gap: '0.75rem', fontSize: '0.8rem', margin: 0, color: 'var(--text-2)' }
const rowLabel: React.CSSProperties = { width: '5rem', flexShrink: 0, color: 'var(--text-3)', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.06em', paddingTop: '0.1rem' }

export const buttonStyle = (variant: 'primary' | 'ghost' | 'danger' = 'ghost', disabled = false): React.CSSProperties => ({
  padding: '0.4rem 0.875rem',
  background: variant === 'primary' ? 'var(--accent)' : variant === 'danger' ? 'var(--danger-bg)' : 'transparent',
  color: variant === 'primary' ? '#fff' : variant === 'danger' ? 'var(--danger)' : 'var(--text-1)',
  border: `1px solid ${variant === 'primary' ? 'var(--accent)' : variant === 'danger' ? 'var(--danger-border)' : 'var(--border-strong)'}`,
  borderRadius: 'var(--radius-xs)',
  fontSize: '0.8rem',
  fontWeight: 500,
  cursor: disabled ? 'default' : 'pointer',
  opacity: disabled ? 0.55 : 1,
  textDecoration: 'none',
  display: 'inline-block',
})

export default function RoutineEngineCard({ card, onChange, showHistoryLink = true }: {
  card: EngineCard
  onChange?: (card: EngineCard) => void
  showHistoryLink?: boolean
}) {
  const [syncing, setSyncing] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const tone = TONE[card.state]
  const run = card.last_run
  const sync = card.last_sync
  const blockedUntil = card.sync_now_available_at ? new Date(card.sync_now_available_at) : null
  const canSync = card.state !== 'setup_incomplete' && !card.paused && !card.sync_running && !syncing
    && !(blockedUntil && blockedUntil > new Date())

  const syncNow = async () => {
    setSyncing(true)
    setNote(null)
    try {
      const res = await syncRoutineNow()
      setNote(res.message)
      onChange?.(res.card)
    } catch (err) {
      setNote(errorMessage(err, 'Sync failed to start'))
    } finally {
      setSyncing(false)
    }
  }

  let lastRun = 'No runs recorded yet'
  if (run) {
    const start = formatWhen(run.started_at ?? run.expected_at)
    const end = run.finished_at ? ` → ${new Date(run.finished_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''
    const status = run.outcome === 'succeeded' ? 'completed' : run.outcome === 'missed' ? "didn't run" : run.outcome
    const counts = run.run_id ? ` · ${plural(run.jobs_new, 'new job')}, ${plural(run.docs_done, 'document')}` : ''
    lastRun = `${start}${end} · ${status}${counts}`
  } else if (card.state === 'no_run_details') {
    lastRun = 'Not available for your routine version'
  }

  const lastSync = sync
    ? sync.status === 'failed'
      ? `${formatWhen(sync.started_at)} · failed`
      : `${formatWhen(sync.finished_at ?? sync.started_at)} · ${sync.jobs_new} new, ${sync.jobs_updated} updated${sync.docs_copied ? `, ${sync.docs_copied} documents` : ''}${sync.status === 'partial' ? ` · ${sync.problems.length} problem${sync.problems.length === 1 ? '' : 's'}` : ''}`
    : 'Not synced yet'

  const nextRun = card.next_run_at
    ? `${formatWhen(card.next_run_at)} (your routine)${card.next_sync_at ? ` · next sync ${card.next_sync_estimated ? '≈ ' : ''}${formatWhen(card.next_sync_at)}` : ''}`
    : '—'

  return (
    <div style={{ padding: '1rem 1.25rem', background: 'var(--bg-surface)', border: `1px solid ${tone.border}`, borderRadius: 'var(--radius)', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
        <p style={{ margin: 0, fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-1)' }}>Your Claude routine</p>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.15rem 0.6rem', borderRadius: '999px', fontSize: '0.75rem', fontWeight: 600, color: tone.color, background: tone.bg, border: `1px solid ${tone.border}` }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: tone.color }} />
          {card.label}
        </span>
      </div>

      {card.state !== 'healthy' && (
        <p style={{ margin: 0, fontSize: '0.825rem', color: 'var(--text-1)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{card.message}</p>
      )}

      {card.state !== 'setup_incomplete' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
          <p style={row}><span style={rowLabel}>Last run</span><span>{lastRun}</span></p>
          <p style={row}><span style={rowLabel}>Synced</span><span>{lastSync}</span></p>
          <p style={row}><span style={rowLabel}>Next run</span><span>{nextRun}</span></p>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {card.state === 'setup_incomplete' || card.state === 'cant_connect' ? (
          <Link to="/applaut/settings" style={buttonStyle('primary')}>
            {card.state === 'setup_incomplete' ? 'Connect your routine' : 'Update connection'}
          </Link>
        ) : (
          <button onClick={syncNow} disabled={!canSync} style={buttonStyle('primary', !canSync)}
            title={blockedUntil && blockedUntil > new Date() ? `Available again at ${blockedUntil.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : undefined}>
            {syncing || card.sync_running ? 'Syncing…' : 'Sync now'}
          </button>
        )}
        {card.routine_url && (
          <a href={card.routine_url} target="_blank" rel="noopener noreferrer" style={buttonStyle()}>Open routine in Claude</a>
        )}
        {showHistoryLink && card.state !== 'setup_incomplete' && (
          <Link to="/applaut/settings#run-history" style={buttonStyle()}>Run history</Link>
        )}
        {note && <span style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>{note}</span>}
      </div>
    </div>
  )
}
