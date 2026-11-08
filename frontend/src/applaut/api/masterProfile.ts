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

// Bullet bank builder (docs/applaut/APPLAUT_AI_V2_PLAN.md §4): Applaut AI drafts
// CV bullets for one role from your notes; nothing is saved until you keep it.

export interface DraftedBullet {
  text: string
  /** Numbers in neither your notes nor the role: check them before keeping. */
  confirm: string[]
}

export interface BulletDraft {
  id: string
  entry_id: string
  notes: string
  status: 'pending' | 'done' | 'failed'
  /** Queue items before this one, while pending. */
  ahead: number | null
  drafts: DraftedBullet[]
  left_out: { text: string; reason: string }[]
  error: string | null
  created_at: string
  finished_at: string | null
}

export async function draftBullets(entryId: string, notes: string): Promise<BulletDraft> {
  return (await client.post<BulletDraft>(`/master-profile/entries/${encodeURIComponent(entryId)}/draft-bullets`, { notes })).data
}

/** The role's open drafts, or null. */
export async function getBulletDrafts(entryId: string): Promise<BulletDraft | null> {
  return (await client.get<BulletDraft | null>(`/master-profile/entries/${encodeURIComponent(entryId)}/drafts`)).data
}

export async function discardBulletDrafts(entryId: string): Promise<void> {
  await client.delete(`/master-profile/entries/${encodeURIComponent(entryId)}/drafts`)
}

/** Appends the bullets you kept (as edited) to the role's facts. */
export async function addFacts(entryId: string, facts: string[], draftId?: string): Promise<MasterProfile> {
  return (await client.post<MasterProfile>(`/master-profile/entries/${encodeURIComponent(entryId)}/facts`,
    { facts, draft_id: draftId ?? null })).data
}

// A master profile drafted from your CV (docs/applaut/APPLAUT_AI_V2_PLAN.md §5):
// Applaut AI points at your CV's lines and Applaut copies them into a draft,
// which you check and save in the editor. Nothing in it is new wording.

export interface ProfileImport {
  id: string
  file_name: string
  status: 'reading' | 'ready' | 'failed'
  /** Queue items before this one, while reading. */
  ahead: number | null
  /** The draft as YAML, once ready. */
  yaml: string | null
  /** What was left out, or still needs filling in. */
  notes: string[]
  error: string | null
  created_at: string
  finished_at: string | null
}

export async function importCv(file: File): Promise<ProfileImport> {
  const form = new FormData()
  form.append('file', file)
  return (await client.post<ProfileImport>('/master-profile/import', form,
    { headers: { 'Content-Type': 'multipart/form-data' } })).data
}

/** The open draft from your CV, or null. */
export async function getProfileImport(): Promise<ProfileImport | null> {
  return (await client.get<ProfileImport | null>('/master-profile/import')).data
}

/** Done with the draft (saved or dropped); Applaut deletes the CV's text. */
export async function closeProfileImport(): Promise<void> {
  await client.delete('/master-profile/import')
}
