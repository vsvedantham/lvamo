import client from './client'

export interface Person {
  id: string
  github_login: string
  name: string | null
  avatar_url: string | null
}

export interface Milestone {
  id: string
  title: string
  due_on: string | null // YYYY-MM-DD
  completed_at: string | null
  reviewed_at: string | null
  reviewed_by: Person | null
  position: number
  created_at: string
}

export interface MilestoneUpdate {
  title?: string
  due_on?: string | null
  completed?: boolean
  reviewed?: boolean
}

export interface FeedbackMessage {
  id: string
  author: Person | null
  author_role: 'owner' | 'mentor' | null
  body: string
  created_at: string
}

export interface FeedbackThread extends FeedbackMessage {
  milestone_id: string | null
  milestone_title: string | null
  claim_id: string | null
  claim_text: string | null
  resolved_at: string | null
  replies: FeedbackMessage[]
}

export interface FeedbackCreate {
  body: string
  parent_id?: string
  milestone_id?: string
  claim_id?: string
}

export interface TimelineWeek { week_start: string; commits: number }
export interface TimelineCommit { sha: string; message: string; author_login: string | null; committed_at: string; url: string }
export interface Timeline {
  weeks: TimelineWeek[]
  total_commits: number
  last_commit_at: string | null
  commits: TimelineCommit[] | null // null: messages hidden (private repo, public page)
}

export interface PageStats {
  days: { day: string; views: number }[]
  total_views: number
  hub_clicks: number
  referrers: { domain: string; views: number }[]
}

const base = (pid: string) => `/projects/${pid}`

export const listMilestones = async (pid: string) => (await client.get<Milestone[]>(`${base(pid)}/milestones`)).data
export const createMilestone = async (pid: string, body: { title: string; due_on: string | null }) =>
  (await client.post<Milestone>(`${base(pid)}/milestones`, body)).data
export const updateMilestone = async (pid: string, mid: string, body: MilestoneUpdate) =>
  (await client.patch<Milestone>(`${base(pid)}/milestones/${mid}`, body)).data
export const deleteMilestone = async (pid: string, mid: string) => { await client.delete(`${base(pid)}/milestones/${mid}`) }

export const listFeedback = async (pid: string) => (await client.get<FeedbackThread[]>(`${base(pid)}/feedback`)).data
export const postFeedback = async (pid: string, body: FeedbackCreate) =>
  (await client.post<FeedbackThread[]>(`${base(pid)}/feedback`, body)).data
export const setFeedbackResolved = async (pid: string, fid: string, resolved: boolean) =>
  (await client.patch<FeedbackThread[]>(`${base(pid)}/feedback/${fid}`, { resolved })).data

export const getTimeline = async (pid: string) => (await client.get<Timeline | null>(`${base(pid)}/timeline`)).data
export const getPageStats = async (pid: string, days = 30) =>
  (await client.get<PageStats>(`${base(pid)}/stats`, { params: { days } })).data

/** "15 Nov 2026" from a YYYY-MM-DD date, without timezone shifts. */
export function formatDay(day: string, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, { ...opts, timeZone: 'UTC' })
}
