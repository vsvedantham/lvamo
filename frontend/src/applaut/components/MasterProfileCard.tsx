import { useEffect, useState } from 'react'
import { errorMessage } from '../api/jobEngine'
import { closeProfileImport, getMasterProfile, openPreview, saveMasterProfileYaml, validationErrors, type MasterProfile } from '../api/masterProfile'
import BulletBankBuilder from './BulletBankBuilder'
import ProfileFromCv from './ProfileFromCv'
import { buttonStyle, formatWhen } from './RoutineEngineCard'

// Settings → Your profile (Applaut AI) or Settings (Basic): the master profile,
// what every generated CV and cover letter may say about you. A saved profile
// shows as a status line with previews; the YAML editor (the Claude routine's
// format, so a routine user can paste master_profile.yaml unchanged) opens on
// "Edit profile", for a CV draft, or when nothing is saved yet. Applaut AI adds
// "Upload a newer CV" and, as its own card, "Add bullets from notes".

const card: React.CSSProperties = {
  padding: '1.25rem', background: 'var(--bg-surface)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius)', display: 'flex', flexDirection: 'column', gap: '0.875rem',
}
const h2: React.CSSProperties = { fontSize: '1rem', fontWeight: 600, margin: 0, color: 'var(--text-1)' }
const muted: React.CSSProperties = { fontSize: '0.8rem', color: 'var(--text-2)', margin: 0 }

