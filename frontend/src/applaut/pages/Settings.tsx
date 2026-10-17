import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  errorMessage, getJobEngine, listRoutineRuns, listRoutineSyncs, removeRoutineConnection, saveRoutineConnection,
  setJobEngine, testRoutineConnection,
  type CheckResult, type ConnectionInput, type JobEngineState, type RoutineRun, type RoutineSync,
} from '../api/jobEngine'
import { JOB_ENGINE_LABELS, type JobEngine } from '../api/profile'
import RoutineEngineCard, { buttonStyle, formatWhen } from '../components/RoutineEngineCard'

// Settings → Job engine (docs/applaut/JOB_ENGINES_DESIGN.md §3.4, §6.6–6.8).
// Secrets are write-only: the form never receives them back, only hints.

const card: React.CSSProperties = {
  padding: '1.25rem', background: 'var(--bg-surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius)', display: 'flex', flexDirection: 'column', gap: '0.875rem',
}
const h2: React.CSSProperties = { fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-1)' }
const muted: React.CSSProperties = { fontSize: '0.8rem', color: 'var(--text-2)', margin: 0 }
const label: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.78rem', color: 'var(--text-2)', fontWeight: 500 }
const pre: React.CSSProperties = {
  margin: 0, padding: '0.75rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)',
  fontSize: '0.75rem', color: 'var(--text-1)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: '320px', overflowY: 'auto',
}

const ENGINES: { id: JobEngine; badge: string; text: string; disabled?: boolean }[] = [
  { id: 'applaut_ai', badge: 'Coming soon', text: "Applaut's AI searches German job sites, reads every new job against your profile and writes a tailored CV and cover letter. Nothing to set up.", disabled: true },
  { id: 'own_routine', badge: 'For IT professionals', text: 'Run the AI job search in your own Claude account. Applaut collects your jobs and documents an hour after each run, reading your Neon database and R2 bucket with read-only keys.' },
  { id: 'basic', badge: 'Fallback', text: 'Keyword search on company job boards with a rule-based match score and template documents. No AI, no setup.' },
]

const TIMEZONES = ['UTC', 'Europe/Berlin', 'Europe/London', 'Europe/Paris', 'Europe/Amsterdam', 'Europe/Vienna', 'Europe/Zurich', 'America/New_York', 'Asia/Kolkata']

const READ_ONLY_SQL = `-- Run in Neon's SQL editor, as the database owner.
-- Choose a long random password; Neon rejects weak ones.
CREATE ROLE applaut_reader WITH LOGIN PASSWORD '<a long random password>';
GRANT CONNECT ON DATABASE neondb TO applaut_reader;
GRANT USAGE ON SCHEMA public TO applaut_reader;
GRANT SELECT ON jobsearchautomationresults, run_tracker TO applaut_reader;
-- Tables the routine adds later are readable too:
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO applaut_reader;`

// --- schedule picker: daily (or weekday) times that share one minute = one cron line

interface Schedule { times: string[]; days: 'daily' | 'weekdays' }

function parseCron(cron: string): Schedule | null {
  const m = cron.trim().match(/^(\d{1,2}) ([\d,]+) \* \* (\*|1-5|mon-fri)$/i)
  if (!m) return null
  const minute = m[1].padStart(2, '0')
  return {
    times: m[2].split(',').map(h => `${h.padStart(2, '0')}:${minute}`),
    days: m[3] === '*' ? 'daily' : 'weekdays',
  }
}

function buildCron(s: Schedule): string | null {
  const parsed = s.times.map(t => t.match(/^(\d{1,2}):(\d{2})$/)).filter(Boolean) as RegExpMatchArray[]
  if (parsed.length === 0 || parsed.length !== s.times.length) return null
  const minutes = new Set(parsed.map(p => Number(p[2])))
  if (minutes.size !== 1) return null
  const hours = [...new Set(parsed.map(p => Number(p[1])))].sort((a, b) => a - b)
  if (hours.some(h => h > 23) || [...minutes][0] > 59) return null
  return `${[...minutes][0]} ${hours.join(',')} * * ${s.days === 'daily' ? '*' : '1-5'}`
}

