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
