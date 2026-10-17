import { useEffect, useState } from 'react'
import { checkSourcesNow, getDataModule, listEvidence, timeAgo, formatValue, type DataModule, type Evidence } from '../api/evidence'
import { apiErrorMessage, type Project } from '../api/projects'
import { SourcesList } from './DataModulePanels'
import { Banner, Button, Card, hintStyle } from './ui'

export function DataSourcesCard({ project }: { project: Project }) {
  const [data, setData] = useState<DataModule | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getDataModule(project.id).then(setData).catch(err => setError(apiErrorMessage(err)))
  }, [project.id, project.manifest_synced_at])

  if (project.project_type !== 'data_science' || !data) return null

  const check = async () => {
    setBusy(true); setError('')
    try { setData(await checkSourcesNow(project.id)) } catch (err) { setError(apiErrorMessage(err)) } finally { setBusy(false) }
  }

  return (
    <Card title="Data sources" aside={<span style={hintStyle}>Checked daily at 05:00 UTC</span>}>
      {error && <Banner kind="error">{error}</Banner>}
      {data.sources.length === 0 ? (
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', lineHeight: 1.6 }}>
          List the datasets your project depends on under <code>data: sources:</code> in prosho.yaml (name, url, licence).
          LVAMO checks each one daily and shows on your page whether it&apos;s still reachable.
        </p>
      ) : (
        <>
          <SourcesList sources={data.sources} />
          <div style={{ marginTop: '0.9rem' }}><Button variant="secondary" onClick={check} disabled={busy}>{busy ? 'Checking…' : 'Check now'}</Button></div>
        </>
      )}
    </Card>
  )
}

export function RecentEvidenceCard({ project }: { project: Project }) {
  const [items, setItems] = useState<Evidence[] | null>(null)
  useEffect(() => { listEvidence(project.id, 20).then(setItems).catch(() => setItems([])) }, [project.id])
  if (!items || items.length === 0) return null
  return (
    <Card title="Recent evidence" aside={<span style={hintStyle}>Latest 20</span>}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--text-2)' }}>
              {['When', 'Key', 'Value', 'From', 'Commit'].map(h => <th key={h} style={{ padding: '0.4rem 0.6rem 0.4rem 0', fontWeight: 500 }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {items.map(e => (
              <tr key={e.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '0.45rem 0.6rem 0.45rem 0', whiteSpace: 'nowrap' }}>{timeAgo(e.recorded_at)}</td>
                <td style={{ padding: '0.45rem 0.6rem 0.45rem 0' }}><code>{e.key.startsWith('source.') ? String(e.payload?.name ?? e.key) : e.key}</code></td>
                <td style={{ padding: '0.45rem 0.6rem 0.45rem 0' }}>{e.kind === 'metric' ? formatValue(e.value_num, e.unit) : e.value_text}</td>
                <td style={{ padding: '0.45rem 0.6rem 0.45rem 0', color: 'var(--text-2)' }}>{e.source === 'ci' ? 'CI' : 'LVAMO check'}</td>
                <td style={{ padding: '0.45rem 0' }}><code>{e.commit_sha?.slice(0, 7) ?? '—'}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
