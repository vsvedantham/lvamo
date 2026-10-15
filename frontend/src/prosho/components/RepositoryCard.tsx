import { useEffect, useState } from 'react'
import { apiErrorMessage, type Project } from '../api/projects'
import { connectRepo, disconnectRepo, getAvailableRepos, syncNow, type AvailableRepos } from '../api/github'
import { Banner, Button, Card, hintStyle } from './ui'

const linkStyle = { color: 'var(--accent)', fontSize: '0.85rem' }

function starterManifest(p: Project): string {
  const type = p.project_type === 'frontend' ? 'frontend' : 'data-science'
  const section = p.project_type === 'frontend'
    ? `frontend:\n  urls_to_screenshot:\n    - https://your-site.example\n`
    : `data:\n  sources:\n    - name: Where your data comes from\n      url: https://example.org/dataset\n      licence: CC BY 4.0\n`
  return `version: 1
title: ${p.title}
type: ${type}
summary: One sentence on what the project does
problem: >
  The problem it tackles, in two or three sentences.
claims:
  - id: first-claim
    text: Something the project promises, e.g. "Covers five countries"
${section}`
}

function when(iso: string | null) {
  return iso ? new Date(iso).toLocaleString() : '—'
}

export default function RepositoryCard({ project, onChange }: { project: Project; onChange: (p: Project) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const connected = project.repo_full_name !== null && !project.repo_access_lost

  const run = async (fn: () => Promise<Project>) => {
    setBusy(true)
    setError('')
    try {
      onChange(await fn())
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="GitHub repository">
      {error && <Banner kind="error">{error}</Banner>}
      {connected ? (
        <Connected project={project} busy={busy}
          onSync={() => run(() => syncNow(project.id))}
          onDisconnect={() => {
            if (window.confirm('Disconnect this repo? Claims are hidden until you connect a repo again.')) {
              run(() => disconnectRepo(project.id))
            }
          }}
        />
      ) : (
        <Picker project={project} busy={busy} onConnect={repoId => run(() => connectRepo(project.id, repoId))} />
      )}
    </Card>
  )
}

function Connected({ project, busy, onSync, onDisconnect }: { project: Project; busy: boolean; onSync: () => void; onDisconnect: () => void }) {
  const repoUrl = `https://github.com/${project.repo_full_name}`
  const errors = project.manifest_errors ?? []
  const missingFile = errors.some(e => e.message.startsWith('No prosho.yaml'))
  // Errors with no line/path aren't about the file's contents (GitHub access, network…).
  const fileProblem = errors.some(e => e.line !== null || e.path)
  const fileUrl = (line: number | null) =>
    `${repoUrl}/blob/${project.manifest_sha ?? 'HEAD'}/prosho.yaml${line ? `#L${line}` : ''}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
      <p style={{ fontSize: '0.9rem' }}>
        <a href={repoUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--text-1)', fontWeight: 600 }}>{project.repo_full_name}</a>
      </p>
      <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '0.3rem 1rem', fontSize: '0.825rem', color: 'var(--text-2)' }}>
        <dt>Last checked</dt><dd style={{ color: 'var(--text-1)' }}>{when(project.manifest_checked_at)}</dd>
        <dt>Last good sync</dt><dd style={{ color: 'var(--text-1)' }}>{when(project.manifest_synced_at)}</dd>
        {project.manifest_sha && (<><dt>Commit</dt><dd><a href={`${repoUrl}/commit/${project.manifest_sha}`} target="_blank" rel="noreferrer" style={linkStyle}><code>{project.manifest_sha.slice(0, 7)}</code></a></dd></>)}
      </dl>

      {errors.length === 0 && project.manifest_synced_at && (
        <Banner kind="success">prosho.yaml is valid. Every push to the default branch updates the page.</Banner>
      )}
      {errors.length > 0 && (
        <div role="alert" style={{ padding: '0.8rem 0.9rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)' }}>
          <p style={{ color: 'var(--danger)', fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.4rem' }}>
            {missingFile ? 'prosho.yaml not found' : fileProblem ? 'prosho.yaml has problems' : 'Last sync failed'}{project.manifest_synced_at ? ' — the page still shows the last good version' : ''}
          </p>
          <ul style={{ margin: 0, paddingLeft: '1.1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            {errors.map((e, i) => (
              <li key={i} style={{ fontSize: '0.825rem', color: 'var(--text-1)', lineHeight: 1.5 }}>
                {e.line !== null && <a href={fileUrl(e.line)} target="_blank" rel="noreferrer" style={linkStyle}>line {e.line}</a>}
                {e.line !== null && e.path && ' · '}
                {e.path && <code>{e.path}</code>}
                {(e.line !== null || e.path) && ': '}
                {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {missingFile && <Starter project={project} />}

      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        <Button onClick={onSync} disabled={busy}>{busy ? 'Working…' : 'Sync now'}</Button>
        <Button variant="secondary" onClick={onDisconnect} disabled={busy}>Disconnect</Button>
      </div>
    </div>
  )
}

function Starter({ project }: { project: Project }) {
  const text = starterManifest(project)
  const [copied, setCopied] = useState(false)
  return (
    <div>
      <p style={{ ...hintStyle, marginBottom: '0.4rem' }}>Add this as <code>prosho.yaml</code> at the root of the repo, edit it, push — then press Sync now.</p>
      <pre style={{ margin: 0, padding: '0.85rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', fontSize: '0.78rem', overflowX: 'auto', lineHeight: 1.55 }}>{text}</pre>
      <button
        type="button"
        onClick={() => navigator.clipboard.writeText(text).then(() => setCopied(true))}
        style={{ marginTop: '0.5rem', background: 'none', border: 'none', color: 'var(--accent)', fontSize: '0.8rem', cursor: 'pointer', padding: 0 }}
      >
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
    </div>
  )
}

function Picker({ project, busy, onConnect }: { project: Project; busy: boolean; onConnect: (repoId: number) => void }) {
  const [avail, setAvail] = useState<AvailableRepos | null>(null)
  const [loadError, setLoadError] = useState('')
  const [repoId, setRepoId] = useState<number | ''>('')

  useEffect(() => {
    getAvailableRepos(project.id).then(setAvail).catch(err => setLoadError(apiErrorMessage(err)))
  }, [project.id])

  if (loadError) return <Banner kind="error">{loadError}</Banner>
  if (!avail) return <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>Checking GitHub…</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
      {project.repo_access_lost && (
        <Banner kind="error">ProSho lost access to {project.repo_full_name} (the app was uninstalled or the repo removed from it). Pick the repo again below.</Banner>
      )}
      {!avail.installed ? (
        <>
          <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', lineHeight: 1.6 }}>
            Install the ProSho GitHub App on your account and choose the project&apos;s repo. ProSho can only <strong>read</strong> it — it
            looks for <code>prosho.yaml</code> and listens for pushes. It never writes to your repo.
          </p>
          <div><a href={avail.install_url} style={{ display: 'inline-block', padding: '0.6rem 1.1rem', background: 'var(--accent)', color: '#fff', borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.875rem', textDecoration: 'none' }}>Install on GitHub</a></div>
          <p style={hintStyle}>Install it on your personal account — organisation accounts aren&apos;t supported in the beta.</p>
        </>
      ) : (
        <>
          {avail.repos.length === 0 ? (
            <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>The app is installed but can&apos;t see any repos yet.</p>
          ) : (
            <form onSubmit={e => { e.preventDefault(); if (repoId !== '') onConnect(repoId) }} style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
              <select value={repoId} onChange={e => setRepoId(e.target.value === '' ? '' : Number(e.target.value))} style={{ flex: '1 1 260px', width: 'auto' }} aria-label="Repository">
                <option value="">Choose a repo…</option>
                {avail.repos.map(r => <option key={r.id} value={r.id}>{r.full_name}{r.private ? ' (private)' : ''}</option>)}
              </select>
              <Button type="submit" disabled={repoId === '' || busy}>{busy ? 'Connecting…' : 'Connect'}</Button>
            </form>
          )}
          {avail.manage_url && (
            <p style={hintStyle}>Repo missing? <a href={avail.manage_url} target="_blank" rel="noreferrer" style={linkStyle}>Choose which repos ProSho can read on GitHub</a>, then reload this page.</p>
          )}
        </>
      )}
    </div>
  )
}
