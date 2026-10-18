import { useState } from 'react'
import { downloadSetupKit } from '../api/jobEngine'
import { apiErrorMessage } from '../api/errors'
import { buttonStyle } from './RoutineEngineCard'

const STEPS: [string, string][] = [
  ['Finish your profile', 'profile/master_profile.yaml is pre-filled from Applaut; replace the TODOs with your real experience.'],
  ['Neon database', 'create a project; its connection string is for the routine. Run sql/applaut_reader.sql for Applaut.'],
  ['Cloudflare R2', 'a bucket, a read & write key for the routine, a read-only key for Applaut.'],
  ['GitHub + Claude routine', 'push the folder to a private repo, create the routine at claude.ai/code/routines, press Run now.'],
  ['Connect Applaut', 'Settings → Job engine: paste the read-only keys, Test connection, Save.'],
]

/** "Don't have a routine yet?": the setup kit download and what to do with it. */
export default function RoutineSetupKit({ compact = false }: { compact?: boolean }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const download = async () => {
    setBusy(true)
    setError(null)
    try {
      await downloadSetupKit()
      setDone(true)
    } catch (err) {
      setError(apiErrorMessage(err, 'Download failed. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {!compact && (
        <p style={{ margin: 0, fontSize: '0.825rem', color: 'var(--text-2)', lineHeight: 1.5 }}>
          The kit has everything to run the AI job search in your own Claude account: the routine's
          instructions, the pipeline, CV and cover letter templates, and a step-by-step README. Your
          profile and search terms are pre-filled from what you entered here. About 1½–2 hours the
          first time (≈45 min if you know GitHub, Neon and Cloudflare); the AI runs on your Claude plan.
        </p>
      )}
      {!compact && (
        <ol style={{ margin: 0, paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
          {STEPS.map(([title, text]) => (
            <li key={title} style={{ fontSize: '0.8rem', color: 'var(--text-2)' }}>
              <strong style={{ color: 'var(--text-1)', fontWeight: 600 }}>{title}:</strong> {text}
            </li>
          ))}
        </ol>
      )}
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <button type="button" onClick={download} disabled={busy} style={buttonStyle(compact ? 'ghost' : 'primary', busy)}>
          {busy ? 'Preparing…' : 'Download the setup kit (.zip)'}
        </button>
        {done && <span style={{ fontSize: '0.78rem', color: 'var(--success)' }}>Downloaded. Start with README.md.</span>}
        {error && <span style={{ fontSize: '0.78rem', color: 'var(--danger)' }}>{error}</span>}
      </div>
    </div>
  )
}
