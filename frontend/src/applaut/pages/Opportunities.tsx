import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  effectiveScore,
  getLocalDocsFolder,
  listOpportunities,
  runDiscovery,
  setTracking,
  type Tracking,
  type TrackingState,
  type Assessment,
  type EngineFilter,
  type MatchFilter,
  type NearMissKeyword,
  type Opportunity,
} from '../api/opportunity'
import { getMyProfile, JOB_ENGINE_LABELS, type JobEngine } from '../api/profile'
import { decideNearMiss } from '../api/scoring'
import { apiErrorMessage } from '../api/errors'

const SOURCE_LABELS: Record<string, string> = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  ashby: 'Ashby',
  personio: 'Personio',
  own_routine: 'Your Claude routine',
  applaut_ai: 'Applaut AI',
}

const REMOTE_COLORS: Record<string, string> = {
  remote: 'var(--success)',
  hybrid: 'var(--warn)',
  onsite: 'var(--text-3)',
}

type Category = 'good' | 'near_miss' | 'below' | 'unscored'

function categoryOf(opp: Opportunity, good: number, nearMiss: number): Category {
  const score = effectiveScore(opp)
  if (score === null) return 'unscored'
  if (score >= good) return 'good'
  if (score >= nearMiss) return 'near_miss'
  return 'below'
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span style={{
      padding: '0.15rem 0.55rem',
      borderRadius: '999px',
      fontSize: '0.7rem',
      fontWeight: 500,
      background: `${color}1a`,
      color,
      border: `1px solid ${color}40`,
      whiteSpace: 'nowrap',
    }}>
      {text}
    </span>
  )
}

function ScoreBadge({ score, good, nearMiss }: { score: number; good: number; nearMiss: number }) {
  const color = score >= good ? 'var(--success)' : score >= nearMiss ? 'var(--warn)' : 'var(--text-3)'
  return (
    <span style={{
      padding: '0.2rem 0.625rem',
      borderRadius: '999px',
      fontSize: '0.8rem',
      fontWeight: 700,
      background: `${color}1a`,
      color,
      border: `1px solid ${color}40`,
      fontVariantNumeric: 'tabular-nums',
      flexShrink: 0,
    }}>
      {score}
    </span>
  )
}

function KeywordChip({ kw }: { kw: NearMissKeyword }) {
  const color = kw.suitable === true ? 'var(--success)' : kw.suitable === false ? 'var(--danger)' : 'var(--warn)'
  const label = kw.suitable === true ? '✓ suitable' : kw.suitable === false ? '✗ outside stack' : '? uncertain'
  return (
    <div style={{ padding: '0.5rem 0.75rem', border: `1px solid ${color}30`, background: `${color}08`, borderRadius: 'var(--radius-xs)', fontSize: '0.8rem' }}>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, color: 'var(--text-1)' }}>{kw.keyword}</span>
        <span style={{ color, fontSize: '0.72rem' }}>{label}</span>
      </div>
      <p style={{ color: 'var(--text-2)', margin: '0.2rem 0 0', fontSize: '0.72rem' }}>{kw.reason}</p>
    </div>
  )
}

