import { useEffect, useState } from 'react'
import { errorMessage } from '../api/jobEngine'
import { closeProfileImport, getMasterProfile, openPreview, saveMasterProfileYaml, validationErrors, type MasterProfile } from '../api/masterProfile'
import BulletBankBuilder from './BulletBankBuilder'
import ProfileFromCv from './ProfileFromCv'
import { buttonStyle, formatWhen } from './RoutineEngineCard'

// Settings → Master profile, for Applaut AI: what every generated CV and cover
// letter may say about you. Edited as YAML in the Claude routine's format, so a
// routine user can paste their master_profile.yaml unchanged.

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
      setSaved(mp); setText(mp.yaml); setMessage(`Saved (version ${mp.version}).`)
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

  const preview = async (kind: 'cv' | 'cover_letter') => {
    setBusy(kind); setMessage(null)
    try { await openPreview(kind) } catch (err) { setMessage(errorMessage(err, 'Could not build the preview')) } finally { setBusy(null) }
  }

  return (
    <div style={card} id="master-profile">
      <div>
        <h2 style={h2}>Master profile</h2>
        <p style={{ ...muted, marginTop: '0.3rem' }}>
          Everything Applaut AI may put in your CV and cover letters, and nothing else: your roles, their bullet
          points (<code>facts</code>), skills, education and languages. For each job, Applaut picks your most relevant
          bullets and orders your skills; AI writes the headline and letter paragraphs, and may reword a few bullets
          to fit the job, using only these facts (you can switch any back on the CV). Same format as the Claude routine's <code>master_profile.yaml</code>, so you can paste that file here.
        </p>
      </div>
      {saved === undefined ? <p style={muted}>Loading…</p> : (
        <>
          {saved === null && canDraft && (
            <p role="alert" style={{ ...muted, color: 'var(--warn)' }}>
              Applaut AI scores jobs and writes documents only from your master profile, so it does nothing for you
              until you save one here.
            </p>
          )}
          {canDraft && (
            <ProfileFromCv key={cvKey} hasSaved={saved !== null} dirty={dirty}
              onLoad={yaml => { setText(yaml); setProblems([]); setMessage(null); setFromCv(true) }} />
          )}
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
          {message && <p style={muted}>{message}</p>}
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <button type="button" onClick={save} disabled={!dirty || busy !== null || !text.trim()} style={buttonStyle('primary')}>
              {busy === 'save' ? 'Saving…' : 'Save'}
            </button>
            <button type="button" onClick={() => preview('cv')} disabled={!saved || dirty || busy !== null} style={buttonStyle()}>
              {busy === 'cv' ? 'Building…' : 'Preview CV'}
            </button>
            <button type="button" onClick={() => preview('cover_letter')} disabled={!saved || dirty || busy !== null} style={buttonStyle()}>
              {busy === 'cover_letter' ? 'Building…' : 'Preview cover letter'}
            </button>
            {saved && <span style={{ ...muted, fontSize: '0.75rem' }}>
              {dirty ? 'Unsaved changes — save to preview' : `Version ${saved.version} · saved ${formatWhen(saved.updated_at)}`}
            </span>}
          </div>
          {canDraft && saved && (
            <BulletBankBuilder saved={saved} dirty={dirty} onSaved={mp => { setSaved(mp); setText(mp.yaml) }} />
          )}
        </>
      )}
    </div>
  )
}
