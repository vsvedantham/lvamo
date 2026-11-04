import { useEffect, useRef, useState } from 'react'
import { chooseBulletVersion, getCvDetails, type BulletVersion, type CvBullet, type DocumentItem } from '../api/documents'
import { apiErrorMessage } from '../api/errors'

/** An Applaut AI CV's reworded bullets, each switchable back to the user's
 *  own wording. A switch builds the CV again (no AI) as a new current version. */
export default function TailoredBullets({ documentId, onNewVersion }: {
  documentId: string
  onNewVersion: (doc: DocumentItem) => void
}) {
  const [bullets, setBullets] = useState<CvBullet[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  const loadedFor = useRef<string | null>(null)  // a switch returns the new version's bullets itself

  useEffect(() => {
    if (loadedFor.current === documentId) return
    setBullets(null)
    getCvDetails(documentId).then(d => {
      loadedFor.current = d.document_id
      setBullets(d.bullets)
    }).catch(() => setError('Could not load the bullets.'))
  }, [documentId])

  const choose = async (b: CvBullet, version: BulletVersion) => {
    setBusy(b.fact_id)
    setError('')
    try {
      const result = await chooseBulletVersion(documentId, b.fact_id, version)
      loadedFor.current = result.details.document_id
      setBullets(result.details.bullets)
      onNewVersion(result.document)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not update the CV. Please try again.'))
    } finally {
      setBusy(null)
    }
  }

  if (bullets === null) {
    return error ? <p style={{ color: 'var(--danger)', fontSize: '0.85rem' }}>{error}</p> : null
  }
  const tailored = bullets.filter(b => b.tailored)

  return (
    <section style={{ border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', padding: '1rem 1.25rem', marginBottom: '1rem', background: 'var(--bg-surface)' }}>
      <h2 style={{ fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.25rem', color: 'var(--text-1)' }}>
        Tailored bullets
      </h2>
      <p style={{ fontSize: '0.8rem', color: 'var(--text-2)', margin: '0 0 0.75rem' }}>
        {tailored.length === 0
          ? 'Every bullet on this CV is shown as you wrote it in your master profile.'
          : `${tailored.length} of ${bullets.length} bullets were reworded for this job, using only your own facts. `
            + 'Switch any back to your wording; the PDF updates right away. The rest are shown as you wrote them.'}
      </p>
      {error && <p style={{ color: 'var(--danger)', fontSize: '0.85rem', margin: '0 0 0.75rem' }}>{error}</p>}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.75rem' }}>
        {tailored.map(b => {
          const usingTailored = b.use === 'tailored'
          return (
            <li key={b.fact_id} style={{ borderTop: '1px solid var(--border)', paddingTop: '0.75rem' }}>
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                <div style={{ flex: '1 1 20rem', minWidth: 0 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-2)', marginBottom: '0.2rem' }}>
                    {b.entry} · {usingTailored ? 'tailored for this job' : 'your wording'}
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-1)', lineHeight: 1.5 }}>
                    {usingTailored ? b.tailored : b.original}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-2)', lineHeight: 1.5, marginTop: '0.3rem' }}>
                    {usingTailored ? 'Your wording: ' : 'Tailored: '}{usingTailored ? b.original : b.tailored}
                  </div>
                </div>
                <button
                  onClick={() => choose(b, usingTailored ? 'original' : 'tailored')}
                  disabled={busy !== null}
                  style={{ padding: '0.35rem 0.8rem', fontSize: '0.8rem', border: '1px solid var(--border-strong)', borderRadius: '6px', cursor: busy ? 'default' : 'pointer', background: 'transparent', color: 'var(--text-1)', whiteSpace: 'nowrap', opacity: busy && busy !== b.fact_id ? 0.5 : 1 }}
                >
                  {busy === b.fact_id ? 'Updating…' : usingTailored ? 'Use my wording' : 'Use tailored'}
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
