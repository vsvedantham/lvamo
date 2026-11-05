import { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api/jobEngine'
import {
  getCvTemplates, getTemplatePreviewLink, removeCvTemplate, uploadCvTemplate, useCvTemplate,
  type CvTemplate, type CvTemplateState,
} from '../api/cvTemplate'
import { buttonStyle, formatWhen } from './RoutineEngineCard'

// Settings → CV template (Applaut AI): the standard template, or the user's own
// .docx CV. Applaut AI reads the upload once; the user compares their file with
// Applaut's version before switching it on.

const POLL_MS = 10_000
const card: React.CSSProperties = {
  padding: '1.25rem', background: 'var(--bg-surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius)', display: 'flex', flexDirection: 'column', gap: '0.875rem',
}
const h2: React.CSSProperties = { fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-1)' }
const h3: React.CSSProperties = { fontSize: '0.85rem', fontWeight: 600, margin: 0, color: 'var(--text-1)' }
const muted: React.CSSProperties = { fontSize: '0.8rem', color: 'var(--text-2)', margin: 0 }
const list: React.CSSProperties = { ...muted, margin: 0, paddingLeft: '1.1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }

function Report({ t }: { t: CvTemplate }) {
  const r = t.report
  const roles = r.roles ?? []
  const rows = r.rows ?? []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {(r.differences?.length ?? 0) > 0 && (
        <div role="alert" style={{ ...muted, color: 'var(--danger)' }}>
          <strong>Applaut's version doesn't match your file, so it can't be used:</strong>
          <ul style={{ ...list, color: 'var(--danger)', marginTop: '0.25rem' }}>
            {r.differences!.map((d, i) => <li key={i} style={{ overflowWrap: 'anywhere' }}>{d}</li>)}
          </ul>
        </div>
      )}
      <div>
        <h3 style={h3}>What each job's CV changes</h3>
        <ul style={{ ...list, marginTop: '0.3rem' }}>
          <li>{r.headline ? 'The headline under your name is written for the job.' : 'No headline line was found; the top of your CV stays as it is.'}</li>
          {rows.length > 0 && (
            <li>Skills: {rows.map(x => x.row ? `${x.label} (ordered for the job)` : `${x.label} (kept as uploaded: no "${x.label}" row in your master profile)`).join(' · ')}</li>
          )}
          {roles.map((x, i) => (
            <li key={i} style={{ overflowWrap: 'anywhere' }}>
              <em>{x.heading}</em>: {x.entry
                ? `bullets${x.technologies ? ' and technologies' : ''} from "${x.entry}" in your master profile, picked for the job`
                : `kept as uploaded (no matching role in your master profile)`}
            </li>
          ))}
          <li>Everything else (name, contact, dates, education, any summary) stays exactly as in your file.
            {t.pages ? ` Each CV keeps to ${t.pages} ${t.pages === 1 ? 'page' : 'pages'}, like your file.` : ''}</li>
        </ul>
      </div>
      {(r.fonts?.length ?? 0) > 0 && (
        <p style={{ ...muted, color: 'var(--warn)' }}>
          {r.fonts!.map(f => f.font).join(', ')} {r.fonts!.length === 1 ? "isn't" : "aren't"} available on Applaut's
          server, so {r.fonts!.length === 1 ? 'it is' : 'they are'} shown in a similar font. Line breaks may differ
          slightly from Word; check the PDF.
        </p>
      )}
      {(r.notes?.length ?? 0) > 0 && (
        <ul style={list}>{r.notes!.map((n, i) => <li key={i}>{n}</li>)}</ul>
      )}
    </div>
  )
}

export default function CvTemplateCard() {
  const [state, setState] = useState<CvTemplateState | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const load = () => getCvTemplates().then(setState).catch(err => setMessage(errorMessage(err, 'Could not load your template')))
  useEffect(() => { load() }, [])

  useEffect(() => {  // while Applaut AI reads the upload, check every 10 s
    if (state?.latest?.status !== 'reading') return
    const t = window.setTimeout(load, POLL_MS)
    return () => window.clearTimeout(t)
  }, [state])

  const run = async (key: string, action: () => Promise<unknown>, fallback: string, done?: string) => {
    setBusy(key); setMessage(null)
    try { await action(); await load(); if (done) setMessage(done) }
    catch (err) { setMessage(errorMessage(err, fallback)) }
    finally { setBusy(null) }
  }

  const upload = (file: File) => run('upload', () => uploadCvTemplate(file), 'Could not upload the file')

  const openPreview = async (t: CvTemplate, which: 'original' | 'rebuilt') => {
    const tab = window.open('', '_blank')  // inside the click, so popup blockers allow it
    setBusy(which); setMessage(null)
    try {
      const url = await getTemplatePreviewLink(t.id, which)
      if (tab) tab.location.href = url
      else window.location.href = url
    } catch (err) {
      tab?.close()
      setMessage(errorMessage(err, 'Could not open the PDF'))
    } finally {
      setBusy(null)
    }
  }

  const active = state?.active ?? null
  const latest = state?.latest ?? null

  return (
    <div style={card} id="cv-template">
      <div>
        <h2 style={h2}>CV template</h2>
        <p style={{ ...muted, marginTop: '0.3rem' }}>
          Applaut AI uses the standard template unless you upload your own CV as a Word file (.docx). Your layout
          stays exactly as it is: for each job only the headline under your name, the order of your skills, each
          role's bullets and its technologies line change, all from your master profile. Cover letters keep the
          standard template.
        </p>
      </div>

      {state === null ? <p style={muted}>{message ?? 'Loading…'}</p> : (
        <>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <p style={{ ...muted, color: 'var(--text-1)' }}>
              In use: <strong>{active ? `your template (${active.file_name})` : 'the standard template'}</strong>
              {active?.decided_at && <span style={muted}> · since {formatWhen(active.decided_at)}</span>}
            </p>
            {active && (
              <button type="button" disabled={busy !== null} style={buttonStyle('ghost', busy !== null)}
                onClick={() => run('stop', () => removeCvTemplate(active.id), 'Could not switch it off',
                  'Switched back to the standard template. CVs already written keep theirs.')}>
                {busy === 'stop' ? 'Switching…' : 'Use the standard template'}
              </button>
            )}
          </div>

          {latest?.status === 'reading' && (
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <p style={muted}>
                Reading <strong>{latest.file_name}</strong>…{' '}
                {latest.ahead ? `${latest.ahead} ${latest.ahead === 1 ? 'item' : 'items'} ahead in the queue. ` : ''}
                This takes a few minutes; you can leave this page.
              </p>
              <button type="button" disabled={busy !== null} style={buttonStyle('ghost', busy !== null)}
                onClick={() => run('discard', () => removeCvTemplate(latest.id), 'Could not cancel')}>Cancel</button>
            </div>
          )}

          {latest?.status === 'failed' && (
            <p role="alert" style={{ ...muted, color: 'var(--danger)', overflowWrap: 'anywhere' }}>
              Applaut couldn't make <strong>{latest.file_name}</strong> into a template: {latest.error}
            </p>
          )}

          {latest?.status === 'ready' && (
            <div style={{ border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', padding: '1rem',
                          display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
              <div>
                <h3 style={h3}>Check {latest.file_name} before using it</h3>
                <p style={{ ...muted, marginTop: '0.3rem' }}>
                  Open both PDFs: Applaut's version is your file rebuilt from the template with your own text, and
                  should look the same.
                </p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button type="button" disabled={busy !== null} style={buttonStyle('ghost', busy !== null)}
                  onClick={() => openPreview(latest, 'original')}>{busy === 'original' ? 'Opening…' : 'Your file (PDF)'}</button>
                <button type="button" disabled={busy !== null} style={buttonStyle('ghost', busy !== null)}
                  onClick={() => openPreview(latest, 'rebuilt')}>{busy === 'rebuilt' ? 'Opening…' : "Applaut's version (PDF)"}</button>
              </div>
              <Report t={latest} />
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button type="button" disabled={busy !== null || !latest.can_use}
                  style={buttonStyle('primary', busy !== null || !latest.can_use)}
                  onClick={() => run('use', () => useCvTemplate(latest.id), 'Could not switch it on',
                    'Your template is on. Every new CV uses it.')}>
                  {busy === 'use' ? 'Switching on…' : 'Use this template'}
                </button>
                <button type="button" disabled={busy !== null} style={buttonStyle('ghost', busy !== null)}
                  onClick={() => run('discard', () => removeCvTemplate(latest.id), 'Could not discard it')}>Discard</button>
              </div>
            </div>
          )}

          {latest?.status !== 'reading' && (
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <input ref={fileInput} type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                style={{ display: 'none' }} aria-label="Your CV as a .docx file"
                onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) upload(f) }} />
              <button type="button" disabled={busy !== null} style={buttonStyle(active || latest ? 'ghost' : 'primary', busy !== null)}
                onClick={() => fileInput.current?.click()}>
                {busy === 'upload' ? 'Uploading…' : active || latest ? 'Upload another .docx' : 'Upload your CV (.docx)'}
              </button>
              <span style={{ ...muted, fontSize: '0.75rem' }}>
                Word or Google Docs (File → Download → Microsoft Word). Up to 5 MB.
              </span>
            </div>
          )}
          {message && <p style={muted}>{message}</p>}
        </>
      )}
    </div>
  )
}
