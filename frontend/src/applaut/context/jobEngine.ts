import { useEffect, useState } from 'react'
import { getMyProfile, type JobEngine } from '../api/profile'

// The signed-in user's job engine for parts of the app that only differ by it
// (the sidebar hides Resume for Applaut AI). Loaded once per user; Settings
// and onboarding announce a change so every user of the hook updates at once.

const EVENT = 'applaut:job-engine'
let cached: { userId: string; engine: JobEngine } | null = null

export function announceJobEngine(userId: string, engine: JobEngine) {
  cached = { userId, engine }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: cached }))
}

/** null until known (or with no profile yet). */
export function useJobEngine(userId: string | undefined): JobEngine | null {
  const [engine, setEngine] = useState<JobEngine | null>(cached && cached.userId === userId ? cached.engine : null)
  useEffect(() => {
    if (!userId) { setEngine(null); return }
    const on = (e: Event) => {
      const d = (e as CustomEvent<{ userId: string; engine: JobEngine }>).detail
      if (d.userId === userId) setEngine(d.engine)
    }
    window.addEventListener(EVENT, on)
    if (cached?.userId === userId) setEngine(cached.engine)
    else getMyProfile().then(p => announceJobEngine(userId, p.job_engine)).catch(() => setEngine(null))
    return () => window.removeEventListener(EVENT, on)
  }, [userId])
  return engine
}
