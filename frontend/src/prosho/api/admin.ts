import client from './client'
import type { ProshoRole } from './auth'
import type { Visibility } from './projects'
import type { Person } from './team'

export interface AdminUser extends Person {
  role: ProshoRole
  is_active: boolean
  created_at: string
  projects_owned: number
}

export interface AdminProject {
  id: string
  slug: string
  title: string
  visibility: Visibility
  is_active: boolean
  repo_full_name: string | null
  owner: Person
  mentors: Person[]
  created_at: string
}

export interface AuditEntry {
  id: string
  actor_login: string | null
  action: string
  entity: string
  entity_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  created_at: string
}

export const listUsers = async () => (await client.get<AdminUser[]>('/admin/users')).data
export const updateUser = async (id: string, body: { role?: ProshoRole; is_active?: boolean }) =>
  (await client.patch<AdminUser[]>(`/admin/users/${id}`, body)).data
export const listAllProjects = async () => (await client.get<AdminProject[]>('/admin/projects')).data
export const setProjectActive = async (id: string, is_active: boolean) =>
  (await client.patch<AdminProject[]>(`/admin/projects/${id}`, { is_active })).data
export const assignMentor = async (pid: string, mentor_id: string) =>
  (await client.post<AdminProject[]>(`/admin/projects/${pid}/mentors`, { mentor_id })).data
export const removeMentor = async (pid: string, mentor_id: string) =>
  (await client.delete<AdminProject[]>(`/admin/projects/${pid}/mentors/${mentor_id}`)).data
export const getAuditLog = async (before?: string) =>
  (await client.get<AuditEntry[]>('/admin/audit', { params: { limit: 100, before } })).data
