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
}): Promise<OpportunityList> {
  const { data } = await client.get<OpportunityList>('/opportunities', { params })
  return data
}

export async function getOpportunity(id: string): Promise<OpportunityDetail> {
  const { data } = await client.get<OpportunityDetail>(`/opportunities/${id}`)
  return data
}
