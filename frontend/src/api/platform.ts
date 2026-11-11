// LVAMO platform API (api.lvamo.com): settings and email codes, shared by
// every vertical. Plain fetch, no auth: these endpoints are public by design.
export const PLATFORM_API_BASE =
  (import.meta.env.VITE_PLATFORM_API_BASE_URL ?? 'http://localhost:8000') + '/api/v1/platform'

export type EmailCodePurpose = 'register' | 'reset_password'

export class PlatformApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${PLATFORM_API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new PlatformApiError(0, 'Could not reach the server. Check your connection and try again.')
  }
  if (!res.ok) {
    let message = 'Something went wrong. Please try again.'
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') message = body.detail
      else if (Array.isArray(body?.detail) && body.detail.length) {
        message = body.detail.map((d: any) => String(d?.msg ?? 'invalid value').replace(/^Value error, /, '')).join(' · ')
      }
    } catch { /* not JSON */ }
    throw new PlatformApiError(res.status, message)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

export async function getPublicSetting(name: string): Promise<string | null> {
  try {
    const data = await call<{ value: string }>(`/settings/${encodeURIComponent(name)}`)
    return data.value
  } catch {
    return null
  }
}

/** Is sign-up / password reset by emailed code on for this vertical?
 * (`otp_verification_enabled` in platform.settings, comma-separated). */
export async function emailCodesEnabled(vertical: string): Promise<boolean> {
  const value = await getPublicSetting('otp_verification_enabled')
  return (value ?? '').split(',').map(v => v.trim().toLowerCase()).includes(vertical)
}

export interface EmailCodeSent {
  resend_after_seconds: number
  expires_in_seconds: number
}

export function sendEmailCode(vertical: string, email: string, purpose: EmailCodePurpose): Promise<EmailCodeSent> {
  return call<EmailCodeSent>('/auth/email-codes', {
    method: 'POST',
    body: JSON.stringify({ vertical, email, purpose }),
  })
}

export function resetPassword(vertical: string, email: string, code: string, newPassword: string): Promise<void> {
  return call<void>('/auth/password-reset', {
    method: 'POST',
    body: JSON.stringify({ vertical, email, code, new_password: newPassword }),
  })
}
