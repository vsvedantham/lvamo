import client from './client'

// Applaut AI's master profile (docs/applaut/APPLAUT_AI_ENGINE_DESIGN.md §7.1):
// the Claude routine's master_profile.yaml shape, edited here as YAML.

export interface MasterProfile {
  data: Record<string, unknown>
  yaml: string
  version: number
  source: 'manual' | 'yaml'
  updated_at: string
}

export async function getMasterProfile(): Promise<MasterProfile | null> {
  try {
    return (await client.get<MasterProfile>('/master-profile')).data
  } catch (err: any) {
    if (err?.response?.status === 404) return null
    throw err
  }
}

/** Saves, or throws; a validation failure carries one line per problem in `errors`. */
export async function saveMasterProfileYaml(yaml: string): Promise<MasterProfile> {
  return (await client.put<MasterProfile>('/master-profile', { yaml })).data
}

export function validationErrors(err: unknown): string[] {
  const errors = (err as { response?: { data?: { errors?: unknown } } })?.response?.data?.errors
  return Array.isArray(errors) ? errors.map(String) : []
}

/** Opens the saved profile's CV or cover-letter preview PDF in a new tab. */
export async function openPreview(kind: 'cv' | 'cover_letter'): Promise<void> {
  const tab = window.open('', '_blank')  // opened synchronously so popup blockers allow it
  const res = await client.get(`/master-profile/preview/${kind}`, { responseType: 'blob' })
  const url = URL.createObjectURL(res.data as Blob)
  if (tab) tab.location.href = url
  else window.location.href = url
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
