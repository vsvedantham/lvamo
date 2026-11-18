import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listAiRuns, type AiNight, type AiRunsResponse } from '../api/jobEngine'
import { formatWhen } from './RoutineEngineCard'

// Applaut AI's nightly runs for this user: what each night searched, what fit
// them, and what the AI did with it. Settings shows the list
// (#nightly-runs); Opportunities shows last night in one line.

export const SOURCE_NAMES: Record<string, string> = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  personio: 'Personio',
  smartrecruiters: 'SmartRecruiters',
  bundesagentur: 'Bundesagentur für Arbeit',
  arbeitnow: 'Arbeitnow',
}

const card: React.CSSProperties = {
  padding: '1.25rem', background: 'var(--bg-surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius)', display: 'flex', flexDirection: 'column', gap: '0.875rem',
}
const h2: React.CSSProperties = { fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-1)' }
const muted: React.CSSProperties = { fontSize: '0.8rem', color: 'var(--text-2)', margin: 0 }
const linkButton: React.CSSProperties = {
  alignSelf: 'flex-start', background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: '0.75rem',
}
const SHOWN = 7

/** "Tue 18 Nov" from a YYYY-MM-DD date, without shifting it by the time zone. */
function nightLabel(runDate: string): string {
  const [y, m, d] = runDate.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}

function nightStatus(n: AiNight): { text: string; color: string } {
  if (!n.discovery_done_at) return { text: 'searching', color: 'var(--blue)' }
  if (n.scoring_left || n.docs_left) return { text: 'working', color: 'var(--blue)' }
  if (n.scoring_failed || n.docs_failed) return { text: 'done, with problems', color: 'var(--warn)' }
  return { text: 'done', color: 'var(--success)' }
}

function NightRow({ night: n, threshold }: { night: AiNight; threshold: number }) {
  const [open, setOpen] = useState(false)
  const status = nightStatus(n)
  const funnel = [
    `${n.postings_checked} postings checked`,
    `${n.matched} fit your search`,
    `${n.new} new for you`,
    `${n.scored} scored${n.scoring_left ? `, ${n.scoring_left} still to score` : ''}${n.scoring_failed ? ` (${n.scoring_failed} failed)` : ''}`,
    `${n.good} at ${threshold}%+`,
    `${plural(n.docs_done, 'CV & cover letter', 'CVs & cover letters')}${n.docs_left ? `, ${n.docs_left} being written` : ''}${n.docs_failed ? ` (${n.docs_failed} failed)` : ''}`,
  ].join(' · ')
  const notes = [
    n.waiting > 0 && `${plural(n.waiting, 'job')} over the nightly limit, scored on a later night`,
    n.no_description > 0 && `${plural(n.no_description, 'job')} skipped: the posting has no description`,
    n.closed !== null && n.closed > 0 && `${plural(n.closed, 'closed posting')} removed from the list`,
  ].filter(Boolean)
  const sources = Object.entries(n.by_source).sort((a, b) => b[1] - a[1])
  return (
    <li style={{ padding: '0.75rem 0', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'baseline' }}>
        <span style={{ fontSize: '0.825rem', color: 'var(--text-1)', fontWeight: 500 }}>{nightLabel(n.run_date)}</span>
        <span style={{ fontSize: '0.78rem', fontWeight: 600, color: status.color }}>{status.text}</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>started {formatWhen(n.started_at)}</span>
      </div>
      <p style={{ ...muted, fontSize: '0.75rem' }}>{funnel}</p>
      {notes.map((t, i) => <p key={i} style={{ ...muted, fontSize: '0.75rem', color: 'var(--text-3)' }}>{t}</p>)}
      {sources.length > 0 && (
        <button type="button" onClick={() => setOpen(o => !o)} style={linkButton}>
          {open ? 'Hide sources' : 'Show sources'}
        </button>
      )}
      {open && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', gap: '0.35rem 1rem' }}>
          {sources.map(([source, count]) => (
            <li key={source} style={{ fontSize: '0.75rem', color: 'var(--text-2)' }}>
              {SOURCE_NAMES[source] ?? source} <span style={{ color: 'var(--text-1)', fontVariantNumeric: 'tabular-nums' }}>{count}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

/** Settings → Nightly runs. */
export default function NightlyRuns() {
  const [data, setData] = useState<AiRunsResponse | null>(null)
  const [failed, setFailed] = useState(false)
  const [all, setAll] = useState(false)
  useEffect(() => { listAiRuns().then(setData).catch(() => setFailed(true)) }, [])
  // Opened from a #nightly-runs link: the cards above load first and push this
  // one down, so scroll to it again once they (and this list) have rendered.
  useEffect(() => {
    if (!data || window.location.hash !== '#nightly-runs') return
    const t = window.setTimeout(() => document.getElementById('nightly-runs')?.scrollIntoView({ behavior: 'smooth' }), 300)
    return () => window.clearTimeout(t)
  }, [data])

  const t = data?.totals
  const nights = data ? (all ? data.nights : data.nights.slice(0, SHOWN)) : []
  return (
    <div style={card} id="nightly-runs">
      <h2 style={h2}>Nightly runs</h2>
      <p style={muted}>
        Every night at 22:00 (Berlin) Applaut's AI checks every job source, keeps the jobs that fit your countries
        and roles, and scores the new ones against your master profile. Jobs it scores {data?.doc_threshold ?? 80}% or
        more get a tailored CV and cover letter.
        {data && <> Next run: <strong style={{ color: 'var(--text-1)' }}>{formatWhen(data.next_run_at)}</strong>.</>}
      </p>
      {failed ? <p style={muted}>Couldn't load the runs. Try again later.</p>
        : data === null ? <p style={muted}>Loading…</p>
        : data.nights.length === 0 ? <p style={muted}>No runs for you yet. Your first one is {formatWhen(data.next_run_at)}.</p>
        : (
          <>
            {t && (
              <p style={{ ...muted, color: 'var(--text-1)' }}>
                {plural(t.nights, 'night')} so far: <strong>{t.new}</strong> new jobs for you, <strong>{t.scored}</strong> scored,{' '}
                <strong>{t.good}</strong> at {data.doc_threshold}%+, <strong>{t.docs_done}</strong> with a CV and cover letter.
              </p>
            )}
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {nights.map(n => <NightRow key={n.run_date} night={n} threshold={data.doc_threshold} />)}
            </ul>
            {data.nights.length > SHOWN && (
              <button type="button" onClick={() => setAll(a => !a)} style={linkButton}>
                {all ? 'Show fewer' : `Show all ${data.nights.length} nights`}
              </button>
            )}
          </>
        )}
    </div>
  )
}

/** Opportunities: last night in one line, linking to Settings → Nightly runs. */
export function LastNight() {
  const [data, setData] = useState<AiRunsResponse | null>(null)
  useEffect(() => { listAiRuns(1).then(setData).catch(() => setData(null)) }, [])
  if (!data) return null
  const n = data.nights[0]
  const link = <Link to="/applaut/settings#nightly-runs" style={{ color: 'var(--accent)' }}>Nightly runs</Link>
  return (
    <p style={{ color: 'var(--text-2)', fontSize: '0.8rem', margin: '0.2rem 0 0' }}>
      {n
        ? <>{nightLabel(n.run_date)}: {n.new} new for you, {n.scored} scored{n.scoring_left ? ` (${n.scoring_left} to go)` : ''}, {n.good} at {data.doc_threshold}%+ · {link}</>
        : <>First nightly run {formatWhen(data.next_run_at)} · {link}</>}
    </p>
  )
}
