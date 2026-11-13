import client from './client'

export type GenerationMode = 'template' | 'ai'

export interface DocumentItem {
  id: string
  opportunity_id: string
  document_type: string
  generation_mode: string
  content: string
  ai_model: string | null
  is_current: boolean
  created_at: string
  engine: 'basic' | 'applaut_ai' | 'own_routine'
  content_type: string
  /** A PDF exists; get a short-lived link with getDocumentFileLink. */
  has_file: boolean
  /** An Applaut AI CV whose bullets can be switched (getCvDetails). */
  has_details: boolean
}

export type BulletVersion = 'tailored' | 'original'

export interface CvBullet {
  fact_id: string
  /** The role or project the bullet is listed under. */
  entry: string
  original: string
  /** The wording written for this job, when one passed the checks. */
  tailored: string | null
  use: BulletVersion
  /** Why the fact is shown as written, when the model's wording wasn't used. */
  note: string | null
}

export interface CvDetails {
  document_id: string
  is_current: boolean
  bullets: CvBullet[]
}

export interface BulletChoiceResult {
  /** The CV's new current version. */
  document: DocumentItem
  details: CvDetails
}

export interface DocumentFileLink {
  url: string
  expires_in: number
  file_name: string
}

export interface OpportunityDocuments {
  opportunity_id: string
  tailored_resume: DocumentItem | null
  cover_letter: DocumentItem | null
}

export interface GenerateDocumentsResult {
  tailored_resume: DocumentItem
  cover_letter: DocumentItem
  mode: string
}

export async function generateDocuments(
  opportunityId: string,
  mode: GenerationMode = 'template',
): Promise<GenerateDocumentsResult> {
  const { data } = await client.post<GenerateDocumentsResult>(
    `/opportunities/${opportunityId}/documents?mode=${mode}`,
  )
  return data
}

export async function getOpportunityDocuments(
  opportunityId: string,
): Promise<OpportunityDocuments> {
  const { data } = await client.get<OpportunityDocuments>(
    `/opportunities/${opportunityId}/documents`,
  )
  return data
}

export async function getDocument(documentId: string): Promise<DocumentItem> {
  const { data } = await client.get<DocumentItem>(`/documents/${documentId}`)
  return data
}

export async function getDocumentFileLink(documentId: string): Promise<DocumentFileLink> {
  const { data } = await client.get<DocumentFileLink>(`/documents/${documentId}/file`)
  return data
}

export async function getCvDetails(documentId: string): Promise<CvDetails> {
  const { data } = await client.get<CvDetails>(`/documents/${documentId}/details`)
  return data
}

export async function chooseBulletVersion(
  documentId: string,
  factId: string,
  version: BulletVersion,
): Promise<BulletChoiceResult> {
  const { data } = await client.post<BulletChoiceResult>(
    `/documents/${documentId}/bullets/${encodeURIComponent(factId)}/use`,
    { version },
  )
  return data
}

/** Applaut AI: queue a failed CV and cover letter for this job once more. */
export async function writeDocumentsAgain(opportunityId: string): Promise<{ docs_status: string }> {
  const { data } = await client.post<{ docs_status: string }>(`/opportunities/${opportunityId}/documents/write-again`)
  return data
}
