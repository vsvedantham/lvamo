import { useEffect, useState } from 'react'
import { API_BASE } from '../api/client'
import { createToken, listTokens, revokeToken, timeAgo, type CreatedToken, type IngestToken } from '../api/evidence'
import type { Claim } from '../api/github'
import { apiErrorMessage, type Project } from '../api/projects'
import { Banner, Button, Card, Field, hintStyle } from './ui'

const code: React.CSSProperties = {
  margin: 0, padding: '0.85rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-xs)', fontSize: '0.75rem', overflowX: 'auto', lineHeight: 1.55,
}

function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false)
  return (
    <button type="button" onClick={() => navigator.clipboard.writeText(text).then(() => setDone(true))}
      style={{ background: 'none', border: 'none', color: 'var(--accent)', fontSize: '0.8rem', cursor: 'pointer', padding: 0 }}>
      {done ? 'Copied ✓' : label}
    </button>
  )
}

function exampleItems(claims: Claim[]): string {
  const metrics = claims.filter(c => c.metric_key).map(c => c.metric_key as string)
  const lines = (metrics.length ? metrics : ['your_metric'])
    .map(k => `  {"key": "${k}", "kind": "metric", "value_num": 12.3, "unit": "%"}`)
  lines.push('  {"key": "pipeline", "kind": "run", "value_text": "success", "payload": {"tests_passed": 48, "tests_total": 48}}')
  return `[\n${lines.join(',\n')}\n]`
}

function workflowStep(): string {
  return `      - name: Report evidence to ProSho
        if: always()
        env:
          PROSHO_TOKEN: \${{ secrets.PROSHO_TOKEN }}
        run: |
          jq -n --arg sha "$GITHUB_SHA" --slurpfile items prosho-evidence.json \\
            '{commit_sha: $sha, items: $items[0]}' |
          curl -fsS -X POST "${API_BASE}/ingest/evidence" \\
            -H "Authorization: Bearer $PROSHO_TOKEN" \\
            -H "Content-Type: application/json" --data-binary @-`
}

export default function EvidenceCard({ project, claims }: { project: Project; claims: Claim[] }) {
  const [tokens, setTokens] = useState<IngestToken[] | null>(null)
  const [created, setCreated] = useState<CreatedToken | null>(null)
  const [label, setLabel] = useState('GitHub Actions')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listTokens(project.id).then(setTokens).catch(err => setError(apiErrorMessage(err)))
  }, [project.id])

  const create = async () => {
    setBusy(true); setError('')
    try {
      const t = await createToken(project.id, label.trim())
      setCreated(t)
      setTokens(ts => [t, ...(ts ?? [])])
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (t: IngestToken) => {
    if (!window.confirm(`Revoke "${t.label}" (${t.token_prefix}…)? CI using it will stop reporting.`)) return
    try {
      const updated = await revokeToken(project.id, t.id)
      setTokens(ts => ts?.map(x => (x.id === t.id ? updated : x)) ?? null)
      if (created?.id === t.id) setCreated(null)
    } catch (err) {
      setError(apiErrorMessage(err))
    }
  }

  return (
    <Card title="Evidence from CI">
      {error && <Banner kind="error">{error}</Banner>}
      <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', lineHeight: 1.6, marginBottom: '1rem' }}>
        Your pipeline sends results (metrics, test runs) to ProSho. A claim with a <code>metric</code> in prosho.yaml then shows
        <strong> Met</strong> or <strong>Not met</strong> from the latest value — nobody types the status in.
      </p>

      {created && (
        <div style={{ marginBottom: '1.25rem' }}>
          <Banner kind="success">Token created. Copy it now — it won’t be shown again.</Banner>
          <pre style={code}>{created.token}</pre>
          <div style={{ marginTop: '0.4rem' }}><CopyButton text={created.token} label="Copy token" /></div>
          <ol style={{ margin: '1rem 0 0', paddingLeft: '1.1rem', fontSize: '0.85rem', lineHeight: 1.7, color: 'var(--text-1)' }}>
            <li>In your repo on GitHub: <em>Settings → Secrets and variables → Actions → New repository secret</em>, name <code>PROSHO_TOKEN</code>, paste the token.</li>
            <li>Have your pipeline write its results to <code>prosho-evidence.json</code>:
              <pre style={{ ...code, marginTop: '0.4rem' }}>{exampleItems(claims)}</pre>
            </li>
            <li>Add this step at the end of the workflow job:
              <pre style={{ ...code, marginTop: '0.4rem' }}>{workflowStep()}</pre>
              <CopyButton text={workflowStep()} label="Copy step" />
            </li>
          </ol>
        </div>
      )}

      <form onSubmit={e => { e.preventDefault(); create() }} style={{ display: 'flex', gap: '0.6rem', alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <div style={{ flex: '1 1 220px' }}>
          <Field label="New token label"><input value={label} onChange={e => setLabel(e.target.value)} maxLength={100} /></Field>
        </div>
        <Button type="submit" disabled={busy || label.trim() === ''}>{busy ? 'Creating…' : 'Create token'}</Button>
      </form>

      {tokens && tokens.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {tokens.map(t => (
            <li key={t.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', padding: '0.6rem 0.8rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', opacity: t.revoked_at ? 0.55 : 1 }}>
              <span style={{ fontSize: '0.85rem', minWidth: 0 }}>
                <strong>{t.label}</strong> <code style={{ color: 'var(--text-2)' }}>{t.token_prefix}…</code>
                <span style={{ ...hintStyle, display: 'block' }}>
                  {t.revoked_at ? `Revoked ${timeAgo(t.revoked_at)}` : `Last used ${timeAgo(t.last_used_at)}`}
                </span>
              </span>
              {!t.revoked_at && <Button variant="secondary" onClick={() => revoke(t)}>Revoke</Button>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