function SchedulePicker({ cron, timezone, onChange }: { cron: string; timezone: string; onChange: (cron: string, tz: string) => void }) {
  const parsed = useMemo(() => parseCron(cron), [cron])
  const [advanced, setAdvanced] = useState(parsed === null)
  const [timesText, setTimesText] = useState(parsed ? parsed.times.join(', ') : '06:07, 18:07')
  const [days, setDays] = useState<Schedule['days']>(parsed?.days ?? 'daily')
  const [problem, setProblem] = useState<string | null>(null)

  const apply = (text: string, d: Schedule['days']) => {
    const built = buildCron({ times: text.split(',').map(t => t.trim()).filter(Boolean), days: d })
    setProblem(built ? null : 'Use times like 06:07, 18:07 that share the same minute (your routine uses one cron line).')
    if (built) onChange(built, timezone)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
      <p style={muted}>Enter the same schedule as your routine in Claude. Applaut checks 30 min, 1 h, 2 h and 3 h after each run, and syncs an hour after the run finishes.</p>
      {advanced ? (
        <label style={label}>Cron (minute hour day month weekday)
          <input value={cron} onChange={e => onChange(e.target.value, timezone)} placeholder="7 6,18 * * *" />
        </label>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.6rem' }}>
          <label style={label}>Run times
            <input value={timesText} onChange={e => { setTimesText(e.target.value); apply(e.target.value, days) }} placeholder="06:07, 18:07" />
          </label>
          <label style={label}>Days
            <select value={days} onChange={e => { const d = e.target.value as Schedule['days']; setDays(d); apply(timesText, d) }}>
              <option value="daily">Every day</option>
              <option value="weekdays">Monday to Friday</option>
            </select>
          </label>
        </div>
      )}
      <label style={{ ...label, maxWidth: '260px' }}>Timezone of these times
        <select value={timezone} onChange={e => onChange(cron, e.target.value)}>
          {[...new Set([timezone, ...TIMEZONES])].map(tz => <option key={tz} value={tz}>{tz}</option>)}
        </select>
      </label>
      {problem && <p style={{ ...muted, color: 'var(--warn)' }}>{problem}</p>}
      <p style={{ ...muted, fontSize: '0.75rem' }}>
        Cron: <code>{cron}</code> ({timezone}) ·{' '}
        <button type="button" onClick={() => setAdvanced(a => !a)} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: '0.75rem' }}>
          {advanced ? 'Use the simple picker' : 'Edit cron directly'}
        </button>
      </p>
    </div>
  )
}

// --- connection form

function Checks({ checks }: { checks: CheckResult[] }) {
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
      {checks.map(c => (
        <li key={c.key} style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8rem', color: 'var(--text-1)' }}>
          <span style={{ color: c.ok ? 'var(--success)' : 'var(--danger)', fontWeight: 700, width: '1rem', flexShrink: 0 }}>{c.ok ? '✓' : '✕'}</span>
          <span><strong style={{ fontWeight: 600 }}>{c.label}</strong> — <span style={{ color: 'var(--text-2)', overflowWrap: 'anywhere' }}>{c.message}</span></span>
        </li>
      ))}
    </ul>
  )
}

