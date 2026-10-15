import client from './client'
import type { Project } from './projects'

export interface RepoOption {
  id: number
  full_name: string
  private: boolean
}

export interface AvailableRepos {
  installed: boolean
  install_url: string
  manage_url: string | null
  repos: RepoOption[]
}

export type TargetOp = 'gte' | 'lte' | 'abs_lte' | 'between' | 'eq'
export type ManualStatus = 'not_started' | 'in_progress' | 'met' | 'not_met'

export interface Claim {
  id: string
  key: string
  text: string
  metric_key: string | null
  target_op: TargetOp | null
  target_value: number | null
  target_value_hi: number | null
  manual_status: ManualStatus
  position: number
}

export const MANUAL_STATUS_LABEL: Record<ManualStatus, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  met: 'Met',
  not_met: 'Not met',
}

export function describeTarget(c: Claim): string {
  const v = c.target_value
  switch (c.target_op) {
    case 'gte': return `≥ ${v}`
    case 'lte': return `≤ ${v}`
    case 'abs_lte': return `within ±${v}`
    case 'between': return `between ${v} and ${c.target_value_hi}`
    case 'eq': return `= ${v}`
    default: return ''
  }
}

export async function getAvailableRepos(projectId: string): Promise<AvailableRepos> {
  return (await client.get<AvailableRepos>(`/projects/${projectId}/github/repos`)).data
}

export async function connectRepo(projectId: string, repoId: number): Promise<Project> {
  return (await client.post<Project>(`/projects/${projectId}/github/connect`, { repo_id: repoId })).data
}

export async function disconnectRepo(projectId: string): Promise<Project> {
  return (await client.delete<Project>(`/projects/${projectId}/github`)).data
}

export async function syncNow(projectId: string): Promise<Project> {
  return (await client.post<Project>(`/projects/${projectId}/sync`)).data
}

export async function listClaims(projectId: string): Promise<Claim[]> {
  return (await client.get<Claim[]>(`/projects/${projectId}/claims`)).data
}

export async function setClaimStatus(projectId: string, claimId: string, manual_status: ManualStatus): Promise<Claim> {
  return (await client.patch<Claim>(`/projects/${projectId}/claims/${claimId}`, { manual_status })).data
}
