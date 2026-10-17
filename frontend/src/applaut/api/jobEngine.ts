import client from './client'
import type { JobEngine } from './profile'

export interface RoutineConnection {
  neon_host: string
  neon_saved: boolean
  r2_account_id: string
  r2_bucket: string
  r2_prefix: string
  r2_access_key_hint: string
  r2_secret_saved: boolean
  routine_url: string | null
  schedule_cron: string
  timezone: string
  contract_version: number | null
  status: 'setup' | 'active' | 'error' | 'paused'
  verified_at: string | null
  last_check_at: string | null
  last_error: string | null
  consecutive_failures: number
  created_at: string
  updated_at: string
}

export type RunOutcome = 'running' | 'succeeded' | 'problems' | 'failed' | 'stopped' | 'missed'

export interface RoutineRun {
  id: string
  run_id: string | null
  expected_at: string | null
  outcome: RunOutcome
  message: string
  contract_version: number | null
  started_at: string | null
  finished_at: string | null
  status: string | null
  current_step: string | null
  error: string | null
  searches_run: number | null
  search_budget: number | null
  postings_found: number | null
  postings_assessed: number | null
  jobs_eligible: number | null
  jobs_new: number | null
  jobs_updated: number | null
  jobs_rejected: number | null
  docs_done: number | null
  docs_failed: number | null
  sources_failed: string | null
  summary: string | null
}

export interface RoutineSync {
  id: string
  trigger: 'scheduled' | 'manual' | 'initial'
  run_id: string | null
  status: 'running' | 'succeeded' | 'partial' | 'failed'
  started_at: string
  finished_at: string | null
  rows_read: number
  jobs_new: number
  jobs_updated: number
  jobs_removed: number
  docs_copied: number
  docs_skipped: number
  problems: string[]
  error: string | null
}

export type CardState =
  | 'setup_incomplete' | 'waiting' | 'running' | 'healthy' | 'problems' | 'failed'
  | 'stopped' | 'didnt_run' | 'cant_connect' | 'no_run_details'

export interface EngineCard {
  state: CardState
  label: string
  message: string
  paused: boolean
  last_run: RoutineRun | null
  last_sync: RoutineSync | null
  next_run_at: string | null
  next_sync_at: string | null
  next_sync_estimated: boolean
  sync_running: boolean
  sync_now_available_at: string | null
  routine_url: string | null
}

export interface JobEngineState {
  engine: JobEngine
  engine_changed_at: string | null
  credentials_storage_ready: boolean
  connection: RoutineConnection | null
  card: EngineCard | null
}

export interface ConnectionInput {
  neon_url?: string
  r2_account_id?: string
  r2_bucket?: string
  r2_prefix?: string
  r2_access_key_id?: string
  r2_secret?: string
  routine_url?: string | null
  schedule_cron?: string
  timezone?: string
}

export interface CheckResult {
  key: string
  label: string
  ok: boolean
  message: string
}

export interface ConnectionTest {
  ok: boolean
  checks: CheckResult[]
  contract_version: number | null
}

export async function getJobEngine(): Promise<JobEngineState> {
  return (await client.get('/job-engine')).data
}

export async function setJobEngine(engine: JobEngine, confirmDeleteCredentials = false): Promise<JobEngineState> {
  return (await client.put('/job-engine', { engine, confirm_delete_credentials: confirmDeleteCredentials })).data
}

export async function testRoutineConnection(data: ConnectionInput): Promise<ConnectionTest> {
  return (await client.post('/job-engine/routine/test', data)).data
}

/** Resolves to the new state, or rejects with an axios error whose
 * response.data holds `checks` when a check failed (nothing is saved then). */
export async function saveRoutineConnection(data: ConnectionInput): Promise<JobEngineState> {
  return (await client.put('/job-engine/routine', data)).data
}

export async function removeRoutineConnection(): Promise<void> {
  await client.delete('/job-engine/routine')
}

export async function syncRoutineNow(): Promise<{ queued: boolean; message: string; card: EngineCard }> {
  return (await client.post('/job-engine/routine/sync-now')).data
}

export async function listRoutineRuns(limit = 50): Promise<RoutineRun[]> {
  return (await client.get('/job-engine/routine/runs', { params: { limit } })).data
}

export async function listRoutineSyncs(limit = 20): Promise<RoutineSync[]> {
  return (await client.get('/job-engine/routine/syncs', { params: { limit } })).data
}

/** FastAPI error detail as a sentence. */
export function errorMessage(err: unknown, fallback = 'Something went wrong'): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, '')
  return fallback
}
