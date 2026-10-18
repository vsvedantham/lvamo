import client from './client'

export type JobEngine = 'basic' | 'applaut_ai' | 'own_routine'

export const JOB_ENGINE_LABELS: Record<JobEngine, string> = {
  basic: 'Applaut Basic',
  applaut_ai: 'Applaut AI',
  own_routine: 'Your Claude routine',
}

export interface Profile {
  id: string
  user_id: string
  display_name: string
  total_experience_years: number | null
  target_roles: string[]
  target_countries: string[]
  remote_preference: string
  employment_types: string[]
  skills: string[]
  languages: string[]
  discovery_frequency_hours: number
  discovery_enabled: boolean
  good_threshold: number
  near_miss_threshold: number
  job_engine: JobEngine
  created_at: string
  updated_at: string
}

export interface CreateProfilePayload {
  display_name: string
  total_experience_years?: number
  target_roles: string[]
  target_countries: string[]
  remote_preference: string
  employment_types: string[]
  skills: string[]
  languages: string[]
  discovery_frequency_hours: number
  good_threshold?: number
  /** Chosen in onboarding; Applaut AI isn't available yet. */
  job_engine?: 'basic' | 'own_routine'
  /** Applaut Basic only: run discovery automatically every discovery_frequency_hours. */
  discovery_enabled?: boolean
}

export async function createProfile(data: CreateProfilePayload): Promise<Profile> {
  const { data: res } = await client.post<Profile>('/profiles', data)
  return res
}

export async function getMyProfile(): Promise<Profile> {
  const { data } = await client.get<Profile>('/profiles/me')
  return data
}

export async function updateMyProfile(
  data: Partial<CreateProfilePayload>,
): Promise<Profile> {
  const { data: res } = await client.patch<Profile>('/profiles/me', data)
  return res
}
