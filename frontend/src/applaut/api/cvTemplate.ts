import client from './client'

// Your own CV template (docs/applaut/APPLAUT_AI_V2_PLAN.md §5): upload your
// .docx CV once; Applaut AI reads it, and every new CV keeps its layout with
// only the headline, skills, bullets and technologies filled in per job.

export type CvTemplateStatus = 'reading' | 'ready' | 'failed' | 'active' | 'retired' | 'discarded'

export interface CvTemplateReport {
  headline?: boolean
  roles?: { heading: string; bullets: number; technologies: boolean; entry: string | null }[]
  rows?: { label: string; row: string | null }[]
  differences?: string[]
  fonts?: { font: string; shown_as: string }[]
  notes?: string[]
}

export interface CvTemplate {
  id: string
  file_name: string
  status: CvTemplateStatus
  ahead: number | null
  pages: number | null
  report: CvTemplateReport
  error: string | null
  can_use: boolean
  created_at: string
  finished_at: string | null
  decided_at: string | null
}

export interface CvTemplateState {
  active: CvTemplate | null
  latest: CvTemplate | null
}

export async function getCvTemplates(): Promise<CvTemplateState> {
  return (await client.get<CvTemplateState>('/cv-template')).data
}

export async function uploadCvTemplate(file: File): Promise<CvTemplate> {
  const form = new FormData()
  form.append('file', file)
  return (await client.post<CvTemplate>('/cv-template', form, { headers: { 'Content-Type': 'multipart/form-data' } })).data
}

export async function useCvTemplate(id: string): Promise<CvTemplate> {
  return (await client.post<CvTemplate>(`/cv-template/${id}/use`)).data
}

/** Switch an active template off, or drop an upload that isn't on. */
export async function removeCvTemplate(id: string): Promise<void> {
  await client.delete(`/cv-template/${id}`)
}

export async function getTemplatePreviewLink(id: string, which: 'original' | 'rebuilt'): Promise<string> {
  return (await client.get<{ url: string }>(`/cv-template/${id}/preview/${which}`)).data.url
}
