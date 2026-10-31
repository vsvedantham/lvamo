import { type FormEvent, type ReactNode, useState } from 'react'
import { apiErrorMessage } from '../api/projects'
import { Banner, Button, Card } from './ui'

// The one place something can't be undone: say what goes, then make the
// person type a name before the button wakes up.
export default function DeleteCard({ title, children, confirmWord, action, onDelete }: {
  title: string
  children: ReactNode
  confirmWord: string
  action: string
  onDelete: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const matches = typed.trim().toLowerCase() === confirmWord.toLowerCase()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!matches) return
    setBusy(true)
    setError('')
    try {
      await onDelete()
    } catch (err) {
      setError(apiErrorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Card title={title}>
      <div style={{ fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.6 }}>{children}</div>
      {error && <div style={{ marginTop: '1rem' }}><Banner kind="error">{error}</Banner></div>}
      {open ? (
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginTop: '1rem', maxWidth: '420px' }}>
          <label style={{ fontSize: '0.85rem' }} htmlFor="delete-confirm">
            Type <strong style={{ fontFamily: 'var(--font-mono, monospace)' }}>{confirmWord}</strong> to confirm
          </label>
          <input id="delete-confirm" value={typed} onChange={e => setTyped(e.target.value)} autoFocus autoComplete="off" spellCheck={false} />
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <Button type="submit" variant="danger" disabled={!matches || busy}>{busy ? 'Deleting…' : action}</Button>
            <Button variant="secondary" onClick={() => { setOpen(false); setTyped('') }}>Cancel</Button>
          </div>
        </form>
      ) : (
        <div style={{ marginTop: '1rem' }}>
          <Button variant="secondary" onClick={() => setOpen(true)}>{action}…</Button>
        </div>
      )}
    </Card>
  )
}
