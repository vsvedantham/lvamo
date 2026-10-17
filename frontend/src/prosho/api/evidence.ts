import client from './client'

export interface IngestToken {
  id: string
  label: string
  token_prefix: string
  last_used_at: string | null
  revoked_at: string | null
  created_at: string
}

export interface CreatedToken extends IngestToken {
  token: string // shown once
}

export interface Evidence {
  id: string
  module: string
  kind: 'metric' | 'check' | 'artifact' | 'run'
  key: string
  value_num: number | null
  value_text: string | null
  unit: string | null
  payload: Record<string, unknown> | null
  commit_sha: string | null
  source: 'ci' | 'webhook' | 'scheduler' | 'manual'
  recorded_at: string
}

export interface SourcePanelItem {
  name: string
  url: string
  licence: string | null
  status: 'pass' | 'fail' | 'warn' | 'unchecked'
  checked_at: string | null
  detail: string | null
  status_code: number | null
}

export interface MetricPanelItem {
  key: string
  value: number | null
  unit: string | null
  recorded_at: string
  commit_sha: string | null
  claim_text: string | null
  target_op: string | null
  target_value: number | null
  target_value_hi: number | null
  status: 'met' | 'not_met' | 'awaiting_evidence' | null
}

export interface RunPanelItem {
  key: string
  status: string | null
  recorded_at: string
  commit_sha: string | null
  details: { duration_s?: number; tests_passed?: number; tests_total?: number; url?: string }
}

export interface DataModule {
  sources: SourcePanelItem[]
  metrics: MetricPanelItem[]
  runs: RunPanelItem[]
}

export const listTokens = async (pid: string) => (await client.get<IngestToken[]>(`/projects/${pid}/tokens`)).data
export const createToken = async (pid: string, label: string) =>
  (await client.post<CreatedToken>(`/projects/${pid}/tokens`, { label })).data
export const revokeToken = async (pid: string, tid: string) =>
  (await client.delete<IngestToken>(`/projects/${pid}/tokens/${tid}`)).data
export const listEvidence = async (pid: string, limit = 20) =>
  (await client.get<Evidence[]>(`/projects/${pid}/evidence`, { params: { limit } })).data
export const getDataModule = async (pid: string) => (await client.get<DataModule>(`/projects/${pid}/data-module`)).data
export const checkSourcesNow = async (pid: string) => (await client.post<DataModule>(`/projects/${pid}/sources/check`)).data

/** "3 min ago", "2 h ago", "4 days ago" — for evidence timestamps. */
export function timeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  const d = Math.floor(s / 86400)
  return `${d} day${d === 1 ? '' : 's'} ago`
}

export function formatValue(value: number | null, unit: string | null): string {
  if (value === null) return '—'
  const n = Number.isInteger(value) ? String(value) : value.toFixed(Math.abs(value) < 1 ? 3 : 2).replace(/\.?0+$/, '')
  return unit ? `${n} ${unit}` : n
}
