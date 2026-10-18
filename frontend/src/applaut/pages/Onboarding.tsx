import { type KeyboardEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createProfile } from '../api/profile'

const COUNTRIES = [
  { code: 'DE', name: 'Germany' },
  { code: 'FR', name: 'France' },
  { code: 'NL', name: 'Netherlands' },
  { code: 'AT', name: 'Austria' },
  { code: 'BE', name: 'Belgium' },
  { code: 'CH', name: 'Switzerland' },
  { code: 'ES', name: 'Spain' },
  { code: 'IT', name: 'Italy' },
  { code: 'PT', name: 'Portugal' },
  { code: 'PL', name: 'Poland' },
  { code: 'SE', name: 'Sweden' },
  { code: 'NO', name: 'Norway' },
  { code: 'DK', name: 'Denmark' },
  { code: 'FI', name: 'Finland' },
  { code: 'IE', name: 'Ireland' },
  { code: 'CZ', name: 'Czech Republic' },
  { code: 'RO', name: 'Romania' },
  { code: 'HU', name: 'Hungary' },
  { code: 'US', name: 'United States' },
]

const EMPLOYMENT_TYPES = [
  { value: 'full_time', label: 'Full-time' },
  { value: 'part_time', label: 'Part-time' },
  { value: 'contract', label: 'Contract' },
  { value: 'freelance', label: 'Freelance' },
  { value: 'internship', label: 'Internship' },
]

const REMOTE_OPTIONS = [
  { value: 'remote_only', label: 'Remote only' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'onsite', label: 'On-site' },
  { value: 'any', label: 'Any' },
]

const inputStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  padding: '0.5rem 0.75rem',
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-xs)',
  fontSize: '0.875rem',
  color: 'var(--text-1)',
  boxSizing: 'border-box',
  fontFamily: 'inherit',
  outline: 'none',
}

const labelStyle: React.CSSProperties = {
  fontSize: '0.8rem',
  fontWeight: 500,
  color: 'var(--text-2)',
  display: 'block',
  marginBottom: '0.375rem',
}

function TagInput({ tags, onChange, placeholder }: { tags: string[]; onChange: (t: string[]) => void; placeholder?: string }) {
  const [val, setVal] = useState('')
  const add = () => {
    const v = val.trim()
    if (v && !tags.includes(v)) onChange([...tags, v])
    setVal('')
  }
  return (
    <div>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <input
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          style={{ ...inputStyle, flex: 1 }}
          placeholder={placeholder ?? 'Type and press Enter'}
        />
        <button type="button" onClick={add} style={{ padding: '0.4rem 0.875rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.825rem', whiteSpace: 'nowrap' }}>
          Add
        </button>
      </div>
      {tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem', marginTop: '0.625rem' }}>
          {tags.map(t => (
            <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.2rem 0.625rem', background: 'var(--accent-glow)', border: '1px solid var(--accent-border)', borderRadius: '999px', fontSize: '0.775rem', color: 'var(--accent)' }}>
              {t}
              <button type="button" onClick={() => onChange(tags.filter(x => x !== t))} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--accent)', lineHeight: 1, fontSize: '0.9rem', opacity: 0.7 }}>×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  )
}

const FIELD_LABELS: Record<string, string> = {
  display_name: 'Profile name',
  total_experience_years: 'Years of experience',
  target_roles: 'Target roles',
  target_countries: 'Countries',
  remote_preference: 'Work mode',
  employment_types: 'Employment types',
  skills: 'Skills',
  languages: 'Languages',
  discovery_frequency_hours: 'Discovery frequency',
  good_threshold: 'Good-match threshold',
}

/** The API's error as a sentence. FastAPI's validation errors are a list of
 * objects, which React can't render as text (that blanked the page). */
function describeError(err: any): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: any) => {
      const field = Array.isArray(d?.loc) ? String(d.loc[d.loc.length - 1]) : ''
      return `${FIELD_LABELS[field] ?? field}: ${String(d?.msg ?? 'invalid value').replace(/^Value error, /, '')}`
    }).join(' · ')
  }
  return 'Failed to create profile. Please try again.'
}