function ConnectionForm({ state, onSaved }: { state: JobEngineState; onSaved: (s: JobEngineState) => void }) {
  const saved = state.connection
  const [form, setForm] = useState<Required<Omit<ConnectionInput, 'routine_url'>> & { routine_url: string }>({
    neon_url: '', r2_access_key_id: '', r2_secret: '',
    r2_account_id: saved?.r2_account_id ?? '', r2_bucket: saved?.r2_bucket ?? 'job-search-automation-documents',
    r2_prefix: saved?.r2_prefix ?? 'jobautomationdocs', routine_url: saved?.routine_url ?? '',
    schedule_cron: saved?.schedule_cron ?? '7 6,18 * * *', timezone: saved?.timezone ?? 'UTC',
  })
  const [busy, setBusy] = useState<'test' | 'save' | 'remove' | null>(null)
  const [checks, setChecks] = useState<CheckResult[] | null>(null)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const [showSql, setShowSql] = useState(false)

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  const payload = (): ConnectionInput => {
    const p: ConnectionInput = {
      r2_account_id: form.r2_account_id, r2_bucket: form.r2_bucket, r2_prefix: form.r2_prefix,
      routine_url: form.routine_url || null, schedule_cron: form.schedule_cron, timezone: form.timezone,
    }
    // Empty secret fields keep what's saved.
    if (form.neon_url) p.neon_url = form.neon_url
    if (form.r2_access_key_id) p.r2_access_key_id = form.r2_access_key_id
    if (form.r2_secret) p.r2_secret = form.r2_secret
    return p
  }

  const test = async () => {
    setBusy('test'); setMessage(null)
    try {
      const res = await testRoutineConnection(payload())
      setChecks(res.checks)
      setMessage({ ok: res.ok, text: res.ok ? 'Everything checks out. Save to connect.' : 'A check failed; see below.' })
    } catch (err) {
      setChecks(null); setMessage({ ok: false, text: errorMessage(err) })
    } finally { setBusy(null) }
  }

  const save = async () => {
    setBusy('save'); setMessage(null)
    try {
      const res = await saveRoutineConnection(payload())
      setChecks(null)
      setForm(f => ({ ...f, neon_url: '', r2_access_key_id: '', r2_secret: '' }))
      setMessage({ ok: true, text: saved ? 'Connection updated.' : 'Connected. The first sync is starting now.' })
      onSaved(res)
    } catch (err) {
      const data = (err as { response?: { data?: { checks?: CheckResult[] } } })?.response?.data
      if (data?.checks) setChecks(data.checks)
      setMessage({ ok: false, text: errorMessage(err, 'Not saved') })
    } finally { setBusy(null) }
  }

  const remove = async () => {
    if (!window.confirm('Remove the connection? Applaut deletes the stored Neon URL and R2 keys now. Jobs and documents already synced stay.')) return
    setBusy('remove'); setMessage(null)
    try {
      await removeRoutineConnection()
      onSaved(await getJobEngine())
    } catch (err) {
      setMessage({ ok: false, text: errorMessage(err) })
    } finally { setBusy(null) }
  }

  const missingNew = !saved && (!form.neon_url || !form.r2_access_key_id || !form.r2_secret || !form.r2_account_id)

  return (
    <div style={card}>
      <div>
        <h2 style={h2}>Connection</h2>
        <p style={{ ...muted, marginTop: '0.3rem' }}>
          Applaut only ever <strong>reads</strong> your database and bucket. Use a read-only Neon role and an R2 key with
          "Object Read only" permission for this bucket. To prove the key can't write, Applaut tries to save one empty file
          (<code>applaut-permission-check/…</code>); if that works, it deletes the file and refuses the key.
          Secrets are stored encrypted and never shown again.
        </p>
      </div>

      {saved?.status === 'paused' && (
        <p style={{ ...muted, color: 'var(--danger)' }}>
          Checking is paused after {saved.consecutive_failures} failed connection attempts ({saved.last_error}). Fix the
          problem, then press <strong>Save</strong> (with new values, or as is) to try again.
        </p>
      )}

      <label style={label}>Neon connection string (read-only role)
        <input type="password" autoComplete="off" value={form.neon_url} onChange={set('neon_url')}
          placeholder={saved ? `Saved · ${saved.neon_host} — leave empty to keep` : 'postgresql://applaut_reader:…@ep-….neon.tech/neondb?sslmode=require'} />
      </label>
      <button type="button" onClick={() => setShowSql(s => !s)} style={{ alignSelf: 'flex-start', background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: '0.78rem' }}>
        {showSql ? 'Hide' : 'Show'} the SQL that creates a read-only role
      </button>
      {showSql && <pre style={pre}>{READ_ONLY_SQL}</pre>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
        <label style={label}>Cloudflare account id
          <input value={form.r2_account_id} onChange={set('r2_account_id')} placeholder="32 hexadecimal characters" />
        </label>
        <label style={label}>R2 bucket
          <input value={form.r2_bucket} onChange={set('r2_bucket')} />
        </label>
        <label style={label}>Folder in the bucket
          <input value={form.r2_prefix} onChange={set('r2_prefix')} />
        </label>
        <label style={label}>R2 access key id (read-only)
          <input autoComplete="off" value={form.r2_access_key_id} onChange={set('r2_access_key_id')}
            placeholder={saved ? `Saved · ends in …${saved.r2_access_key_hint}` : ''} />
        </label>
        <label style={label}>R2 secret access key
          <input type="password" autoComplete="off" value={form.r2_secret} onChange={set('r2_secret')}
            placeholder={saved ? 'Saved — leave empty to keep' : ''} />
        </label>
        <label style={label}>Routine link (optional)
          <input value={form.routine_url} onChange={set('routine_url')} placeholder="https://claude.ai/code/routines/…" />
        </label>
      </div>

      <SchedulePicker cron={form.schedule_cron} timezone={form.timezone}
        onChange={(cron, tz) => setForm(f => ({ ...f, schedule_cron: cron, timezone: tz }))} />

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button type="button" onClick={test} disabled={busy !== null || missingNew} style={buttonStyle('ghost', busy !== null || missingNew)}>
          {busy === 'test' ? 'Testing…' : 'Test connection'}
        </button>
        <button type="button" onClick={save} disabled={busy !== null || missingNew} style={buttonStyle('primary', busy !== null || missingNew)}>
          {busy === 'save' ? 'Checking and saving…' : saved ? 'Save' : 'Save and connect'}
        </button>
        {saved && (
          <button type="button" onClick={remove} disabled={busy !== null} style={buttonStyle('danger', busy !== null)}>
            {busy === 'remove' ? 'Removing…' : 'Remove connection'}
          </button>
        )}
      </div>
      {message && <p style={{ ...muted, color: message.ok ? 'var(--success)' : 'var(--danger)' }}>{message.text}</p>}
      {checks && <Checks checks={checks} />}
      {saved && (
        <p style={{ ...muted, fontSize: '0.75rem' }}>
          Last verified {formatWhen(saved.verified_at)} · last checked {formatWhen(saved.last_check_at)}
          {saved.contract_version !== null && ` · contract v${saved.contract_version}`}
        </p>
      )}
    </div>
  )
}

// --- history

const OUTCOME_COLOR: Record<string, string> = {
  succeeded: 'var(--success)', running: 'var(--blue)', problems: 'var(--warn)',
  failed: 'var(--danger)', stopped: 'var(--danger)', missed: 'var(--danger)',
}

function RunRow({ run }: { run: RoutineRun }) {
  const [open, setOpen] = useState(false)
  const outcome = run.outcome === 'succeeded' ? 'completed' : run.outcome === 'missed' ? "didn't run" : run.outcome === 'problems' ? 'finished with problems' : run.outcome
  const funnel = run.run_id
    ? [
        run.searches_run !== null && `${run.searches_run}${run.search_budget ? ` of ${run.search_budget}` : ''} searches`,
        run.postings_found !== null && `${run.postings_found} found`,
        run.postings_assessed !== null && `${run.postings_assessed} assessed`,
        run.jobs_eligible !== null && `${run.jobs_eligible} eligible`,
        run.jobs_new !== null && `${run.jobs_new} new, ${run.jobs_updated ?? 0} updated`,
        run.docs_done !== null && `${run.docs_done} documents${run.docs_failed ? ` (${run.docs_failed} failed)` : ''}`,
      ].filter(Boolean).join(' · ')
    : ''
  const hasDetails = Boolean(run.error || run.summary || run.sources_failed)
  return (
    <li style={{ padding: '0.75rem 0', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'baseline' }}>
        <span style={{ fontSize: '0.825rem', color: 'var(--text-1)', fontWeight: 500 }}>{formatWhen(run.started_at ?? run.expected_at)}</span>
        <span style={{ fontSize: '0.78rem', fontWeight: 600, color: OUTCOME_COLOR[run.outcome] ?? 'var(--text-2)' }}>{outcome}</span>
        {run.current_step && run.outcome !== 'succeeded' && <span style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>at {run.current_step}</span>}
        {run.run_id && <span style={{ fontSize: '0.72rem', color: 'var(--text-3)' }}>{run.run_id}</span>}
      </div>
      {run.outcome !== 'succeeded' && <p style={{ ...muted, color: 'var(--text-1)', overflowWrap: 'anywhere' }}>{run.message}</p>}
      {funnel && <p style={{ ...muted, fontSize: '0.75rem' }}>{funnel}</p>}
      {hasDetails && (
        <button type="button" onClick={() => setOpen(o => !o)} style={{ alignSelf: 'flex-start', background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: '0.75rem' }}>
          {open ? 'Hide details' : 'Show details'}
        </button>
      )}
      {open && (
        <>
          {run.error && <pre style={{ ...pre, borderColor: 'var(--danger-border)' }}>{run.error}</pre>}
          {run.sources_failed && <pre style={{ ...pre, borderColor: 'var(--warn-border)' }}>Sources failed: {run.sources_failed}</pre>}
          {run.summary && <pre style={pre}>{run.summary}</pre>}
        </>
      )}
    </li>
  )
}

function History({ refreshKey }: { refreshKey: number }) {
  const [runs, setRuns] = useState<RoutineRun[] | null>(null)
  const [syncs, setSyncs] = useState<RoutineSync[] | null>(null)
  useEffect(() => {
    listRoutineRuns().then(setRuns).catch(() => setRuns([]))
    listRoutineSyncs().then(setSyncs).catch(() => setSyncs([]))
  }, [refreshKey])

  return (
    <>
      <div style={card} id="run-history">
        <h2 style={h2}>Run history</h2>
        <p style={muted}>From your routine's <code>run_tracker</code> table. The full transcript of each run stays in your Claude account.</p>
        {runs === null ? <p style={muted}>Loading…</p> : runs.length === 0 ? <p style={muted}>No runs recorded yet.</p> : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>{runs.map(r => <RunRow key={r.id} run={r} />)}</ul>
        )}
      </div>
      <div style={card}>
        <h2 style={h2}>Syncs</h2>
        {syncs === null ? <p style={muted}>Loading…</p> : syncs.length === 0 ? <p style={muted}>No syncs yet.</p> : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {syncs.map(s => (
              <li key={s.id} style={{ padding: '0.6rem 0', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-1)' }}>
                  {formatWhen(s.started_at)} · {s.trigger} ·{' '}
                  <span style={{ color: s.status === 'failed' ? 'var(--danger)' : s.status === 'partial' ? 'var(--warn)' : s.status === 'running' ? 'var(--blue)' : 'var(--success)' }}>{s.status}</span>
                  {s.status !== 'failed' && ` · ${s.jobs_new} new, ${s.jobs_updated} updated, ${s.docs_copied} documents`}
                  {s.jobs_removed > 0 && ` · ${s.jobs_removed} no longer in your routine's database`}
                </span>
                {s.error && <span style={{ ...muted, color: 'var(--danger)', overflowWrap: 'anywhere' }}>{s.error}</span>}
                {s.problems.slice(0, 5).map((p, i) => <span key={i} style={{ ...muted, fontSize: '0.75rem', overflowWrap: 'anywhere' }}>• {p}</span>)}
                {s.problems.length > 5 && <span style={{ ...muted, fontSize: '0.75rem' }}>…and {s.problems.length - 5} more</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  )
}

// --- page

export default function Settings() {
  const [state, setState] = useState<JobEngineState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [switching, setSwitching] = useState<JobEngine | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const location = useLocation()

  const load = useCallback(() => {
    getJobEngine().then(s => { setState(s); setError(null) }).catch(err => setError(errorMessage(err, 'Could not load your settings')))
  }, [])
  useEffect(load, [load])

  useEffect(() => {
    if (state && location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' })
  }, [state, location.hash])

  const choose = async (engine: JobEngine) => {
    if (!state || engine === state.engine) return
    let confirm = false
    if (state.engine === 'own_routine' && state.connection) {
      if (!window.confirm(`Switch to ${JOB_ENGINE_LABELS[engine]}? This deletes your routine's stored connection (Neon URL and R2 keys). Jobs and documents already synced stay.`)) return
      confirm = true
    }
    setSwitching(engine)
    try {
      setState(await setJobEngine(engine, confirm))
      setRefreshKey(k => k + 1)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSwitching(null)
    }
  }

  const onSaved = (s: JobEngineState) => { setState(s); setRefreshKey(k => k + 1) }

  return (
    <div style={{ maxWidth: '760px', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.25rem', color: 'var(--text-1)' }}>Settings</h1>
        <p style={{ ...muted, fontSize: '0.875rem' }}>Job engine: what finds jobs for you and writes your CV and cover letter.</p>
      </div>
      {error && <p style={{ ...muted, color: 'var(--danger)' }}>{error}</p>}
      {!state ? (!error && <p style={muted}>Loading…</p>) : (
        <>
          <div style={card}>
            <h2 style={h2}>Job engine</h2>
            <div role="radiogroup" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
              {ENGINES.map(e => {
                const active = state.engine === e.id
                return (
                  <button key={e.id} type="button" role="radio" aria-checked={active} disabled={e.disabled || switching !== null}
                    onClick={() => choose(e.id)}
                    style={{
                      textAlign: 'left', padding: '0.875rem', borderRadius: 'var(--radius-sm)', cursor: e.disabled ? 'default' : 'pointer',
                      background: active ? 'var(--accent-glow)' : 'var(--bg-elevated)', opacity: e.disabled ? 0.55 : 1,
                      border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border)'}`, display: 'flex', flexDirection: 'column', gap: '0.4rem',
                    }}>
                    <span style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-1)' }}>{JOB_ENGINE_LABELS[e.id]}</span>
                      {active && <span style={{ fontSize: '0.7rem', color: 'var(--accent)', fontWeight: 600 }}>Current</span>}
                    </span>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{e.badge}</span>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-2)', lineHeight: 1.45 }}>{switching === e.id ? 'Switching…' : e.text}</span>
                  </button>
                )
              })}
            </div>
            <p style={{ ...muted, fontSize: '0.75rem' }}>You can change this any time. Your jobs and documents stay when you switch.</p>
          </div>

          {state.engine === 'own_routine' && (
            <>
              {state.card && <RoutineEngineCard card={state.card} showHistoryLink={false}
                onChange={c => { setState(s => s ? { ...s, card: c } : s); setRefreshKey(k => k + 1) }} />}
              {state.credentials_storage_ready ? (
                <ConnectionForm key={state.connection?.updated_at ?? 'new'} state={state} onSaved={onSaved} />
              ) : (
                <div style={card}><p style={{ ...muted, color: 'var(--warn)' }}>Applaut can't store connection details on this server yet (no encryption key configured).</p></div>
              )}
              {state.connection && <History refreshKey={refreshKey} />}
            </>
          )}
        </>
      )}
    </div>
  )
}
