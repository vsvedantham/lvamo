import client, { API_BASE } from './client'
import type { DemoKind, ProjectType, Visibility } from './projects'
import type { TargetOp } from './github'
import type { DataModule } from './evidence'
import type { Timeline } from './team'

export type PublicClaimStatus = 'not_started' | 'in_progress' | 'met' | 'not_met' | 'awaiting_evidence'

export interface PublicClaim {
  key: string
  text: string
  status: PublicClaimStatus
  self_reported: boolean
  metric_key: string | null
  target_op: TargetOp | null
  target_value: number | null
  target_value_hi: number | null
  latest_value: number | null
  latest_unit: string | null
  latest_at: string | null
  latest_commit: string | null
}

export interface PublicProject {
  slug: string
  title: string
  summary: string | null
  problem: string | null
  project_type: ProjectType
  university: string | null
  programme: string | null
  visibility: Visibility
  demo_kind: DemoKind | null
  demo_url: string | null
  owner: { name: string | null; github_login: string; avatar_url: string | null }
  claims: PublicClaim[]
  data_module: DataModule | null
  milestones: { title: string; due_on: string | null; completed_at: string | null; reviewed: boolean }[]
  timeline: Timeline | null
  mentored: boolean
  updated_at: string
  preview: boolean
  viewer_is_team: boolean
}

// Uses the shared client, so a signed-in owner's token rides along and they
// can preview their own private page.
export async function getPublicProject(slug: string): Promise<PublicProject> {
  return (await client.get<PublicProject>(`/public/projects/${encodeURIComponent(slug)}`)).data
}

/** Aggregate counts only (BETA_PLAN §11). Fire-and-forget: `keepalive` lets
 * the hub-click request finish while the page navigates away, and a failure
 * never bothers the visitor. Only the referrer's domain is kept server-side. */
export function recordPageEvent(slug: string, event: 'view' | 'hub_click'): void {
  try {
    fetch(`${API_BASE}/public/projects/${encodeURIComponent(slug)}/events`, {
      method: 'POST',
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event, referrer: event === 'view' ? document.referrer || null : null }),
    }).catch(() => {})
  } catch { /* old browsers without keepalive — not worth an error */ }
}
