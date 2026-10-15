import { useEffect, useState } from 'react'
import { apiErrorMessage, type Project } from '../api/projects'
import { describeTarget, listClaims, MANUAL_STATUS_LABEL, setClaimStatus, type Claim, type ManualStatus } from '../api/github'
import { Banner, Card, hintStyle } from './ui'

export default function ClaimsCard({ project }: { project: Project }) {
  const [claims, setClaims] = useState<Claim[] | null>(null)
  const [error, setError] = useState('')

  // Claims change whenever prosho.yaml syncs.
  useEffect(() => {
    listClaims(project.id).then(setClaims).catch(err => setError(apiErrorMessage(err)))
  }, [project.id, project.manifest_synced_at, project.repo_full_name])

  const update = async (c: Claim, status: ManualStatus) => {
    setError('')
    try {
      const saved = await setClaimStatus(project.id, c.id, status)
      setClaims(cs => cs?.map(x => (x.id === saved.id ? saved : x)) ?? null)
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  if (!project.manifest_managed) return null

  return (
    <Card title="Claims" aside={<span style={hintStyle}>From prosho.yaml</span>}>
      {error && <Banner kind="error">{error}</Banner>}
      {claims?.length === 0 && <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>No claims yet — add a <code>claims:</code> list to prosho.yaml.</p>}
      <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {claims?.map(c => (
          <li key={c.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', padding: '0.85rem 0.95rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)' }}>
            <div style={{ flex: '1 1 260px', minWidth: 0 }}>
              <p style={{ fontSize: '0.9rem', lineHeight: 1.5, overflowWrap: 'anywhere' }}>{c.text}</p>
              <p style={{ ...hintStyle, marginTop: '0.25rem' }}>
                {c.metric_key
                  ? <>Measured: <code>{c.metric_key}</code> {describeTarget(c)}</>
                  : 'Self-reported — you set the status'}
              </p>
            </div>
            {c.metric_key ? (
              <span style={{ alignSelf: 'center', padding: '0.2rem 0.6rem', borderRadius: '999px', fontSize: '0.72rem', fontWeight: 600, border: '1px solid var(--border-strong)', color: 'var(--text-2)' }}>
                Awaiting evidence
              </span>
            ) : (
              <select value={c.manual_status} onChange={e => update(c, e.target.value as ManualStatus)} aria-label={`Status of "${c.text}"`} style={{ width: 'auto', alignSelf: 'center' }}>
                {(Object.keys(MANUAL_STATUS_LABEL) as ManualStatus[]).map(s => <option key={s} value={s}>{MANUAL_STATUS_LABEL[s]}</option>)}
              </select>
            )}
          </li>
        ))}
      </ol>
    </Card>
  )
}
