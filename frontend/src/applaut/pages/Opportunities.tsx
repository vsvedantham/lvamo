import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { createApplication } from '../api/applications'
import {
  effectiveScore,
  listOpportunities,
  runDiscovery,
  type Assessment,
  type EngineFilter,
  type MatchFilter,
  type NearMissKeyword,
  type Opportunity,
} from '../api/opportunity'
import { getMyProfile, JOB_ENGINE_LABELS, type JobEngine } from '../api/profile'
import { decideNearMiss } from '../api/scoring'

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

function GoodMatchActions({ opp }: { opp: Opportunity }) {
  const [starting, setStarting] = useState(false)
  const [applicationId, setApplicationId] = useState<string | null>(null)
  const navigate = useNavigate()

  const startApplication = async () => {
    setStarting(true)
    try {
      const app = await createApplication(opp.id, opp.score?.id)
      setApplicationId(app.id)
    } catch (err: any) {
      if (err.response?.status === 409) navigate('/applaut/applications')
    } finally {
      setStarting(false)
    }
  }

  return (
    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
      <button
        onClick={() => navigate(`/applaut/documents/${opp.id}`)}
        style={{ padding: '0.35rem 0.875rem', background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-1)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.8rem' }}
      >
        {opp.is_private ? 'View documents →' : 'Generate documents →'}
      </button>
      {applicationId ? (
        <Link to="/applaut/applications" style={{ padding: '0.35rem 0.875rem', background: 'var(--success-bg)', color: 'var(--success)', border: '1px solid var(--success-border)', borderRadius: 'var(--radius-xs)', fontSize: '0.8rem', textDecoration: 'none' }}>
          Application started ✓
        </Link>
      ) : (
        <button
          onClick={startApplication}
          disabled={starting}
          style={{ padding: '0.35rem 0.875rem', background: 'var(--blue-bg)', color: 'var(--blue)', border: '1px solid var(--blue-border)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.8rem', opacity: starting ? 0.7 : 1 }}
        >
          {starting ? 'Starting…' : 'Start application'}
        </button>
      )}
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

function OpportunityCard({ opp, goodThreshold, nearMissThreshold, onUpdate }: {
  opp: Opportunity
  goodThreshold: number
  nearMissThreshold: number
  onUpdate: () => void
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
      transition: 'border-color 0.15s',
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
            <Badge text={SOURCE_LABELS[opp.source] ?? opp.source} color="var(--accent)" />
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

      {/* An AI engine only brings in jobs it judged worth applying to. */}
      {(category === 'good' || opp.is_private) && <GoodMatchActions opp={opp} />}
      {needsReview && <NearMissPanel opp={opp} goodThreshold={goodThreshold} onUpdate={onUpdate} />}
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

export default function Opportunities() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialMatch = searchParams.get('match') as MatchFilter | null

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
  const PAGE_SIZE = 20

  const updateMatchFilter = (m: MatchFilter) => {
    setFilterMatch(m)
    setSearchParams(m === 'all' ? {} : { match: m })
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
      })
      setItems(res.items)
      setTotal(res.total)
      setGoodThreshold(res.good_threshold)
      setNearMissThreshold(res.near_miss_threshold)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(1); setPage(1) }, [filterSource, filterCountry, filterMatch, filterEngine])
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
      setMessage(err.response?.data?.detail ?? 'Discovery failed.')
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
          {total > 0 && <p style={{ color: 'var(--text-2)', fontSize: '0.825rem', marginTop: '0.2rem' }}>{total} jobs found</p>}
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
          <p style={{ fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-1)' }}>No jobs found yet</p>
          <p style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>
            {isBasic || !engine
              ? 'Click "Run discovery" to search across all job boards — new jobs are scored automatically.'
              : `New jobs appear here after ${JOB_ENGINE_LABELS[engine]} runs.`}
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
          {items.map(opp => (
            <OpportunityCard
              key={opp.id}
              opp={opp}
              goodThreshold={goodThreshold}
              nearMissThreshold={nearMissThreshold}
              onUpdate={() => load()}
            />
          ))}
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
