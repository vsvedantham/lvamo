import { useEffect, useState } from 'react'
import type { Project } from '../api/projects'
import { formatDay, getPageStats, type PageStats } from '../api/team'
import ActivityBars from './ActivityBars'
import { Card, hintStyle } from './ui'

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

// Daily aggregates only: no visitor is tracked (BETA_PLAN §11). Your own and
// your mentor's visits aren't counted.
export default function PageStatsCard({ project }: { project: Project }) {
  const [stats, setStats] = useState<PageStats | null>(null)
  useEffect(() => { getPageStats(project.id, 30).then(setStats).catch(() => setStats(null)) }, [project.id])

  if (!stats || project.published_at === null) return null
  const first = stats.days[0].day

  return (
    <Card title="Page views" aside={<span style={hintStyle}>Last 30 days</span>}>
      <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', marginBottom: '1.1rem' }}>
        <Stat value={stats.total_views} label="views" />
        <Stat value={stats.hub_clicks} label="clicks to LVAMO" />
      </div>
      <ActivityBars
        height={56}
        bars={stats.days.map(d => ({ key: d.day, value: d.views, label: `${formatDay(d.day, { day: 'numeric', month: 'short' })} · ${plural(d.views, 'view')}` }))}
        summary="Views per day"
        startLabel={formatDay(first, { day: 'numeric', month: 'short' })}
        endLabel="Today"
      />
      {stats.referrers.length > 0 && (
        <>
          <h3 style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-2)', margin: '1.25rem 0 0.4rem' }}>Where visitors came from</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <tbody>
              {stats.referrers.map(r => (
                <tr key={r.domain} style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={{ padding: '0.4rem 0', overflowWrap: 'anywhere' }}>{r.domain || <span style={{ color: 'var(--text-2)' }}>Direct link / unknown</span>}</td>
                  <td style={{ padding: '0.4rem 0', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{r.views}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <p style={{ ...hintStyle, marginTop: '0.9rem' }}>Counted once per visit, without cookies. Your own and your mentor&apos;s visits aren&apos;t counted.</p>
    </Card>
  )
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <p style={{ fontSize: '1.6rem', fontWeight: 700, lineHeight: 1.1, fontVariantNumeric: 'tabular-nums' }}>{value}</p>
      <p style={{ fontSize: '0.78rem', color: 'var(--text-2)' }}>{label}</p>
    </div>
  )
}
