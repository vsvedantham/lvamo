import { useEffect, useState } from 'react'
import { errorMessage } from '../api/jobEngine'
import {
  addFacts, discardBulletDrafts, draftBullets, getBulletDrafts, validationErrors,
  type BulletDraft, type MasterProfile,
} from '../api/masterProfile'
import { buttonStyle } from './RoutineEngineCard'

// Settings → Master profile → Add bullets from notes (Applaut AI): you describe
// what you did in a role, Applaut AI drafts CV bullets from it, and you keep,
// edit or discard each one. Nothing reaches your profile until you add it.

const POLL_MS = 10_000
const muted: React.CSSProperties = { fontSize: '0.8rem', color: 'var(--text-2)', margin: 0 }

interface Entry { id: string; label: string; facts: number }

function entriesOf(data: Record<string, any>): Entry[] {
  const roles = (data.experience ?? []).map((e: any) => ({
    id: e.id, label: `${e.title} at ${e.company}`, facts: (e.facts ?? []).length,
  }))
  const projects = (data.projects ?? []).map((p: any) => ({
    id: p.id, label: `Project: ${p.name}`, facts: (p.facts ?? []).length,
  }))
  return [...roles, ...projects]
}

type Choice = { text: string; keep: boolean | null }  // null: not decided yet

