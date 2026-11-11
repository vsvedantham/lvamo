import client, { API_ROOT } from './client'

export type UserType = 'employee' | 'job_seeker'
export type ReferFrequency = 'weekly' | 'monthly'
export type ReferralViewCapacity = 'up_to_5' | '5_to_10' | '10_to_20' | 'no_cap'
export type JobSeekerStatus = 'none' | 'part_time' | 'mini_job' | 'serving_notice'

export interface EmployeeDetails {
  company_name: string
  working_since: string // YYYY-MM-DD
  daily_referral_view_cap: ReferralViewCapacity
  // Always asked directly now — no more "can you refer at all?" gate.
  // referral_capacity reuses the same bucketed scale as
  // daily_referral_view_cap, per spec.
  refer_frequency: ReferFrequency
  referral_capacity: ReferralViewCapacity
  company_careers_url: string
}

export interface SeekerDetails {
  current_job_status: JobSeekerStatus
  notice_join_date?: string | null // YYYY-MM-DD, only when serving_notice
  cv_drive_link: string
}

// Two distinct shapes, matching the backend's discriminated union
// (schemas/auth.py) — employees register directly, job seekers go through
// LinkedIn OAuth first. See jobref/pages/Register.tsx for the split UI.
export interface EmployeeRegisterPayload {
  user_type: 'employee'
  first_name: string
  last_name: string
  email: string
  phone: string
  password: string
  domain: string
  employee: EmployeeDetails
  // Only while emailed codes are on for Jobref (platform setting).
  email_code?: string
}

export interface SeekerRegisterPayload {
  user_type: 'job_seeker'
  // Proves LinkedIn OAuth was completed; the account's email/LinkedIn
  // identity is always sourced server-side from this token, never from a
  // client-submitted email field.
  registration_token: string
  first_name: string
  last_name: string
  phone: string
  password: string
  domain: string
  seeker: SeekerDetails
}

export type RegisterPayload = EmployeeRegisterPayload | SeekerRegisterPayload

export interface LinkedInPrefill {
  first_name: string
  last_name: string
  email: string
  email_verified: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface JobrefUser {
  id: string
  first_name: string
  last_name: string
  email: string
  phone: string
  user_type: UserType
  domain: string
  is_active: boolean
  created_at: string
  employee_profile: EmployeeDetails | null
  seeker_profile: SeekerDetails | null
}

export async function register(payload: RegisterPayload): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>('/auth/register', payload)
  return data
}

// Not a client.ts call — the OAuth handshake itself is a full-page
// navigation (not XHR) so the LinkedIn Client Secret never has to reach
// the frontend; the backend does the code exchange server-side.
export function linkedInAuthorizeUrl(): string {
  return `${API_ROOT}/api/v1/jobref/auth/linkedin/authorize`
}

export async function getLinkedInPrefill(token: string): Promise<LinkedInPrefill> {
  const { data } = await client.get<LinkedInPrefill>('/auth/linkedin/prefill', { params: { token } })
  return data
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>('/auth/login', { email, password })
  return data
}

export async function getMe(): Promise<JobrefUser> {
  const { data } = await client.get<JobrefUser>('/auth/me')
  return data
}

// Everything editable except email (identity/dedup key — never editable).
// Mirrors RegisterPayload's shape: exactly one of employee/seeker, matching
// the caller's own account type.
export interface ProfileUpdatePayload {
  first_name: string
  last_name: string
  phone: string
  domain: string
  employee?: EmployeeDetails
  seeker?: SeekerDetails
}

export async function updateProfile(payload: ProfileUpdatePayload): Promise<JobrefUser> {
  const { data } = await client.patch<JobrefUser>('/auth/me', payload)
  return data
}
