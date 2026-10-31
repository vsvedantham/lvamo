import { useEffect, useState } from 'react'
import { timeAgo } from '../api/evidence'
import type { Project } from '../api/projects'
import { formatDay, getTimeline, type Timeline } from '../api/team'
import ActivityBars from './ActivityBars'
import { Card, hintStyle } from './ui'

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Commits per week plus, when allowed, the latest commit messages. Used on
 * the public page and on the manage page. */
export function TimelinePanel({ timeline, hiddenNote }: { timeline: Timeline; hiddenNote?: string }) {
  const weeks = timeline.weeks
  const shownTotal = weeks.reduce((n, w) => n + w.commits, 0)
  return (
    <div>
      <ActivityBars
        bars={weeks.map(w => ({ key: w.week_start, value: w.commits, label: `Week of ${formatDay(w.week_start, { day: 'numeric', month: 'short' })} · ${plural(w.commits, 'commit')}` }))}
        summary={`${plural(shownTotal, 'commit')} in the last ${weeks.length} weeks${timeline.last_commit_at ? ` · latest ${timeAgo(timeline.last_commit_at)}` : ''}`}
        startLabel={formatDay(weeks[0].week_start, { day: 'numeric', month: 'short' })}
        endLabel="This week"
      />
      {timeline.commits ? (
        <ol style={{ listStyle: 'none', margin: '1.1rem 0 0', padding: 0, display: 'flex', flexDirection: 'column' }}>
          {timeline.commits.slice(0, 8).map(c => (
            <li key={c.sha} style={{ display: 'flex', gap: '0.75rem', alignItems: 'baseline', padding: '0.5rem 0', borderTop: '1px solid var(--border)', fontSize: '0.85rem' }}>
              <a href={c.url} target="_blank" rel="noreferrer" style={{ flexShrink: 0, color: 'var(--text-2)' }}><code>{c.sha.slice(0, 7)}</code></a>
              <span style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere', color: 'var(--text-1)' }}>{c.message || '(no message)'}</span>
              <span style={{ flexShrink: 0, color: 'var(--text-3)', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>{timeAgo(c.committed_at)}</span>
            </li>
          ))}
        </ol>
      ) : hiddenNote ? (
        <p style={{ ...hintStyle, marginTop: '0.75rem' }}>{hiddenNote}</p>
      ) : null}
    </div>
  )
}

export function TimelineCard({ project }: { project: Project }) {
  const [timeline, setTimeline] = useState<Timeline | null | undefined>(undefined)
  useEffect(() => {
    if (!project.repo_full_name) { setTimeline(null); return }
    getTimeline(project.id).then(setTimeline).catch(() => setTimeline(null))
  }, [project.id, project.repo_full_name, project.manifest_checked_at])

  if (!project.repo_full_name || timeline === undefined) return null
  return (
    <Card title="Work timeline" aside={<span style={hintStyle}>Commits on {project.repo_full_name}</span>}>
      {timeline ? (
        <>
          <TimelinePanel timeline={timeline} />
          {project.access === 'owner' && (
            <p style={{ ...hintStyle, marginTop: '0.75rem' }}>
              Your page always shows weekly activity. Commit messages appear there only if the repo itself is public.
            </p>
          )}
        </>
      ) : (
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>No commits read yet — they appear after the next push or “Sync now”.</p>
      )}
    </Card>
  )
}