export default function BulletBankBuilder({ saved, dirty, onSaved }: {
  saved: MasterProfile
  dirty: boolean
  onSaved: (mp: MasterProfile) => void
}) {
  const entries = entriesOf(saved.data)
  const [entryId, setEntryId] = useState(entries[0]?.id ?? '')
  const [notes, setNotes] = useState('')
  const [draft, setDraft] = useState<BulletDraft | null | undefined>(undefined)
  const [choices, setChoices] = useState<Choice[]>([])
  const [busy, setBusy] = useState<'draft' | 'add' | 'discard' | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const show = (d: BulletDraft | null) => {
    setDraft(d)
    setChoices(d?.status === 'done' ? d.drafts.map(x => ({ text: x.text, keep: null })) : [])
  }

  useEffect(() => {
    if (!entryId) return
    setDraft(undefined); setMessage(null)
    getBulletDrafts(entryId).then(show).catch(err => { setDraft(null); setMessage(errorMessage(err, 'Could not load drafts')) })
  }, [entryId])

  useEffect(() => {  // while the writer is on it, check every 10 s
    if (draft?.status !== 'pending') return
    const t = window.setTimeout(() => {
      getBulletDrafts(draft.entry_id).then(show).catch(() => undefined)
    }, POLL_MS)
    return () => window.clearTimeout(t)
  }, [draft])

  if (entries.length === 0) return null
  const entry = entries.find(e => e.id === entryId)
  const kept = choices.filter(c => c.keep && c.text.trim())

  const start = async () => {
    setBusy('draft'); setMessage(null)
    try { show(await draftBullets(entryId, notes)); setNotes('') }
    catch (err) { setMessage(errorMessage(err, 'Could not start drafting')) }
    finally { setBusy(null) }
  }

  const discard = async () => {
    setBusy('discard'); setMessage(null)
    try { await discardBulletDrafts(entryId); show(null) }
    catch (err) { setMessage(errorMessage(err, 'Could not discard the drafts')) }
    finally { setBusy(null) }
  }

  const add = async () => {
    if (!draft) return
    setBusy('add'); setMessage(null)
    try {
      const mp = await addFacts(entryId, kept.map(c => c.text.trim()), draft.id)
      onSaved(mp)
      show(null)
      setMessage(`Added ${kept.length} ${kept.length === 1 ? 'bullet' : 'bullets'} to ${entry?.label} (version ${mp.version}).`)
    } catch (err) {
      const errs = validationErrors(err)
      setMessage(errs.length ? errs.join(' · ') : errorMessage(err, 'Could not add the bullets'))
    } finally {
      setBusy(null)
    }
  }

  const setChoice = (i: number, change: Partial<Choice>) =>
    setChoices(cs => cs.map((c, k) => (k === i ? { ...c, ...change } : c)))

  return (
    <section style={{ borderTop: '1px solid var(--border)', paddingTop: '0.875rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div>
        <h3 style={{ fontSize: '0.9rem', fontWeight: 600, margin: 0, color: 'var(--text-1)' }}>Add bullets from notes</h3>
        <p style={{ ...muted, marginTop: '0.3rem' }}>
          The more bullets a role has, the more Applaut AI can pick from for each job (8–12 per role works well).
          Describe what you did in your own words; Applaut AI drafts bullets from it, using only what you wrote. You
          keep, edit or discard each one before anything is added.
        </p>
      </div>

      <label style={{ ...muted, display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
        Role or project
        <select value={entryId} onChange={e => setEntryId(e.target.value)} disabled={busy !== null}
          style={{ padding: '0.4rem 0.6rem', fontSize: '0.85rem', maxWidth: '100%' }}>
          {entries.map(e => <option key={e.id} value={e.id}>{e.label} · {e.facts} {e.facts === 1 ? 'bullet' : 'bullets'}</option>)}
        </select>
      </label>

      {draft === undefined ? <p style={muted}>Loading…</p> : draft === null ? (
        <>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} maxLength={4000}
            aria-label="Notes about this role"
            placeholder="What you built or ran, with what, for whom, and what changed. Numbers only if you know them."
            style={{ minHeight: '120px', fontSize: '0.85rem', lineHeight: 1.5, resize: 'vertical', width: '100%', boxSizing: 'border-box' }} />
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <button type="button" onClick={start} disabled={busy !== null || notes.trim().length < 20}
              style={buttonStyle('primary', busy !== null || notes.trim().length < 20)}>
              {busy === 'draft' ? 'Sending…' : 'Draft bullets'}
            </button>
            <span style={{ ...muted, fontSize: '0.75rem' }}>Takes a few minutes; you can leave this page.</span>
          </div>
        </>
      ) : draft.status === 'pending' ? (
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <p style={muted}>
            {draft.ahead ? `Waiting: ${draft.ahead} ${draft.ahead === 1 ? 'item' : 'items'} ahead in the queue.` : 'Drafting your bullets…'}
            {' '}This page checks again every few seconds.
          </p>
          <button type="button" onClick={discard} disabled={busy !== null} style={buttonStyle('ghost', busy !== null)}>Cancel</button>
        </div>
      ) : draft.status === 'failed' ? (
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <p style={{ ...muted, color: 'var(--danger)' }}>Drafting failed: {draft.error}</p>
          <button type="button" onClick={discard} disabled={busy !== null} style={buttonStyle('ghost', busy !== null)}>Try again</button>
        </div>
      ) : (
        <>
          {choices.length === 0 && <p style={muted}>No drafts came out of these notes.</p>}
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {choices.map((c, i) => {
              const confirm = draft.drafts[i]?.confirm ?? []
              return (
                <li key={i} style={{ border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', padding: '0.75rem',
                                     opacity: c.keep === false ? 0.5 : 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <textarea value={c.text} onChange={e => setChoice(i, { text: e.target.value })} disabled={c.keep === false}
                    aria-label={`Draft ${i + 1}`}
                    style={{ minHeight: '60px', fontSize: '0.85rem', lineHeight: 1.5, resize: 'vertical', width: '100%', boxSizing: 'border-box' }} />
                  {confirm.length > 0 && (
                    <p style={{ ...muted, color: 'var(--warn)' }}>
                      Check: {confirm.join(', ')} {confirm.length === 1 ? "isn't" : "aren't"} in your notes. Keep it only if it's right.
                    </p>
                  )}
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button type="button" onClick={() => setChoice(i, { keep: c.keep ? null : true })}
                      style={buttonStyle(c.keep ? 'primary' : 'ghost')} aria-pressed={!!c.keep}>
                      {c.keep ? 'Kept ✓' : 'Keep'}
                    </button>
                    <button type="button" onClick={() => setChoice(i, { keep: c.keep === false ? null : false })}
                      style={buttonStyle('ghost')} aria-pressed={c.keep === false}>
                      {c.keep === false ? 'Discarded' : 'Discard'}
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
          {draft.left_out.length > 0 && (
            <details style={muted}>
              <summary style={{ cursor: 'pointer' }}>{draft.left_out.length} {draft.left_out.length === 1 ? 'draft was' : 'drafts were'} left out by the checks</summary>
              <ul style={{ margin: '0.4rem 0 0', paddingLeft: '1.1rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                {draft.left_out.map((x, i) => <li key={i}>{x.text} <em>({x.reason})</em></li>)}
              </ul>
            </details>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <button type="button" onClick={add} disabled={busy !== null || dirty || kept.length === 0}
              style={buttonStyle('primary', busy !== null || dirty || kept.length === 0)}>
              {busy === 'add' ? 'Adding…' : `Add ${kept.length || ''} kept ${kept.length === 1 ? 'bullet' : 'bullets'}`.replace('  ', ' ')}
            </button>
            <button type="button" onClick={discard} disabled={busy !== null} style={buttonStyle('ghost', busy !== null)}>
              Discard all
            </button>
            {dirty && <span style={{ ...muted, fontSize: '0.75rem' }}>Save or undo your YAML changes first.</span>}
          </div>
        </>
      )}
      {message && <p style={muted}>{message}</p>}
    </section>
  )
}
