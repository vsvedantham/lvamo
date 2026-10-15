import client from './client'
import type { DemoKind, ProjectType, Visibility } from './projects'
import type { TargetOp } from './github'

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
  updated_at: string
  preview: boolean
}

// Uses the shared client, so a signed-in owner's token rides along and they
// can preview their own private page.
export async function getPublicProject(slug: string): Promise<PublicProject> {
  return (await client.get<PublicProject>(`/public/projects/${encodeURIComponent(slug)}`)).data
}
