import client, { API_BASE } from './client'

export type ProshoRole = 'student' | 'mentor' | 'admin'

export interface ProshoUser {
  id: string
  github_login: string
  name: string | null
  email: string | null
  avatar_url: string | null
  role: ProshoRole
}

// A full-page navigation, not an XHR: the backend redirects to GitHub, and
// GitHub back to the backend, which keeps the client secret server-side.
export const githubSignInUrl = `${API_BASE}/auth/github/authorize`

export async function exchangeLoginCode(code: string): Promise<string> {
  const { data } = await client.post<{ access_token: string }>('/auth/exchange', { code })
  return data.access_token
}

export async function getMe(): Promise<ProshoUser> {
  const { data } = await client.get<ProshoUser>('/auth/me')
  return data
}
