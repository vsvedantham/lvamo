import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getOpportunity, type Assessment, type OpportunityDetail } from '../api/opportunity'
import { JOB_ENGINE_LABELS } from '../api/profile'

export default function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [opp, setOpp] = useState<OpportunityDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    getOpportunity(id)
      .then(setOpp)
      .catch(() => setError('Opportunity not found.'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <p style={{ color: '#6b7280' }}>Loading…</p>
  if (error || !opp) return <p style={{ color: '#dc2626' }}>{error || 'Not found.'}</p>

  return (
    <div style={{ maxWidth: '680px', margin: '0 auto' }}>
      <Link to="/applaut/opportunities" style={{ fontSize: '0.875rem', color: '#6b7280', textDecoration: 'none', display: 'inline-block', marginBottom: '1.25rem' }}>← Back to opportunities</Link>

      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.25rem' }}>{opp.title}</h1>
      <p style={{ color: '#6b7280', marginBottom: '1rem' }}>{opp.company_name}</p>

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
        {opp.location_raw && <Chip label={`📍 ${opp.location_raw}`} />}
        {opp.remote_option && <Chip label={opp.remote_option} />}
        {opp.employment_type && <Chip label={opp.employment_type} />}
        {opp.source && <Chip label={opp.assessment ? `Found by ${JOB_ENGINE_LABELS[opp.assessment.engine]}` : opp.source} />}
        {opp.posted_at && <Chip label={`Posted ${new Date(opp.posted_at).toLocaleDateString()}`} />}
      </div>

      {(opp.salary_min || opp.salary_max) && (
        <p style={{ marginBottom: '1rem', fontWeight: 500 }}>
          Salary: {opp.salary_currency || ''} {opp.salary_min?.toLocaleString() ?? '?'} – {opp.salary_max?.toLocaleString() ?? '?'}
        </p>
      )}

      {opp.assessment && <AssessmentPanel assessment={opp.assessment} />}

      {opp.description && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>Description</h2>
          <div style={{ fontSize: '0.9rem', lineHeight: 1.7, color: 'var(--text-1)', whiteSpace: 'pre-wrap' }}>
            {opp.description.replace(/<[^>]+>/g, '')}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
      <Link
        to={`/applaut/documents/${opp.id}`}
        style={{ display: 'inline-block', padding: '0.625rem 1.5rem', border: '1px solid var(--border-strong)', color: 'var(--text-1)', borderRadius: '6px', textDecoration: 'none', fontSize: '0.9rem' }}
      >
        {opp.is_private ? 'CV & cover letter →' : 'Documents →'}
      </Link>
      {opp.application_url && (
        <a
          href={opp.application_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ display: 'inline-block', padding: '0.625rem 1.5rem', background: '#111827', color: '#fff', borderRadius: '6px', textDecoration: 'none', fontSize: '0.9rem' }}
        >
          View & apply →
        </a>
      )}
      </div>
    </div>
  )
}

function AssessmentPanel({ assessment }: { assessment: Assessment }) {
  return (
    <section style={{ marginBottom: '1.5rem', padding: '1rem 1.125rem', border: '1px solid var(--border)', borderRadius: '8px', background: 'var(--bg-surface)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>AI assessment</h2>
        {assessment.match_score != null && (
          <span style={{ fontSize: '1.25rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{assessment.match_score}% match</span>
        )}
      </div>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-2)', margin: '0 0 0.875rem' }}>
        Match % = the job's must-have skills found in your profile. By {JOB_ENGINE_LABELS[assessment.engine]},
        first seen {new Date(assessment.first_seen_at).toLocaleDateString()}
        {assessment.times_seen > 1 ? `, still listed (seen ${assessment.times_seen} times, last ${new Date(assessment.last_seen_at).toLocaleDateString()})` : ''}.
      </p>

      {assessment.flags.length > 0 && (
        <ul style={{ margin: '0 0 0.875rem', padding: '0.625rem 0.875rem 0.625rem 1.75rem', background: 'var(--warn-bg)', border: '1px solid var(--warn-border)', borderRadius: '6px', color: 'var(--text-1)', fontSize: '0.85rem' }}>
          {assessment.flags.map(f => <li key={f}>{f}</li>)}
        </ul>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.875rem' }}>
        <SkillList title="Must-haves you have" items={assessment.matched_skills} color="var(--success)" mark="✓" />
        <SkillList title="Must-haves you're missing" items={assessment.missing_skills} color="var(--danger)" mark="✗" />
      </div>

      {(assessment.german_required || assessment.seniority) && (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-2)', margin: '0.875rem 0 0' }}>
          {assessment.german_required && <>German required: <strong>{assessment.german_required}</strong>. </>}
          {assessment.seniority && <>Seniority: <strong>{assessment.seniority}</strong>.</>}
        </p>
      )}
      {assessment.notes && (
        <p style={{ fontSize: '0.85rem', color: 'var(--text-1)', margin: '0.875rem 0 0', whiteSpace: 'pre-wrap' }}>{assessment.notes}</p>
      )}
    </section>
  )
}

function SkillList({ title, items, color, mark }: { title: string; items: string[]; color: string; mark: string }) {
  return (
    <div>
      <h3 style={{ fontSize: '0.8rem', fontWeight: 600, margin: '0 0 0.375rem', color: 'var(--text-2)' }}>{title} ({items.length})</h3>
      {items.length === 0 ? (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-3)', margin: 0 }}>None</p>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
          {items.map(s => <li key={s} style={{ fontSize: '0.85rem' }}><span style={{ color, marginRight: '0.4rem' }}>{mark}</span>{s}</li>)}
        </ul>
      )}
    </div>
  )
}

function Chip({ label }: { label: string }) {
  return (
    <span style={{ padding: '0.25rem 0.75rem', border: '1px solid #e5e7eb', borderRadius: '999px', fontSize: '0.8rem', color: 'var(--text-2)' }}>
      {label}
    </span>
  )
}
