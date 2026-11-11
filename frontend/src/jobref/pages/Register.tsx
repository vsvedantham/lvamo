import { type FormEvent, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import BrandedPage from '../../components/BrandedPage'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { useJobrefAuth } from '../context/AuthContext'
import EmailCodeStep from '../../components/EmailCodeStep'
import { useEmailCodesEnabled } from '../../hooks/useEmailCodesEnabled'
import { PlatformApiError, sendEmailCode } from '../../api/platform'
import { linkedInAuthorizeUrl } from '../api/auth'
import type { EmployeeRegisterPayload, ReferFrequency, ReferralViewCapacity } from '../api/auth'

const field: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '0.375rem' }
const labelStyle: React.CSSProperties = { fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-2)' }

const panel: React.CSSProperties = {
  background: 'var(--bg-surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '1.75rem',
}

const backLink: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
  color: 'var(--text-2)', fontSize: '0.8rem', fontWeight: 500, marginBottom: '1.25rem',
}

// Which path the user picked — carried in the URL (not just component state)
// so the browser back button and a page refresh both behave correctly.
type Choice = 'employee' | 'job_seeker' | null

export default function JobrefRegister() {
  useDocumentTitle('Create account | Jobref')
  const { register, user, loading: authLoading } = useJobrefAuth()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const linkedinError = params.get('linkedin') === 'error'
  const choice = (params.get('as') as Choice) ?? null

  // Employee form state
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [domain, setDomain] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [workingSince, setWorkingSince] = useState('')
  const [dailyReferralViewCap, setDailyReferralViewCap] = useState<ReferralViewCapacity>('up_to_5')
  const [referFrequency, setReferFrequency] = useState<ReferFrequency>('weekly')
  const [referralCapacity, setReferralCapacity] = useState<ReferralViewCapacity>('up_to_5')
  const [companyCareersUrl, setCompanyCareersUrl] = useState('')

  // Disable "Create account" until every required field is actually
  // filled in — was previously always clickable, relying only on the
  // browser's native `required` validation to silently block an empty
  // submit, giving no visual signal the form wasn't ready.
  const employeeFormValid =
    firstName.trim() !== '' &&
    lastName.trim() !== '' &&
    email.trim() !== '' &&
    phone.trim() !== '' &&
    password.length >= 8 &&
    domain.trim() !== '' &&
    companyName.trim() !== '' &&
    workingSince !== '' &&
    companyCareersUrl.trim() !== ''

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // Employees confirm their email with an emailed code while the platform
  // setting `otp_verification_enabled` lists jobref. Job seekers don't:
  // LinkedIn already verified their email.
  const codesOn = useEmailCodesEnabled('jobref')
  const [codeStep, setCodeStep] = useState<{ resendAfter: number } | null>(null)

  const errorText = (err: any) => {
    if (err instanceof PlatformApiError) return err.message
    const detail = err?.response?.data?.detail
    return Array.isArray(detail)
      ? detail.map((d: any) => d.msg).join(' ')
      : detail ?? 'Registration failed. Please try again.'
  }

  const createEmployee = async (emailCode?: string) => {
    const payload: EmployeeRegisterPayload = {
      user_type: 'employee',
      first_name: firstName,
      last_name: lastName,
      email: email.trim(),
      phone,
      password,
      domain,
      employee: {
        company_name: companyName,
        working_since: workingSince,
        daily_referral_view_cap: dailyReferralViewCap,
        refer_frequency: referFrequency,
        referral_capacity: referralCapacity,
        company_careers_url: companyCareersUrl,
      },
      ...(emailCode ? { email_code: emailCode } : {}),
    }
    await register(payload)
    navigate('/jobref/dashboard')
  }

  const handleEmployeeSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (codesOn === null) return
    setError('')
    setLoading(true)
    try {
      if (codesOn) {
        const sent = await sendEmailCode('jobref', email.trim(), 'register')
        setCodeStep({ resendAfter: sent.resend_after_seconds })
      } else {
        await createEmployee()
      }
    } catch (err: any) {
      setError(errorText(err))
    } finally {
      setLoading(false)
    }
  }

  const goBack = () => setParams({}, { replace: false })

  // An existing session should persist — landing here already logged in
  // shouldn't offer to create a new account, it should just continue on.
  if (authLoading) return null
  if (user) return <Navigate to="/jobref/dashboard" replace />

  return (
    <BrandedPage>
      <div style={{ width: '100%', maxWidth: choice ? '460px' : '760px' }}>
        {linkedinError && (
          <div style={{ padding: '0.7rem 0.875rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
            <p style={{ color: 'var(--danger)', fontSize: '0.825rem', margin: 0, textAlign: 'center' }}>
              LinkedIn sign-in was cancelled or failed. Please try again.
            </p>
          </div>
        )}

        {choice === null && (
          <>
            <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
              <h1 style={{ fontSize: '1.6rem', fontWeight: 700, marginBottom: '0.35rem' }}>I am a</h1>
              <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>Choose how you'd like to join Jobref</p>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.25rem' }}>
              <ChoiceCard
                title="Full-time Employee"
                description="Register directly and start referring candidates at your company"
                onClick={() => setParams({ as: 'employee' })}
              />
              <ChoiceCard
                title="Job Seeker"
                description="Sign in with LinkedIn and get discovered by employees willing to refer you"
                onClick={() => setParams({ as: 'job_seeker' })}
              />
            </div>
          </>
        )}

        {choice === 'employee' && (
          <div style={panel}>
            <a href="#" onClick={e => { e.preventDefault(); goBack() }} style={backLink}>
              <BackArrow /> Back
            </a>

            <div style={{ marginBottom: '1.25rem' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.2rem' }}>Full-time Employee</h2>
              <p style={{ color: 'var(--text-2)', fontSize: '0.825rem' }}>Register directly — no LinkedIn required</p>
            </div>

            {codeStep ? (
              <EmailCodeStep
                vertical="jobref"
                purpose="register"
                email={email.trim()}
                resendAfterSeconds={codeStep.resendAfter}
                submitLabel="Create account"
                busyLabel="Creating account…"
                onSubmit={code => createEmployee(code)}
                errorMessage={errorText}
                onBack={() => setCodeStep(null)}
                backLabel="Edit details"
              />
            ) : (<>
            {error && (
              <div style={{ padding: '0.7rem 0.875rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
                <p style={{ color: 'var(--danger)', fontSize: '0.825rem', margin: 0 }}>{error}</p>
              </div>
            )}

            <form onSubmit={handleEmployeeSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <div style={field}>
                  <label style={labelStyle}>First name</label>
                  <input type="text" value={firstName} onChange={e => setFirstName(e.target.value)} required placeholder="Ada" />
                </div>
                <div style={field}>
                  <label style={labelStyle}>Last name</label>
                  <input type="text" value={lastName} onChange={e => setLastName(e.target.value)} required placeholder="Lovelace" />
                </div>
              </div>

              <div style={field}>
                <label style={labelStyle}>Email</label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" autoComplete="email" />
              </div>

              <div style={field}>
                <label style={labelStyle}>Phone <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(German number)</span></label>
                <input type="tel" value={phone} onChange={e => setPhone(e.target.value)} required placeholder="+49 170 1234567" />
              </div>

              <div style={field}>
                <label style={labelStyle}>Password <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(min. 8 characters)</span></label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} placeholder="••••••••" autoComplete="new-password" />
              </div>

              <div style={field}>
                <label style={labelStyle}>Professional field / domain</label>
                <input type="text" value={domain} onChange={e => setDomain(e.target.value)} required placeholder="e.g. Data Engineering" />
              </div>

              <div style={field}>
                <label style={labelStyle}>Company name</label>
                <input type="text" value={companyName} onChange={e => setCompanyName(e.target.value)} required placeholder="Acme GmbH" />
              </div>
              <div style={field}>
                <label style={labelStyle}>Working since</label>
                <input type="date" value={workingSince} onChange={e => setWorkingSince(e.target.value)} required />
              </div>
              <div style={field}>
                <label style={labelStyle}>Company careers page URL</label>
                <input type="url" value={companyCareersUrl} onChange={e => setCompanyCareersUrl(e.target.value)} required placeholder="https://company.com/careers" />
              </div>

              <div style={field}>
                <label style={labelStyle}>How many referral requests can you review per day?</label>
                <select value={dailyReferralViewCap} onChange={e => setDailyReferralViewCap(e.target.value as ReferralViewCapacity)}>
                  <option value="up_to_5">≤ 5</option>
                  <option value="5_to_10">5 - 10</option>
                  <option value="10_to_20">10 - 20</option>
                  <option value="no_cap">No Cap</option>
                </select>
              </div>

              <div style={field}>
                <label style={labelStyle}>How many referrals can you do in a…</label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <SegmentButton active={referFrequency === 'weekly'} onClick={() => setReferFrequency('weekly')}>Week</SegmentButton>
                  <SegmentButton active={referFrequency === 'monthly'} onClick={() => setReferFrequency('monthly')}>Month</SegmentButton>
                </div>
              </div>

              <div style={field}>
                <select value={referralCapacity} onChange={e => setReferralCapacity(e.target.value as ReferralViewCapacity)}>
                  <option value="up_to_5">≤ 5</option>
                  <option value="5_to_10">5 - 10</option>
                  <option value="10_to_20">10 - 20</option>
                  <option value="no_cap">No Cap</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={loading || !employeeFormValid || codesOn === null}
                style={{
                  marginTop: '0.25rem', padding: '0.625rem', background: 'var(--accent)', color: '#fff',
                  border: 'none', borderRadius: 'var(--radius-xs)', fontWeight: 600, fontSize: '0.9rem',
                  opacity: loading || !employeeFormValid ? 0.5 : 1,
                  cursor: loading || !employeeFormValid ? 'not-allowed' : 'pointer',
                }}
              >
                {loading ? (codesOn ? 'Sending code…' : 'Creating account…') : (codesOn ? 'Continue' : 'Create account')}
              </button>
            </form>
            </>)}
          </div>
        )}

        {choice === 'job_seeker' && (
          <div style={panel}>
            <a href="#" onClick={e => { e.preventDefault(); goBack() }} style={backLink}>
              <BackArrow /> Back
            </a>

            <div style={{ marginBottom: '1.25rem' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.2rem' }}>Job Seeker</h2>
              <p style={{ color: 'var(--text-2)', fontSize: '0.825rem' }}>Get discovered by employees willing to refer you</p>
            </div>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-2)', lineHeight: 1.5, marginBottom: '1.5rem' }}>
              We use LinkedIn to sign you in. We only take your <strong>name and
              email address</strong> from your LinkedIn profile — nothing else.
              This is used to prevent duplicate accounts on Jobref.
            </p>

            <a
              href={linkedInAuthorizeUrl()}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.6rem',
                padding: '0.7rem', background: '#0A66C2', color: '#fff', borderRadius: 'var(--radius-xs)',
                fontWeight: 600, fontSize: '0.9rem', textDecoration: 'none',
              }}
            >
              <LinkedInMark />
              Continue with LinkedIn
            </a>
          </div>
        )}

        <p style={{ marginTop: '1.5rem', textAlign: 'center', color: 'var(--text-2)', fontSize: '0.85rem' }}>
          Already have an account?{' '}
          <Link to="/jobref/login" style={{ color: 'var(--accent)', fontWeight: 500 }}>Sign in</Link>
        </p>
      </div>
    </BrandedPage>
  )
}

function SegmentButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: 1,
        padding: '0.55rem',
        borderRadius: 'var(--radius-xs)',
        border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border-strong)'}`,
        background: active ? 'var(--accent-glow)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--text-2)',
        fontWeight: 600,
        fontSize: '0.85rem',
        cursor: 'pointer',
        transition: 'border-color 0.15s, background 0.15s, color 0.15s',
      }}
    >
      {children}
    </button>
  )
}

function ChoiceCard({ title, description, onClick }: { title: string; description: string; onClick: () => void }) {
  const [hover, setHover] = useState(false)
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onClick() }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        flex: '1 1 300px',
        cursor: 'pointer',
        background: 'var(--bg-surface)',
        border: `1px solid ${hover ? 'var(--accent-border)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: '1.75rem',
        transition: 'border-color 0.15s, background 0.15s',
        ...(hover ? { background: 'var(--accent-glow)' } : {}),
      }}
    >
      <h2 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.4rem', color: hover ? 'var(--accent)' : 'var(--text-1)' }}>{title}</h2>
      <p style={{ color: 'var(--text-2)', fontSize: '0.85rem', lineHeight: 1.5 }}>{description}</p>
    </div>
  )
}

function BackArrow() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  )
}

function LinkedInMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M20.45 20.45h-3.55v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.36V9h3.41v1.56h.05c.47-.9 1.63-1.85 3.36-1.85 3.6 0 4.27 2.37 4.27 5.45v6.29zM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12zM7.12 20.45H3.56V9h3.56v11.45z" />
    </svg>
  )
}
