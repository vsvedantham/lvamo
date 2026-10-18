import client from './client'

export interface ScoreDimension {
  score: number
  max: number
  explanation: string
}

export interface NearMissKeyword {
  keyword: string
  suitable: boolean | null
  reason: string
}

export interface OpportunityScore {
  id: string
  total_score: number
  explanation: Record<string, ScoreDimension>
  scoring_mode: string
  near_miss_keywords: NearMissKeyword[] | null
  user_decision: string | null
  created_at: string
}

/** An AI engine's verdict on a job: match %, must-have skills matched / missing, things to check. */
export interface Assessment {
  engine: 'applaut_ai' | 'own_routine'
  match_score: number | null
  matched_skills: string[]
  missing_skills: string[]
  german_required: string | null
  seniority: string | null
  notes: string | null
  flags: string[]
  first_seen_at: string
  last_seen_at: string
  times_seen: number
}

export type TrackingState = 'open' | 'applied' | 'unavailable'

/** Where you are with a job (backed by your application for it). */
export interface Tracking {
  state: TrackingState
  application_id: string | null
  /** pending_review | submitted | interviewing | offered | rejected | closed | withdrawn … */
  status: string | null
  applied_at: string | null
  updated_at: string | null
}

/** The job's folder in your own routine's output (and on your Mac, via its sync). */
export interface RoutineJobRef {
  uid: string
  docs_ready: boolean
  removed: boolean
}

export interface Opportunity {
  id: string
  source: string
  title: string
  company_name: string
  location_raw: string | null
  country_code: string | null
  remote_option: string | null
  employment_type: string | null
  application_url: string | null
  posted_at: string | null
  is_active: boolean
  created_at: string
  /** True when an AI engine brought this job in for you only. */
  is_private: boolean
  score: OpportunityScore | null
  assessment: Assessment | null
  tracking: Tracking
  routine: RoutineJobRef | null
}

export interface OpportunityDetail extends Opportunity {
  description: string | null
  requirements: string | null
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  assessment: Assessment | null
}

export type MatchFilter = 'all' | 'good' | 'near_miss' | 'below' | 'unscored'
export type EngineFilter = 'basic' | 'applaut_ai' | 'own_routine'

/** The score a job is ranked by: an AI engine's match % if there is one, else Applaut's rule-based score. */
export function effectiveScore(opp: Opportunity): number | null {
  return opp.assessment?.match_score ?? opp.score?.total_score ?? null
}

export interface OpportunityList {
  items: Opportunity[]
  total: number
  page: number
  page_size: number
  good_threshold: number
  near_miss_threshold: number
  counts: Record<TrackingState | 'all', number>
  /** Whether Applaut Basic's shared jobs are in this list. */
  include_shared: boolean
}

export interface DiscoveryRunResponse {
  new_jobs_found: number
  scored: number
  good_matches: number
  near_misses: number
  message: string
}

export async function runDiscovery(): Promise<DiscoveryRunResponse> {
  const { data } = await client.post<DiscoveryRunResponse>('/discovery/run')
  return data
}

export async function listOpportunities(params?: {
  page?: number
  page_size?: number
  country_code?: string
  source?: string
  match?: MatchFilter
  engine?: EngineFilter
  state?: TrackingState | 'all'
  /** Default: yes, except for accounts on their own Claude routine. */
  include_shared?: boolean
}): Promise<OpportunityList> {
  const { data } = await client.get<OpportunityList>('/opportunities', { params })
  return data
}

export async function setTracking(
  id: string, state: TrackingState, reason?: 'closed' | 'cannot_apply',
): Promise<Tracking> {
  const { data } = await client.put<Tracking>(`/opportunities/${id}/tracking`, { state, reason })
  return data
}

// The folder your Mac's sync copies the routine's documents into. It's a
// per-computer setting, so it lives in this browser, not on the server.
const LOCAL_FOLDER_KEY = 'applaut_local_docs_folder'
export const DEFAULT_LOCAL_FOLDER = '~/JobSearchDocuments'

export function getLocalDocsFolder(): string {
  try {
    return localStorage.getItem(LOCAL_FOLDER_KEY) || DEFAULT_LOCAL_FOLDER
  } catch {
    return DEFAULT_LOCAL_FOLDER
  }
}

export function setLocalDocsFolder(path: string): void {
  try {
    const clean = path.trim().replace(/\/+$/, '')
    if (clean && clean !== DEFAULT_LOCAL_FOLDER) localStorage.setItem(LOCAL_FOLDER_KEY, clean)
    else localStorage.removeItem(LOCAL_FOLDER_KEY)
  } catch { /* storage blocked: the default is used */ }
}

export async function getOpportunity(id: string): Promise<OpportunityDetail> {
  const { data } = await client.get<OpportunityDetail>(`/opportunities/${id}`)
  return data
}
