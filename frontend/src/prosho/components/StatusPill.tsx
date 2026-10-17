export type PillStatus = 'met' | 'not_met' | 'in_progress' | 'not_started' | 'awaiting_evidence' | 'pass' | 'fail' | 'warn' | 'unchecked' | 'success' | 'failure' | 'cancelled'

const STYLE: Record<PillStatus, { label: string; tone: 'success' | 'danger' | 'warn' | 'neutral' }> = {
  met: { label: '✓ Met', tone: 'success' },
  not_met: { label: 'Not met', tone: 'danger' },
  in_progress: { label: 'In progress', tone: 'warn' },
  not_started: { label: 'Not started', tone: 'neutral' },
  awaiting_evidence: { label: 'Awaiting evidence', tone: 'neutral' },
  pass: { label: '✓ Up', tone: 'success' },
  fail: { label: 'Down', tone: 'danger' },
  warn: { label: 'Warning', tone: 'warn' },
  unchecked: { label: 'Not checked yet', tone: 'neutral' },
  success: { label: '✓ Passed', tone: 'success' },
  failure: { label: 'Failed', tone: 'danger' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}

const TONE = {
  success: ['var(--success-bg)', 'var(--success-border)', 'var(--success)'],
  danger: ['var(--danger-bg)', 'var(--danger-border)', 'var(--danger)'],
  warn: ['var(--warn-bg)', 'var(--warn-border)', 'var(--warn)'],
  neutral: ['transparent', 'var(--border-strong)', 'var(--text-2)'],
}

export default function StatusPill({ status }: { status: string | null }) {
  const s = STYLE[(status ?? 'awaiting_evidence') as PillStatus] ?? { label: status ?? '—', tone: 'neutral' as const }
  const [bg, border, color] = TONE[s.tone]
  return (
    <span style={{ flexShrink: 0, padding: '0.2rem 0.6rem', borderRadius: '999px', fontSize: '0.72rem', fontWeight: 600, whiteSpace: 'nowrap', background: bg, border: `1px solid ${border}`, color }}>
      {s.label}
    </span>
  )
}
