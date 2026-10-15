import client from './client'

export type ProjectType = 'data_science' | 'frontend'
export type Visibility = 'private' | 'unlisted' | 'public'
export type DemoKind = 'streamlit' | 'url' | 'video'

export interface ManifestError {
  line: number | null
  path: string
  message: string
}

export interface Project {
  id: string
  slug: string
  title: string
  summary: string | null
  problem: string | null
  project_type: ProjectType
  university: string | null
  programme: string | null
  visibility: Visibility
  supervisor_ok_at: string | null
  repo_full_name: string | null
  demo_kind: DemoKind | null
  demo_url: string | null
  manifest_sha: string | null
  manifest_synced_at: string | null
  manifest_errors: ManifestError[] | null
  published_at: string | null
  created_at: string
  updated_at: string
  manifest_managed: boolean
}

export interface ProjectUpdate {
  title?: string
  slug?: string
  university?: string | null
  programme?: string | null
  visibility?: Visibility
  supervisor_confirmed?: boolean
  demo_kind?: DemoKind | null
  demo_url?: string | null
}

export const PROJECT_TYPE_LABEL: Record<ProjectType, string> = {
  data_science: 'Data science',
  frontend: 'Website / frontend',
}

export async function listProjects(): Promise<Project[]> {
  return (await client.get<Project[]>('/projects')).data
}

export async function createProject(body: { title: string; slug: string; project_type: ProjectType }): Promise<Project> {
  return (await client.post<Project>('/projects', body)).data
}

export async function getProject(id: string): Promise<Project> {
  return (await client.get<Project>(`/projects/${id}`)).data
}

export async function updateProject(id: string, body: ProjectUpdate): Promise<Project> {
  return (await client.patch<Project>(`/projects/${id}`, body)).data
}

/** FastAPI errors are a string (409/404) or a list of field errors (422). */
export function apiErrorMessage(err: any, fallback = 'Something went wrong. Please try again.'): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: any) => String(d.msg ?? '').replace(/^Value error, /, '')).filter(Boolean).join(' · ') || fallback
  }
  return fallback
}
