import { describeTarget, type TargetOp } from '../api/github'
import { formatValue, timeAgo, type DataModule } from '../api/evidence'
import StatusPill from './StatusPill'

// The data-science module's three panels (BETA_PLAN §2) — used on the public
// page and, for sources, on the owner's dashboard.

const panelTitle: React.CSSProperties = {
  fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-2)', marginBottom: '0.9rem',
}
const row: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.9rem', flexWrap: 'wrap',
  padding: '0.8rem 1rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
}
const sub: React.CSSProperties = { fontSize: '0.78rem', color: 'var(--text-3)', marginTop: '0.2rem', overflowWrap: 'anywhere' }

export function SourcesList({ sources }: { sources: DataModule['sources'] }) {
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
      {sources.map(s => (
        <li key={s.url} style={row}>
          <div style={{ flex: '1 1 240px', minWidth: 0 }}>
            <a href={s.url} target="_blank" rel="noreferrer" style={{ fontSize: '0.9rem', color: 'var(--text-1)', fontWeight: 500 }}>{s.name}</a>
            <p style={sub}>
              {[s.licence, s.checked_at ? `checked ${timeAgo(s.checked_at)}` : null, s.status === 'fail' ? s.detail : null].filter(Boolean).join(' · ')}
            </p>
          </div>
          <StatusPill status={s.status} />
        </li>
      ))}
    </ul>
  )
}

export default function DataModulePanels({ data }: { data: DataModule }) {
  const { sources, metrics, runs } = data
  if (!sources.length && !metrics.length && !runs.length) return null
  return (
    <>
      {metrics.length > 0 && (
        <section style={{ marginBottom: '2.5rem' }}>
          <h2 style={panelTitle}>Results</h2>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {metrics.map(m => (
              <li key={m.key} style={row}>
                <div style={{ flex: '1 1 240px', minWidth: 0 }}>
                  <p style={{ fontSize: '1.15rem', fontWeight: 700 }}>{formatValue(m.value, m.unit)}</p>
                  <p style={sub}>
                    <code>{m.key}</code>
                    {m.target_op && <> · target {describeTarget({ target_op: m.target_op as TargetOp, target_value: m.target_value, target_value_hi: m.target_value_hi })}</>}
                    {' · '}{timeAgo(m.recorded_at)}{m.commit_sha && <> · <code>{m.commit_sha.slice(0, 7)}</code></>}
                  </p>
                </div>
                {m.status && <StatusPill status={m.status} />}
              </li>
            ))}
          </ul>
        </section>
      )}

      {runs.length > 0 && (
        <section style={{ marginBottom: '2.5rem' }}>
          <h2 style={panelTitle}>Pipeline</h2>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {runs.map(r => (
              <li key={r.key} style={row}>
                <div style={{ flex: '1 1 240px', minWidth: 0 }}>
                  <p style={{ fontSize: '0.9rem', fontWeight: 500 }}>{r.key} — last run {timeAgo(r.recorded_at)}</p>
                  <p style={sub}>
                    {[r.details.tests_total !== undefined ? `${r.details.tests_passed ?? 0} / ${r.details.tests_total} tests passed` : null,
                      r.details.duration_s !== undefined ? `${Math.round(r.details.duration_s)} s` : null,
                      r.commit_sha ? r.commit_sha.slice(0, 7) : null].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <StatusPill status={r.status} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {sources.length > 0 && (
        <section style={{ marginBottom: '2.5rem' }}>
          <h2 style={panelTitle}>Data sources</h2>
          <SourcesList sources={sources} />
          <p style={{ ...sub, marginTop: '0.6rem' }}>Checked daily by LVAMO — not reported by the student.</p>
        </section>
      )}
    </>
  )
}