/** `canDraft`: Applaut AI is the engine, so it can draft bullets from your notes. */
export default function MasterProfileCard({ canDraft = false }: { canDraft?: boolean }) {
  const [saved, setSaved] = useState<MasterProfile | null | undefined>(undefined)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState<'save' | 'cv' | 'cover_letter' | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [fromCv, setFromCv] = useState(false)  // the editor holds the draft from the user's CV
  const [cvKey, setCvKey] = useState(0)
  const [editing, setEditing] = useState(false)  // the YAML editor is open

  useEffect(() => {
    getMasterProfile()
      .then(mp => { setSaved(mp); setText(mp?.yaml ?? '') })
      .catch(err => { setSaved(null); setMessage(errorMessage(err, 'Could not load your master profile')) })
  }, [])

  const dirty = saved !== undefined && text !== (saved?.yaml ?? '')

  const save = async () => {
    setBusy('save'); setProblems([]); setMessage(null)
    try {
      const mp = await saveMasterProfileYaml(text)
      setSaved(mp); setText(mp.yaml); setMessage(`Saved (version ${mp.version}).`); setEditing(false)
      if (fromCv) {  // the draft is now the profile: Applaut drops the CV's text
        setFromCv(false)
        await closeProfileImport().catch(() => undefined)
        setCvKey(k => k + 1)
      }
    } catch (err) {
      const errs = validationErrors(err)
      if (errs.length) setProblems(errs)
      else setMessage(errorMessage(err, 'Could not save'))
    } finally {
      setBusy(null)
    }
  }

  const cancel = () => { setText(saved?.yaml ?? ''); setProblems([]); setMessage(null); setEditing(false) }

  const preview = async (kind: 'cv' | 'cover_letter') => {
    setBusy(kind); setMessage(null)
    try { await openPreview(kind) } catch (err) { setMessage(errorMessage(err, 'Could not build the preview')) } finally { setBusy(null) }
  }

  const showEditor = editing || fromCv || dirty || saved === null
  const counts = saved ? profileCounts(saved.data) : null
  const previewButtons = (
    <>
      <button type="button" onClick={() => preview('cv')} disabled={!saved || dirty || busy !== null} style={buttonStyle()}>
        {busy === 'cv' ? 'Building…' : 'Preview CV'}
      </button>
      <button type="button" onClick={() => preview('cover_letter')} disabled={!saved || dirty || busy !== null} style={buttonStyle()}>
        {busy === 'cover_letter' ? 'Building…' : 'Preview cover letter'}
      </button>
    </>
  )

  return (
    <>
      <div style={card} id="master-profile">
        <div>
          <h2 style={h2}>Master profile</h2>
          <p style={{ ...muted, marginTop: '0.3rem' }}>
            Your jobs and what you did in each, your skills, education and languages. Applaut writes your CVs and
            cover letters only from this, and never adds anything that isn't here.
          </p>
        </div>
        {saved === undefined ? <p style={muted}>Loading…</p> : (
          <>
            {saved === null && canDraft && (
              <p role="alert" style={{ ...muted, color: 'var(--warn)' }}>
                Applaut can't score jobs or write documents for you until you save a profile here.
              </p>
            )}
            {saved && (
              <div style={{ padding: '0.75rem 0.875rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                            borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                <p style={{ ...muted, color: 'var(--text-1)' }}>
                  {dirty
                    ? <span style={{ color: 'var(--warn)' }}>Unsaved changes. Save them to preview.</span>
                    : <><strong>Saved</strong> · version {saved.version} · {formatWhen(saved.updated_at)}</>}
                  {counts && <span style={muted}> · {counts}</span>}
                </p>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  {previewButtons}
                  {!showEditor && (
                    <button type="button" onClick={() => setEditing(true)} disabled={busy !== null} style={buttonStyle()}>
                      Edit profile
                    </button>
                  )}
                </div>
              </div>
            )}
            {canDraft && (
              <ProfileFromCv key={cvKey} hasSaved={saved !== null} dirty={dirty}
                onLoad={yaml => { setText(yaml); setProblems([]); setMessage(null); setFromCv(true) }} />
            )}
            {showEditor && (
              <>
                <p style={{ ...muted, fontSize: '0.75rem' }}>
                  Written in YAML, the same format as the Claude routine's <code>master_profile.yaml</code>.
                </p>
                <textarea value={text} onChange={e => setText(e.target.value)} spellCheck={false}
                  placeholder={'personal:\n  name: Your Name\n  ...\ndefault_headline: ...\nexperience:\n  - id: company_role\n    facts:\n      - ...'}
                  aria-label="Master profile (YAML)"
                  style={{ minHeight: '360px', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.78rem',
                           lineHeight: 1.5, resize: 'vertical', width: '100%', boxSizing: 'border-box' }} />
                {problems.length > 0 && (
                  <div role="alert" style={{ ...muted, color: 'var(--danger)', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                    <strong>Nothing was saved. Fix these:</strong>
                    {problems.map((p, i) => <span key={i} style={{ overflowWrap: 'anywhere' }}>• {p}</span>)}
                  </div>
                )}
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                  <button type="button" onClick={save} disabled={!dirty || busy !== null || !text.trim()} style={buttonStyle('primary', !dirty || busy !== null || !text.trim())}>
                    {busy === 'save' ? 'Saving…' : 'Save'}
                  </button>
                  {saved && !fromCv && (
                    <button type="button" onClick={cancel} disabled={busy !== null} style={buttonStyle()}>
                      {dirty ? 'Discard changes' : 'Close editor'}
                    </button>
                  )}
                  {!saved && previewButtons}
                </div>
              </>
            )}
            {message && <p style={muted}>{message}</p>}
          </>
        )}
      </div>
      {canDraft && saved && (
        <BulletBankBuilder saved={saved} dirty={dirty} onSaved={mp => { setSaved(mp); setText(mp.yaml) }} />
      )}
    </>
  )
}

/** "4 roles · 1 project · 11 bullets" from the saved profile. */
function profileCounts(data: Record<string, any>): string | null {
  const roles = Array.isArray(data?.experience) ? data.experience : []
  const projects = Array.isArray(data?.projects) ? data.projects : []
  if (!roles.length && !projects.length) return null
  const bullets = [...roles, ...projects].reduce((n: number, e: any) => n + (Array.isArray(e?.facts) ? e.facts.length : 0), 0)
  const n = (k: number, one: string, many = `${one}s`) => `${k} ${k === 1 ? one : many}`
  return [n(roles.length, 'role'), projects.length ? n(projects.length, 'project') : null, n(bullets, 'bullet')].filter(Boolean).join(' · ')
}
