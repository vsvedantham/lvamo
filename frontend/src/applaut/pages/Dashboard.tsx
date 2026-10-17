import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getMyProfile, JOB_ENGINE_LABELS, type Profile } from '../api/profile'
import { getJobEngine, type EngineCard } from '../api/jobEngine'
import RoutineEngineCard from '../components/RoutineEngineCard'
import { getMyResume, type Resume } from '../api/resume'
import { getDashboardStats, type DashboardStats } from '../api/stats'
import { disableDiscovery, enableDiscovery, getSchedulerStatus, type SchedulerStatus } from '../api/scheduler'

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function timeUntil(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return 'any moment'
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  return `${Math.floor(hrs / 24)}d`
}

function StatCard({ label, value, sub, href, color }: {
  label: string; value: number | string; sub?: string; href?: string; color?: string
}) {
  const inner = (
    <div style={{
      padding: '1.25rem',
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      display: 'flex',
      flexDirection: 'column',
      gap: '0.3rem',
      transition: 'border-color 0.15s',
    }}
      onMouseEnter={e => href && ((e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-strong)')}
      onMouseLeave={e => href && ((e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border)')}
    >
      <p style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>{label}</p>
      <p style={{ fontSize: '1.875rem', fontWeight: 700, margin: 0, color: color ?? 'var(--text-1)', lineHeight: 1.1, fontVariantNumeric: 'tabular-nums' }}>{value}</p>
      {sub && <p style={{ fontSize: '0.72rem', color: 'var(--text-3)', margin: 0 }}>{sub}</p>}
    </div>
  )
  if (href) return <Link to={href} style={{ textDecoration: 'none' }}>{inner}</Link>
  return inner
}

function DiscoveryWidget({ hasProfile }: { hasProfile: boolean }) {
  const [sched, setSched] = useState<SchedulerStatus | null>(null)
  const [toggling, setToggling] = useState(false)

  useEffect(() => {
    if (!hasProfile) return
    getSchedulerStatus().then(setSched).catch(() => null)
  }, [hasProfile])

  if (!hasProfile || !sched) return null

  const nextRun = sched.jobs[0]?.next_run_at ?? null
  const enabled = sched.discovery_enabled

  const toggle = async () => {
    setToggling(true)
    try {
      const updated = enabled ? await disableDiscovery() : await enableDiscovery()
      setSched(updated)
    } finally {
      setToggling(false)
    }
  }

  return (
    <div style={{
      padding: '1rem 1.25rem',
      background: 'var(--bg-surface)',
      border: `1px solid ${enabled ? 'var(--success-border)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '1rem',
      flexWrap: 'wrap',
      marginBottom: '1.25rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.875rem' }}>
        <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: enabled ? 'var(--success)' : 'var(--text-3)', flexShrink: 0, boxShadow: enabled ? '0 0 6px var(--success)' : 'none' }} />
        <div>
          <p style={{ margin: 0, fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-1)' }}>
            Auto discovery — {enabled ? `every ${sched.discovery_frequency_hours}h` : 'off'}
          </p>
          <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-2)' }}>
            {sched.last_discovery_at ? `Last run ${timeAgo(sched.last_discovery_at)}` : 'Never run'}
            {enabled && nextRun ? ` · Next in ${timeUntil(nextRun)}` : ''}
          </p>
        </div>
      </div>
      <button
        onClick={toggle}
        disabled={toggling}
        style={{
          padding: '0.375rem 0.875rem',
          background: enabled ? 'var(--danger-bg)' : 'var(--success-bg)',
          color: enabled ? 'var(--danger)' : 'var(--success)',
          border: `1px solid ${enabled ? 'var(--danger-border)' : 'var(--success-border)'}`,
          borderRadius: 'var(--radius-xs)',
          cursor: 'pointer',
          fontSize: '0.8rem',
          fontWeight: 500,
          opacity: toggling ? 0.7 : 1,
        }}
      >
        {toggling ? '…' : enabled ? 'Disable' : 'Enable'}
      </button>
    </div>
  )
}

function EngineWidget({ profile }: { profile: Profile | null }) {
  const [card, setCard] = useState<EngineCard | null>(null)

  useEffect(() => {
    if (profile?.job_engine !== 'own_routine') return
    getJobEngine().then(s => setCard(s.card)).catch(() => null)
  }, [profile?.job_engine])

  if (!profile) return null
  if (profile.job_engine === 'basic') return <DiscoveryWidget hasProfile />
  if (profile.job_engine !== 'own_routine' || !card) return null
  return <div style={{ marginBottom: '1.25rem' }}><RoutineEngineCard card={card} onChange={setCard} /></div>
}

function SetupCard({ title, description, href, cta }: { title: string; description: string; href: string; cta: string }) {
  return (
    <div style={{ padding: '1.25rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div>
        <p style={{ fontWeight: 600, fontSize: '0.9rem', margin: '0 0 0.3rem', color: 'var(--text-1)' }}>{title}</p>
        <p style={{ color: 'var(--text-2)', fontSize: '0.8rem', margin: 0 }}>{description}</p>
      </div>
      <Link
        to={href}
        style={{ alignSelf: 'flex-start', padding: '0.4rem 0.9rem', background: 'var(--accent)', color: '#fff', borderRadius: 'var(--radius-xs)', fontSize: '0.8rem', fontWeight: 500, textDecoration: 'none' }}
      >
        {cta}
      </Link>
    </div>
  )
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ padding: '1.25rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <p style={{ fontWeight: 600, fontSize: '0.9rem', margin: '0 0 0.2rem', color: 'var(--text-1)' }}>{title}</p>
      {children}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <p style={{ fontSize: '0.825rem', margin: 0, color: 'var(--text-2)' }}>
      <span style={{ color: 'var(--text-1)', fontWeight: 500 }}>{label}: </span>{value}
    </p>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [resume, setResume] = useState<Resume | null>(null)
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([getMyProfile(), getMyResume(), getDashboardStats()]).then(([p, r, s]) => {
      setProfile(p.status === 'fulfilled' ? p.value : null)
      setResume(r.status === 'fulfilled' ? r.value : null)
      setStats(s.status === 'fulfilled' ? s.value : null)
      setLoading(false)
    })
  }, [])

  return (
    <div style={{ maxWidth: '760px' }}>
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.25rem', color: 'var(--text-1)' }}>Dashboard</h1>
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', margin: 0 }}>
          Welcome back, <strong style={{ color: 'var(--text-1)' }}>{user?.name}</strong>
        </p>
      </div>

      {loading ? (
        <p style={{ color: 'var(--text-2)' }}>Loading…</p>
      ) : (
        <>
          <EngineWidget profile={profile} />

          {stats && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' }}>
              <StatCard label="Jobs found" value={stats.opportunities_found} href="/applaut/opportunities" />
              <StatCard label="Good matches" value={stats.good_matches} href="/applaut/opportunities?match=good" color="var(--success)" />
              <StatCard label="Near misses" value={stats.near_misses} href="/applaut/opportunities?match=near_miss" color="var(--warn)" />
              <StatCard label="Documents" value={stats.documents_generated} sub="resumes + letters" />
              <StatCard
                label="Applications"
                value={stats.applications.total}
                href="/applaut/applications"
                color={stats.applications.offered ? 'var(--purple)' : undefined}
                sub={
                  stats.applications.interviewing ? `${stats.applications.interviewing} interviewing` :
                  stats.applications.submitted ? `${stats.applications.submitted} submitted` : undefined
                }
              />
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {profile === null ? (
              <SetupCard
                title="Set up your profile"
                description="Tell us your target roles, locations, and preferences so we can find the right jobs for you."
                href="/applaut/onboarding"
                cta="Set up profile"
              />
            ) : (
              <InfoCard title={profile.display_name}>
                <InfoRow label="Roles" value={profile.target_roles.join(', ')} />
                <InfoRow label="Countries" value={profile.target_countries.join(', ')} />
                <InfoRow label="Remote" value={profile.remote_preference} />
                <InfoRow label="Job engine" value={JOB_ENGINE_LABELS[profile.job_engine]} />
                {profile.job_engine === 'basic' && <InfoRow label="Discovery" value={`every ${profile.discovery_frequency_hours}h`} />}
                <Link to="/applaut/onboarding" style={{ fontSize: '0.8rem', color: 'var(--accent)', textDecoration: 'none', marginTop: '0.25rem' }}>Edit profile →</Link>
              </InfoCard>
            )}

            {resume === null ? (
              <SetupCard
                title="Upload your resume"
                description="Upload your master resume and AI will extract your skills, experience, and education."
                href="/applaut/resume"
                cta="Upload resume"
              />
            ) : (
              <InfoCard title="Master Resume">
                <InfoRow label="File" value={resume.file_name} />
                <InfoRow label="Version" value={String(resume.version)} />
                {resume.content_extracted && (
                  <InfoRow
                    label="Skills"
                    value={resume.content_extracted.skills.slice(0, 5).join(', ') + (resume.content_extracted.skills.length > 5 ? ` +${resume.content_extracted.skills.length - 5} more` : '')}
                  />
                )}
                <Link to="/applaut/resume" style={{ fontSize: '0.8rem', color: 'var(--accent)', textDecoration: 'none', marginTop: '0.25rem' }}>View / replace →</Link>
              </InfoCard>
            )}

            {profile && resume && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '0.75rem' }}>
                <SetupCard title="Find & score jobs" description="Run discovery, see match scores, and act on near misses — all in one place." href="/applaut/opportunities" cta="View opportunities" />
                <SetupCard title="Documents" description="Generate tailored resumes and cover letters from your good matches." href="/applaut/opportunities?match=good" cta="View good matches" />
                <SetupCard title="Applications" description="Track your pipeline from review to offer." href="/applaut/applications" cta="View applications" />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
