import client from './client'

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: string
  name: string
  email: string
  is_active: boolean
  is_verified: boolean
  created_at: string
}

export async function register(
  name: string,
  email: string,
  password: string,
  emailCode?: string,
): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>('/auth/register', {
    name,
    email,
    password,
    // Only while emailed codes are on for Applaut (platform setting).
    ...(emailCode ? { email_code: emailCode } : {}),
  })
  return data
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>('/auth/login', {
    email,
    password,
  })
  return data
}

export async function getMe(): Promise<User> {
  const { data } = await client.get<User>('/auth/me')
  return data
}
