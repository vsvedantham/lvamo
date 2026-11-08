import { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api/jobEngine'
import { closeProfileImport, getProfileImport, importCv, type ProfileImport } from '../api/masterProfile'
import { buttonStyle } from './RoutineEngineCard'

// Master profile → "Start from your CV" (docs/applaut/APPLAUT_AI_V2_PLAN.md §5).
// Applaut AI reads the CV's lines and says which line is what; the draft is the
// CV's own text, so the user only checks it, fills the gaps and saves.

const POLL_MS = 10_000
const muted: React.CSSProperties = { fontSize: '0.8rem', color: 'var(--text-2)', margin: 0 }
const h3: React.CSSProperties = { fontSize: '0.85rem', fontWeight: 600, margin: 0, color: 'var(--text-1)' }
const list: React.CSSProperties = { ...muted, margin: 0, paddingLeft: '1.1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }

interface Props {
  /** A profile is saved already, so loading the draft would replace it in the editor. */
  hasSaved: boolean
  /** The editor has unsaved changes. */
  dirty: boolean
  /** Put the draft's YAML into the editor (not saved). */
  onLoad: (yaml: string) => void
}

export default function ProfileFromCv({ hasSaved, dirty, onLoad }: Props) {
  const [imp, setImp] = useState<ProfileImport | null | undefined>(undefined)
  const [busy, setBusy] = useState<'upload' | 'close' | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const load = () => getProfileImport().then(setImp).catch(err => setMessage(errorMessage(err, 'Could not check your CV draft')))
  useEffect(() => { load() }, [])

  useEffect(() => {  // while Applaut AI reads the CV, check every 10 s
    if (imp?.status !== 'reading') return
    const t = window.setTimeout(load, POLL_MS)
    return () => window.clearTimeout(t)
  }, [imp])

  const upload = async (file: File) => {
    setBusy('upload'); setMessage(null); setLoaded(false)
    try { setImp(await importCv(file)) }
    catch (err) { setMessage(errorMessage(err, 'Could not upload the file')) }
    finally { setBusy(null) }
  }

  const close = async () => {
    setBusy('close'); setMessage(null)
    try { await closeProfileImport(); setImp(null); setLoaded(false) }
    catch (err) { setMessage(errorMessage(err, 'Could not discard the draft')) }
    finally { setBusy(null) }
  }

  const loadIntoEditor = () => {
    if (!imp?.yaml) return
    if ((hasSaved || dirty) && !window.confirm(
      'This replaces what is in the editor with the draft from your CV. Your saved profile stays as it is until you save. Continue?')) return
    onLoad(imp.yaml); setLoaded(true)
  }

  if (imp === undefined) return null
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.875rem',
                  display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div>
        <h3 style={h3}>Start from your CV</h3>
        <p style={{ ...muted, marginTop: '0.3rem' }}>
          Upload your CV and Applaut AI sorts its lines into a draft profile: your name, headline, roles and their
          bullets, skills, education. The draft uses only your CV's own words; anything it couldn't place is listed
          so you can fill it in. Applaut keeps only the CV's text, and deletes it once you save or discard the draft.
        </p>
      </div>

      {imp?.status === 'reading' && (
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <p style={muted}>
            Reading <strong>{imp.file_name}</strong>…{' '}
            {imp.ahead ? `${imp.ahead} ${imp.ahead === 1 ? 'item' : 'items'} ahead in the queue. ` : ''}
            This takes a few minutes; you can leave this page.
          </p>
          <button type="button" disabled={busy !== null} style={buttonStyle('ghost', busy !== null)} onClick={close}>
            {busy === 'close' ? 'Cancelling…' : 'Cancel'}
          </button>
        </div>
      )}

      {imp?.status === 'failed' && (
        <p role="alert" style={{ ...muted, color: 'var(--danger)', overflowWrap: 'anywhere' }}>
          Applaut couldn't make a draft from <strong>{imp.file_name}</strong>: {imp.error} You can try again, or write
          the profile by hand below.
        </p>
      )}

      {imp?.status === 'ready' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          <p style={muted}>
            {loaded
              ? <>The draft from <strong>{imp.file_name}</strong> is in the editor. Check it, fill in what's missing,
                  then <strong>Save</strong>.</>
              : <>The draft from <strong>{imp.file_name}</strong> is ready.</>}
          </p>
          {imp.notes.length > 0 && (
            <>
              <strong style={{ ...muted, color: 'var(--text-1)' }}>Check these:</strong>
              <ul style={list}>{imp.notes.map((n, i) => <li key={i} style={{ overflowWrap: 'anywhere' }}>{n}</li>)}</ul>
            </>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {!loaded && (
              <button type="button" disabled={busy !== null} style={buttonStyle('primary', busy !== null)} onClick={loadIntoEditor}>
                Load into the editor
              </button>
            )}
            <button type="button" disabled={busy !== null} style={buttonStyle('ghost', busy !== null)} onClick={close}>
              {busy === 'close' ? 'Discarding…' : 'Discard the draft'}
            </button>
          </div>
        </div>
      )}

      {imp?.status !== 'reading' && imp?.status !== 'ready' && (
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <input ref={fileInput} type="file" style={{ display: 'none' }} aria-label="Your CV as a .docx or .pdf file"
            accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) upload(f) }} />
          <button type="button" disabled={busy !== null} style={buttonStyle(hasSaved ? 'ghost' : 'primary', busy !== null)}
            onClick={() => fileInput.current?.click()}>
            {busy === 'upload' ? 'Uploading…' : 'Upload your CV (.docx or .pdf)'}
          </button>
          <span style={{ ...muted, fontSize: '0.75rem' }}>Up to 5 MB. A scanned PDF has no text to read.</span>
        </div>
      )}

      {message && <p role="alert" style={{ ...muted, color: 'var(--danger)' }}>{message}</p>}
    </div>
  )
}