export default function Onboarding() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Step 1
  const [displayName, setDisplayName] = useState('')
  const [experienceYears, setExperienceYears] = useState(0)
  const [targetRoles, setTargetRoles] = useState<string[]>([])

  // Step 2
  const [countries, setCountries] = useState<string[]>([])
  const [remotePreference, setRemotePreference] = useState('any')
  const [employmentTypes, setEmploymentTypes] = useState<string[]>(['full_time'])

  // Step 3
  const [skills, setSkills] = useState<string[]>([])
  const [languages, setLanguages] = useState<string[]>([])
  const [discoveryFrequency, setDiscoveryFrequency] = useState(24)
  const [goodThreshold, setGoodThreshold] = useState(85)

  const toggleCountry = (code: string) =>
    setCountries(prev => prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code])

  const toggleEmployment = (val: string) =>
    setEmploymentTypes(prev => prev.includes(val) ? prev.filter(t => t !== val) : [...prev, val])

  const next = () => {
    if (step === 1 && (!displayName.trim() || targetRoles.length === 0)) {
      setError('Please enter a profile name and at least one target role.')
      return
    }
    if (step === 1 && !(experienceYears >= 0 && experienceYears <= 50)) {
      setError('Years of experience must be between 0 and 50.')
      return
    }
    if (step === 2 && countries.length === 0) {
      setError('Please select at least one country.')
      return
    }
    if (step === 2 && employmentTypes.length === 0) {
      setError('Please select at least one employment type.')
      return
    }
    setError('')
    setStep(s => s + 1)
  }

  const submit = async () => {
    if (skills.length === 0) {
      setError('Please add at least one skill.')
      return
    }
    setError('')
    setSubmitting(true)
    try {
      await createProfile({
        display_name: displayName.trim(),
        // The API takes whole years; 4.5 would be rejected.
        total_experience_years: Math.round(experienceYears),
        target_roles: targetRoles,
        target_countries: countries,
        remote_preference: remotePreference,
        employment_types: employmentTypes,
        skills,
        languages,
        discovery_frequency_hours: discoveryFrequency,
        good_threshold: goodThreshold,
      })
      navigate('/applaut/resume')
    } catch (err: any) {
      setError(describeError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const progress = ((step - 1) / 3) * 100

  return (
    <div style={{ maxWidth: '560px' }}>
      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.25rem', color: 'var(--text-1)' }}>Set up your profile</h1>
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', margin: '0 0 1.25rem' }}>Step {step} of 3 — {['', 'Basics', 'Location & preferences', 'Skills & settings'][step]}</p>
        <div style={{ height: '3px', background: 'var(--bg-elevated)', borderRadius: '999px', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${progress}%`, background: 'linear-gradient(90deg, var(--accent-dim), var(--accent))', borderRadius: '999px', transition: 'width 0.35s ease' }} />
        </div>
      </div>

      <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '1.75rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        {error && (
          <div style={{ padding: '0.7rem 0.875rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)' }}>
            <p style={{ color: 'var(--danger)', fontSize: '0.825rem', margin: 0 }}>{error}</p>
          </div>
        )}

        {step === 1 && (
          <>
            <FieldGroup label="Profile name">
              <input value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="e.g. Senior Data Engineer" style={inputStyle} />
            </FieldGroup>
            <FieldGroup label="Years of experience">
              <input type="number" min={0} max={50} step={1} value={experienceYears} onChange={e => setExperienceYears(Number(e.target.value) || 0)} style={{ ...inputStyle, width: '120px' }} />
            </FieldGroup>
            <FieldGroup label="Target roles — add each role and press Enter">
              <TagInput tags={targetRoles} onChange={setTargetRoles} placeholder="e.g. Data Engineer" />
            </FieldGroup>
          </>
        )}

        {step === 2 && (
          <>
            <FieldGroup label="Target countries">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '0.5rem' }}>
                {COUNTRIES.map(c => (
                  <label
                    key={c.code}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.5rem 0.625rem',
                      background: countries.includes(c.code) ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                      border: `1px solid ${countries.includes(c.code) ? 'var(--accent-border)' : 'var(--border)'}`,
                      borderRadius: 'var(--radius-xs)',
                      cursor: 'pointer',
                      fontSize: '0.825rem',
                      color: countries.includes(c.code) ? 'var(--accent)' : 'var(--text-2)',
                      transition: 'all 0.15s',
                    }}
                  >
                    <input type="checkbox" checked={countries.includes(c.code)} onChange={() => toggleCountry(c.code)} style={{ display: 'none' }} />
                    {c.name}
                  </label>
                ))}
              </div>
            </FieldGroup>

            <FieldGroup label="Remote preference">
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {REMOTE_OPTIONS.map(o => (
                  <label
                    key={o.value}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                      padding: '0.4rem 0.875rem',
                      background: remotePreference === o.value ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                      border: `1px solid ${remotePreference === o.value ? 'var(--accent-border)' : 'var(--border)'}`,
                      borderRadius: '999px',
                      cursor: 'pointer',
                      fontSize: '0.825rem',
                      color: remotePreference === o.value ? 'var(--accent)' : 'var(--text-2)',
                      transition: 'all 0.15s',
                    }}
                  >
                    <input type="radio" name="remote" value={o.value} checked={remotePreference === o.value} onChange={() => setRemotePreference(o.value)} style={{ display: 'none' }} />
                    {o.label}
                  </label>
                ))}
              </div>
            </FieldGroup>

            <FieldGroup label="Employment types">
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {EMPLOYMENT_TYPES.map(t => (
                  <label
                    key={t.value}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                      padding: '0.4rem 0.875rem',
                      background: employmentTypes.includes(t.value) ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                      border: `1px solid ${employmentTypes.includes(t.value) ? 'var(--accent-border)' : 'var(--border)'}`,
                      borderRadius: '999px',
                      cursor: 'pointer',
                      fontSize: '0.825rem',
                      color: employmentTypes.includes(t.value) ? 'var(--accent)' : 'var(--text-2)',
                      transition: 'all 0.15s',
                    }}
                  >
                    <input type="checkbox" checked={employmentTypes.includes(t.value)} onChange={() => toggleEmployment(t.value)} style={{ display: 'none' }} />
                    {t.label}
                  </label>
                ))}
              </div>
            </FieldGroup>
          </>
        )}

        {step === 3 && (
          <>
            <FieldGroup label="Skills — add each skill and press Enter">
              <TagInput tags={skills} onChange={setSkills} placeholder="e.g. Python, Spark, dbt" />
            </FieldGroup>

            <FieldGroup label="Languages spoken">
              <TagInput tags={languages} onChange={setLanguages} placeholder="e.g. English, German" />
            </FieldGroup>

            {/* The API accepts exactly these (CreateProfileRequest.discovery_frequency_hours). */}
            <FieldGroup label="Discovery frequency (Applaut Basic)">
              <select value={discoveryFrequency} onChange={e => setDiscoveryFrequency(Number(e.target.value))} style={{ ...inputStyle, width: 'auto' }}>
                <option value={6}>Every 6 hours</option>
                <option value={12}>Every 12 hours</option>
                <option value={24}>Every 24 hours</option>
              </select>
            </FieldGroup>

            <FieldGroup label={`Match threshold — Good: ${goodThreshold}+  ·  Near miss: ${goodThreshold - 15}–${goodThreshold - 1}`}>
              <input
                type="range"
                min={70}
                max={100}
                value={goodThreshold}
                onChange={e => setGoodThreshold(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--accent)', cursor: 'pointer' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-3)', marginTop: '0.25rem' }}>
                <span>70 (relaxed)</span><span>85 (recommended)</span><span>100</span>
              </div>
            </FieldGroup>
          </>
        )}

        <div style={{ display: 'flex', gap: '0.625rem', paddingTop: '0.25rem' }}>
          {step > 1 && (
            <button
              onClick={() => { setError(''); setStep(s => s - 1) }}
              style={{ flex: 1, padding: '0.625rem', background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-1)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.9rem' }}
            >
              Back
            </button>
          )}
          {step < 3 ? (
            <button
              onClick={next}
              style={{ flex: 1, padding: '0.625rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 600 }}
            >
              Next
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={submitting}
              style={{ flex: 1, padding: '0.625rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 600, opacity: submitting ? 0.7 : 1 }}
            >
              {submitting ? 'Creating profile…' : 'Create profile'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