function AssessmentSummary({ assessment }: { assessment: Assessment }) {
  return (
    <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
      <span title={assessment.matched_skills.join(', ')} style={{ padding: '0.15rem 0.55rem', background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: '999px', fontSize: '0.72rem', color: 'var(--success)', cursor: 'help' }}>
        ✓ {assessment.matched_skills.length} must-haves matched
      </span>
      {assessment.missing_skills.length > 0 && (
        <span title={assessment.missing_skills.join(', ')} style={{ padding: '0.15rem 0.55rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: '999px', fontSize: '0.72rem', color: 'var(--text-2)', cursor: 'help' }}>
          ✗ missing: {assessment.missing_skills.slice(0, 3).join(', ')}{assessment.missing_skills.length > 3 ? ` +${assessment.missing_skills.length - 3}` : ''}
        </span>
      )}
      {assessment.flags.length > 0 && (
        <span title={assessment.flags.join('\n')} style={{ padding: '0.15rem 0.55rem', background: 'var(--warn-bg)', border: '1px solid var(--warn-border)', borderRadius: '999px', fontSize: '0.72rem', color: 'var(--warn)', cursor: 'help' }}>
          ⚠ {assessment.flags.length} to check
        </span>
      )}
    </div>
  )
}

function DimensionChips({ explanation }: { explanation: Record<string, { score: number; max: number; explanation: string }> }) {
  return (
    <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
      {Object.entries(explanation).map(([key, d]) => (
        <span key={key} title={d.explanation} style={{ padding: '0.15rem 0.55rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: '999px', fontSize: '0.72rem', color: 'var(--text-2)', cursor: 'help' }}>
          {key}: {d.score}/{d.max}
        </span>
      ))}
    </div>
  )
}

function NearMissPanel({ opp, goodThreshold, onUpdate }: { opp: Opportunity; goodThreshold: number; onUpdate: () => void }) {
  const [selected, setSelected] = useState<string[]>([])
  const [deciding, setDeciding] = useState(false)
  const [promoted, setPromoted] = useState<{ newScore: number } | null>(null)

  const keywords = opp.score?.near_miss_keywords || []
  const toggleKeyword = (kw: string) =>
    setSelected(prev => prev.includes(kw) ? prev.filter(k => k !== kw) : [...prev, kw])

  const decide = async (action: 'keep' | 'dismiss' | 'keep_with_keywords') => {
    if (!opp.score) return
    setDeciding(true)
    try {
      const updated = await decideNearMiss(opp.score.id, action, action === 'keep_with_keywords' ? selected : [])
      if (action === 'keep_with_keywords' && updated.total_score >= goodThreshold) {
        setPromoted({ newScore: updated.total_score })
        setTimeout(() => onUpdate(), 2000)
      } else {
        onUpdate()
      }
    } finally {
      setDeciding(false)
    }
  }

  if (promoted) {
    return (
      <div style={{ marginTop: '0.75rem', padding: '0.75rem 1rem', background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 'var(--radius-xs)' }}>
        <p style={{ fontWeight: 600, margin: 0, color: 'var(--success)', fontSize: '0.85rem' }}>
          Promoted to Good Match — new score {promoted.newScore} ✓
        </p>
      </div>
    )
  }

  return (
    <div style={{ marginTop: '0.5rem' }}>
      {keywords.length > 0 && (
        <>
          <p style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-1)' }}>
            Gap keywords — adding these could push your score above {goodThreshold}:
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem', marginBottom: '0.875rem' }}>
            {keywords.map(kw => (
              <div key={kw.keyword} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
                {kw.suitable !== false && (
                  <input type="checkbox" checked={selected.includes(kw.keyword)} onChange={() => toggleKeyword(kw.keyword)} style={{ marginTop: '0.5rem', flexShrink: 0 }} />
                )}
                <KeywordChip kw={kw} />
              </div>
            ))}
          </div>
        </>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {selected.length > 0 && (
          <button
            onClick={() => decide('keep_with_keywords')}
            disabled={deciding}
            style={{ padding: '0.4rem 0.875rem', background: 'var(--success)', color: '#fff', border: 'none', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 500 }}
          >
            Add {selected.length} keyword{selected.length > 1 ? 's' : ''} + keep
          </button>
        )}
        <button
          onClick={() => decide('keep')}
          disabled={deciding}
          style={{ padding: '0.4rem 0.875rem', background: 'var(--bg-elevated)', color: 'var(--text-1)', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.8rem' }}
        >
          Keep without adding
        </button>
        <button
          onClick={() => decide('dismiss')}
          disabled={deciding}
          style={{ padding: '0.4rem 0.875rem', background: 'var(--danger-bg)', color: 'var(--danger)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.8rem' }}
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}

const actionBtn = (tone: 'primary' | 'ghost' | 'success' | 'danger' = 'ghost', disabled = false): React.CSSProperties => ({
  padding: '0.35rem 0.8rem',
  borderRadius: 'var(--radius-xs)',
  fontSize: '0.8rem',
  fontWeight: 500,
  cursor: disabled ? 'default' : 'pointer',
  opacity: disabled ? 0.5 : 1,
  textDecoration: 'none',
  whiteSpace: 'nowrap',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '0.3rem',
  background: tone === 'primary' ? 'var(--accent)' : tone === 'success' ? 'var(--success-bg)' : tone === 'danger' ? 'var(--danger-bg)' : 'transparent',
  color: tone === 'primary' ? '#fff' : tone === 'success' ? 'var(--success)' : tone === 'danger' ? 'var(--danger)' : 'var(--text-1)',
  border: `1px solid ${tone === 'primary' ? 'var(--accent)' : tone === 'success' ? 'var(--success-border)' : tone === 'danger' ? 'var(--danger-border)' : 'var(--border-strong)'}`,
})

const UNAVAILABLE_LABEL: Record<string, string> = { closed: 'Posting closed', withdrawn: "Can't apply" }

function shortDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short' }) : ''
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Older browsers, or clipboard permission denied: copy via a selected textarea.
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    let ok = false
    try { ok = document.execCommand('copy') } catch { ok = false }
    document.body.removeChild(ta)
    return ok
  }
}

/** Apply ↗ · Copy folder path · Documents · Mark as applied · Not available — and Undo. */
function JobActions({ opp, showDocuments, onTracked }: {
  opp: Opportunity
  showDocuments: boolean
  onTracked: (opp: Opportunity, tracking: Tracking) => void
}) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [askReason, setAskReason] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const state = opp.tracking.state

  const track = async (next: TrackingState, reason?: 'closed' | 'cannot_apply') => {
    setBusy(true)
    setAskReason(false)
    try {
      onTracked(opp, await setTracking(opp.id, next, reason))
      setNote(null)
    } catch (err: any) {
      setNote(apiErrorMessage(err, 'Could not update this job'))
    } finally {
      setBusy(false)
    }
  }

  const folder = opp.routine?.docs_ready ? `${getLocalDocsFolder()}/${opp.routine.uid}` : null
  const copyFolder = async () => {
    if (!folder) return
    if (await copyText(folder)) setNote('Folder path copied. In Finder press ⇧⌘G, paste, then Return.')
    else setNote(`Couldn't copy. The folder is ${folder}`)
    window.setTimeout(() => setNote(null), 6000)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {opp.application_url ? (
          <a href={opp.application_url} target="_blank" rel="noopener noreferrer" style={actionBtn('primary')}
            title="Open the job posting to apply">
            Apply ↗
          </a>
        ) : (
          <span style={actionBtn('primary', true)} title="This job has no apply link">Apply ↗</span>
        )}
        {folder && (
          <button type="button" onClick={copyFolder} style={actionBtn()} title={`Copies ${folder}: the CV and cover letter your Mac synced`}>
            Copy folder path
          </button>
        )}
        {showDocuments && (
          <button type="button" onClick={() => navigate(`/applaut/documents/${opp.id}`)} style={actionBtn()}>
            {opp.is_private || opp.routine ? 'Documents' : 'Generate documents'}
          </button>
        )}
        {state === 'open' && (
          <>
            <button type="button" onClick={() => track('applied')} disabled={busy} style={actionBtn('success', busy)}>
              Mark as applied
            </button>
            <button type="button" onClick={() => setAskReason(a => !a)} disabled={busy} style={actionBtn('ghost', busy)}
              aria-expanded={askReason} title="The posting is closed, or you can't apply">
              Not available ▾
            </button>
          </>
        )}
        {state === 'applied' && (
          <>
            <Badge text={`✓ Applied ${shortDate(opp.tracking.applied_at)}`} color="var(--success)" />
            <button type="button" onClick={() => track('open')} disabled={busy} style={actionBtn('ghost', busy)}>Undo</button>
          </>
        )}
        {state === 'unavailable' && (
          <>
            <Badge text={UNAVAILABLE_LABEL[opp.tracking.status ?? ''] ?? 'Not available'} color="var(--text-2)" />
            <button type="button" onClick={() => track('open')} disabled={busy} style={actionBtn('ghost', busy)}>Undo</button>
          </>
        )}
      </div>
      {askReason && state === 'open' && (
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-2)' }}>Why?</span>
          <button type="button" onClick={() => track('unavailable', 'closed')} disabled={busy} style={actionBtn('danger', busy)}>
            Posting closed
          </button>
          <button type="button" onClick={() => track('unavailable', 'cannot_apply')} disabled={busy} style={actionBtn('danger', busy)}>
            I can't apply
          </button>
        </div>
      )}
      {note && <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-2)' }}>{note}</p>}
    </div>
  )
}

const CATEGORY_BORDER: Record<Category, string> = {
  good: 'var(--border)',
  near_miss: 'var(--warn-border)',
  below: 'var(--border)',
  unscored: 'var(--border)',
}

const CATEGORY_BG: Record<Category, string> = {
  good: 'var(--bg-surface)',
  near_miss: 'var(--warn-bg)',
  below: 'var(--bg-surface)',
  unscored: 'var(--bg-surface)',
}

function OpportunityCard({ opp, goodThreshold, nearMissThreshold, onUpdate, onTracked }: {
  opp: Opportunity
  goodThreshold: number
  nearMissThreshold: number
  onUpdate: () => void
  onTracked: (opp: Opportunity, tracking: Tracking) => void
}) {
  const category = categoryOf(opp, goodThreshold, nearMissThreshold)
  // Keyword review applies to Applaut's rule-based score only; an AI engine's
  // assessment already lists what's missing.
  const needsReview = category === 'near_miss' && !opp.assessment && !!opp.score
    && (!opp.score.user_decision || opp.score.user_decision === 'pending_review')

  return (
    <div style={{
      padding: '1.125rem 1.25rem',
      background: CATEGORY_BG[category],
      border: `1px solid ${CATEGORY_BORDER[category]}`,
      borderRadius: 'var(--radius)',
      transition: 'border-color 0.15s, opacity 0.15s',
      opacity: opp.tracking.state === 'open' ? 1 : 0.72,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '0.625rem' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Link
            to={`/applaut/opportunities/${opp.id}`}
            style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-1)', textDecoration: 'none', display: 'block', marginBottom: '0.2rem' }}
          >
            {opp.title}
          </Link>
          <p style={{ color: 'var(--text-2)', fontSize: '0.825rem', margin: '0 0 0.6rem' }}>{opp.company_name}</p>
          <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap', alignItems: 'center' }}>
            {opp.location_raw && (
              <span style={{ fontSize: '0.775rem', color: 'var(--text-2)' }}>📍 {opp.location_raw}</span>
            )}
            {opp.remote_option && (
              <Badge
                text={{ remote: 'Remote', hybrid: 'Hybrid', onsite: 'On-site' }[opp.remote_option] ?? opp.remote_option}
                color={REMOTE_COLORS[opp.remote_option] ?? 'var(--text-2)'}
              />
            )}
            <Badge text={opp.routine ? 'Your Claude routine' : SOURCE_LABELS[opp.source] ?? opp.source} color="var(--accent)" />
            {opp.routine?.removed && <Badge text="No longer in your routine's database" color="var(--text-3)" />}
            {opp.routine && !opp.routine.docs_ready && <Badge text="Documents not ready" color="var(--warn)" />}
            {category === 'near_miss' && !needsReview && !opp.assessment && <Badge text="Reviewed" color="var(--text-3)" />}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.4rem', flexShrink: 0 }}>
          {opp.assessment?.match_score != null ? (
            <span title="Match % from your job engine's AI assessment" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <span style={{ fontSize: '0.68rem', color: 'var(--text-3)' }}>AI match</span>
              <ScoreBadge score={opp.assessment.match_score} good={goodThreshold} nearMiss={nearMissThreshold} />
            </span>
          ) : opp.score ? (
            <ScoreBadge score={opp.score.total_score} good={goodThreshold} nearMiss={nearMissThreshold} />
          ) : (
            <span style={{ fontSize: '0.72rem', color: 'var(--text-3)' }}>not scored</span>
          )}
          {opp.posted_at && (
            <p style={{ fontSize: '0.72rem', color: 'var(--text-3)', whiteSpace: 'nowrap', margin: 0 }}>
              {new Date(opp.posted_at).toLocaleDateString()}
            </p>
          )}
        </div>
      </div>

      {opp.assessment ? <AssessmentSummary assessment={opp.assessment} /> : opp.score && <DimensionChips explanation={opp.score.explanation} />}

      {needsReview && <NearMissPanel opp={opp} goodThreshold={goodThreshold} onUpdate={onUpdate} />}
      <div style={{ marginTop: needsReview ? '0.875rem' : 0 }}>
        {/* Documents: an AI engine's own PDFs, or Applaut's templates for good Basic matches. */}
        <JobActions opp={opp} showDocuments={category === 'good' || opp.is_private || !!opp.routine} onTracked={onTracked} />
      </div>
    </div>
  )
}

const selectStyle: React.CSSProperties = { width: 'auto', fontSize: '0.8rem', padding: '0.4rem 2rem 0.4rem 0.75rem' }

const MATCH_LABELS: Record<MatchFilter, string> = {
  all: 'All matches',
  good: 'Good matches',
  near_miss: 'Near misses',
  below: 'Below threshold',
  unscored: 'Not yet scored',
}

const VALID_MATCH_FILTERS: MatchFilter[] = ['all', 'good', 'near_miss', 'below', 'unscored']

type StateTab = TrackingState | 'all'
const STATE_TABS: { id: StateTab; label: string }[] = [
  { id: 'open', label: 'To review' },
  { id: 'applied', label: 'Applied' },
  { id: 'unavailable', label: 'Not available' },
  { id: 'all', label: 'All' },
]
const VALID_STATES: StateTab[] = ['open', 'applied', 'unavailable', 'all']

function SectionHeading({ text }: { text: string }) {
  return (
    <p style={{ margin: '0.75rem 0 0.125rem', fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
      {text}
    </p>
  )
}

export default function Opportunities() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialMatch = searchParams.get('match') as MatchFilter | null
  const initialState = searchParams.get('state') as StateTab | null

  const [items, setItems] = useState<Opportunity[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [goodThreshold, setGoodThreshold] = useState(85)
  const [nearMissThreshold, setNearMissThreshold] = useState(70)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterCountry, setFilterCountry] = useState('')
  const [filterEngine, setFilterEngine] = useState<EngineFilter | ''>('')
  const [engine, setEngine] = useState<JobEngine | null>(null)
  const [filterMatch, setFilterMatch] = useState<MatchFilter>(
    initialMatch && VALID_MATCH_FILTERS.includes(initialMatch) ? initialMatch : 'all'
  )
  const [stateTab, setStateTab] = useState<StateTab>(
    initialState && VALID_STATES.includes(initialState) ? initialState : 'open'
  )
  const [counts, setCounts] = useState<Record<StateTab, number> | null>(null)
  const PAGE_SIZE = 20

  const syncParams = (m: MatchFilter, st: StateTab) => {
    const params: Record<string, string> = {}
    if (m !== 'all') params.match = m
    if (st !== 'open') params.state = st
    setSearchParams(params)
  }
  const updateMatchFilter = (m: MatchFilter) => {
    setFilterMatch(m)
    syncParams(m, stateTab)
  }
  const updateStateTab = (st: StateTab) => {
    setStateTab(st)
    syncParams(filterMatch, st)
  }

  // Keep a job where it is after an action (so Undo is one click away); the
  // tab counts move at once, the list itself on the next load.
  const onTracked = (opp: Opportunity, tracking: Tracking) => {
    const from = opp.tracking.state
    setItems(prev => prev.map(o => o.id === opp.id ? { ...o, tracking } : o))
    if (from !== tracking.state) {
      setCounts(c => c ? { ...c, [from]: Math.max(0, c[from] - 1), [tracking.state]: c[tracking.state] + 1 } : c)
    }
  }

  const load = async (p = page) => {
    setLoading(true)
    try {
      const res = await listOpportunities({
        page: p,
        page_size: PAGE_SIZE,
        source: filterSource || undefined,
        country_code: filterCountry || undefined,
        match: filterMatch,
        engine: filterEngine || undefined,
        state: stateTab,
      })
      setItems(res.items)
      setTotal(res.total)
      setCounts(res.counts)
      setGoodThreshold(res.good_threshold)
      setNearMissThreshold(res.near_miss_threshold)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(1); setPage(1) }, [filterSource, filterCountry, filterMatch, filterEngine, stateTab])
  useEffect(() => { getMyProfile().then(p => setEngine(p.job_engine)).catch(() => setEngine('basic')) }, [])
  const isBasic = engine === 'basic'

  const discover = async () => {
    setRunning(true)
    setMessage('')
    try {
      const res = await runDiscovery()
      setMessage(res.message)
      load(1); setPage(1)
    } catch (err: any) {
      setMessage(apiErrorMessage(err, 'Discovery failed.'))
    } finally {
      setRunning(false)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div style={{ maxWidth: '760px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.75rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, color: 'var(--text-1)' }}>Opportunities</h1>
          {counts && <p style={{ color: 'var(--text-2)', fontSize: '0.825rem', marginTop: '0.2rem' }}>{counts.open} to review · {counts.applied} applied</p>}
        </div>
        {isBasic ? (
          <button
            onClick={discover}
            disabled={running}
            style={{ padding: '0.5rem 1.25rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500, opacity: running ? 0.7 : 1, whiteSpace: 'nowrap' }}
          >
            {running ? 'Searching & scoring…' : 'Run discovery'}
          </button>
        ) : engine && (
          <span style={{ fontSize: '0.8rem', color: 'var(--text-2)' }}>
            Jobs come from <strong style={{ color: 'var(--text-1)' }}>{JOB_ENGINE_LABELS[engine]}</strong>
          </span>
        )}
      </div>

      {message && (
        <div style={{ padding: '0.75rem 1rem', background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
          <p style={{ color: 'var(--success)', fontSize: '0.85rem', margin: 0 }}>{message}</p>
        </div>
      )}

      <div role="tablist" style={{ display: 'flex', gap: '0.25rem', marginBottom: '1rem', borderBottom: '1px solid var(--border)', overflowX: 'auto', overflowY: 'hidden', scrollbarWidth: 'none' }}>
        {STATE_TABS.map(t => {
          const active = stateTab === t.id
          return (
            <button key={t.id} role="tab" aria-selected={active} onClick={() => updateStateTab(t.id)}
              style={{
                padding: '0.55rem 0.875rem', background: 'none', border: 'none', cursor: 'pointer', whiteSpace: 'nowrap',
                borderBottom: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
                color: active ? 'var(--text-1)' : 'var(--text-2)', fontWeight: active ? 600 : 400, fontSize: '0.85rem',
              }}>
              {t.label}{counts ? <span style={{ marginLeft: '0.35rem', color: 'var(--text-3)', fontVariantNumeric: 'tabular-nums' }}>{counts[t.id]}</span> : null}
            </button>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: '0.625rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        <select value={filterMatch} onChange={e => updateMatchFilter(e.target.value as MatchFilter)} style={selectStyle}>
          {(Object.keys(MATCH_LABELS) as MatchFilter[]).map(m => (
            <option key={m} value={m}>{MATCH_LABELS[m]}</option>
          ))}
        </select>
        {engine && !isBasic && (
          <select value={filterEngine} onChange={e => setFilterEngine(e.target.value as EngineFilter | '')} style={selectStyle}>
            <option value="">All engines</option>
            <option value={engine}>{JOB_ENGINE_LABELS[engine]}</option>
            <option value="basic">{JOB_ENGINE_LABELS.basic}</option>
          </select>
        )}
        <select value={filterSource} onChange={e => setFilterSource(e.target.value)} style={selectStyle}>
          <option value="">All sources</option>
          <option value="greenhouse">Greenhouse</option>
          <option value="lever">Lever</option>
          <option value="ashby">Ashby</option>
          <option value="personio">Personio</option>
        </select>
        <select value={filterCountry} onChange={e => setFilterCountry(e.target.value)} style={selectStyle}>
          <option value="">All countries</option>
          <option value="DE">Germany</option>
          <option value="NL">Netherlands</option>
          <option value="FR">France</option>
          <option value="AT">Austria</option>
          <option value="CH">Switzerland</option>
          <option value="BE">Belgium</option>
          <option value="ES">Spain</option>
          <option value="IT">Italy</option>
          <option value="PT">Portugal</option>
          <option value="PL">Poland</option>
          <option value="SE">Sweden</option>
          <option value="NO">Norway</option>
          <option value="DK">Denmark</option>
          <option value="FI">Finland</option>
          <option value="IE">Ireland</option>
          <option value="CZ">Czech Republic</option>
          <option value="RO">Romania</option>
          <option value="HU">Hungary</option>
          <option value="US">United States</option>
        </select>
        {isBasic && (
          <select value="rule_based" onChange={() => {}} style={selectStyle} title="AI scoring is a premium feature — coming soon">
            <option value="rule_based">Rule-based scoring</option>
            <option value="ai" disabled>AI scoring (premium — coming soon)</option>
          </select>
        )}
      </div>

      {loading ? (
        <p style={{ color: 'var(--text-2)' }}>Loading…</p>
      ) : items.length === 0 ? (
        <div style={{ padding: '3rem', textAlign: 'center', border: '1px dashed var(--border-strong)', borderRadius: 'var(--radius)' }}>
          <p style={{ fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-1)' }}>
            {stateTab === 'open' ? 'Nothing left to review' : stateTab === 'applied' ? 'No applications marked yet' : stateTab === 'unavailable' ? 'No jobs marked not available' : 'No jobs found yet'}
          </p>
          <p style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>
            {stateTab === 'applied' ? 'Press "Mark as applied" on a job once you have applied.'
              : stateTab === 'unavailable' ? 'Jobs you mark as closed or impossible to apply to land here.'
              : isBasic || !engine
              ? 'Click "Run discovery" to search across all job boards — new jobs are scored automatically.'
              : `New jobs appear here after ${JOB_ENGINE_LABELS[engine]} runs.`}
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
          {items.map((opp, i) => {
            // The list is sorted routine-first; label the groups when both are on this page.
            const hasRoutine = items.some(o => o.routine)
            const startsGroup = hasRoutine && (i === 0 || !!items[i - 1].routine !== !!opp.routine)
            return (
              <div key={opp.id} style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                {startsGroup && <SectionHeading text={opp.routine ? 'From your Claude routine' : 'Other jobs (Applaut Basic)'} />}
                <OpportunityCard
                  opp={opp}
                  goodThreshold={goodThreshold}
                  nearMissThreshold={nearMissThreshold}
                  onUpdate={() => load()}
                  onTracked={onTracked}
                />
              </div>
            )
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.75rem', marginTop: '1.5rem' }}>
          <button
            onClick={() => { const p = page - 1; setPage(p); load(p) }}
            disabled={page === 1}
            style={{ padding: '0.375rem 0.875rem', background: 'var(--bg-surface)', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', color: 'var(--text-1)', opacity: page === 1 ? 0.4 : 1 }}
          >
            ←
          </button>
          <span style={{ fontSize: '0.825rem', color: 'var(--text-2)' }}>Page {page} of {totalPages}</span>
          <button
            onClick={() => { const p = page + 1; setPage(p); load(p) }}
            disabled={page === totalPages}
            style={{ padding: '0.375rem 0.875rem', background: 'var(--bg-surface)', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', color: 'var(--text-1)', opacity: page === totalPages ? 0.4 : 1 }}
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
