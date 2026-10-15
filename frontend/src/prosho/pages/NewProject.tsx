import { type FormEvent, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { apiErrorMessage, createProject, PROJECT_TYPE_LABEL, type ProjectType } from '../api/projects'
import ProshoShell from '../components/ProshoShell'
import { Banner, Button, Card, Field, labelStyle } from '../components/ui'

const slugify = (s: string) =>
  s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60).replace(/-+$/, '')

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export default function ProshoNewProject() {
  useDocumentTitle('New project | ProSho')
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [title, setTitle] = useState('')
  const [slug, setSlug] = useState('')
  const [slugEdited, setSlugEdited] = useState(false)
  const [type, setType] = useState<ProjectType>('data_science')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const effectiveSlug = slugEdited ? slug : slugify(title)
  const valid = title.trim() !== '' && effectiveSlug.length >= 3

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      const p = await createProject({ title: title.trim(), slug: effectiveSlug, project_type: type })
      navigate(`/prosho/projects/${p.id}`)
    } catch (err) {
      setError(apiErrorMessage(err))
      setSaving(false)
    }
  }

  // This is also the GitHub App's Setup URL: after installing, GitHub sends
  // the student here with installation_id and the `state` we passed (the
  // project id). Nothing here is trusted — the project page asks the backend,
  // which checks the installation with GitHub itself.
  if (params.get('installation_id')) {
    const state = params.get('state') ?? ''
    return <Navigate to={UUID_RE.test(state) ? `/prosho/projects/${state}` : '/prosho/dashboard'} replace />
  }

  return (
    <ProshoShell>
      <p style={{ marginBottom: '1rem' }}><Link to="/prosho/dashboard" style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>← Your projects</Link></p>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '1.5rem' }}>New project</h1>
      <div style={{ maxWidth: '560px' }}>
        <Card>
          {error && <Banner kind="error">{error}</Banner>}
          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
            <Field label="Project title" hint="You can change this later in prosho.yaml once your repo is connected.">
              <input value={title} onChange={e => setTitle(e.target.value)} maxLength={200} placeholder="HeatRisk EU" required />
            </Field>
            <Field label="Page address" hint={<>Your page will live at <strong>lvamo.com/prosho/{effectiveSlug || '…'}</strong>. It can't change once you've shared the page.</>}>
              <input
                value={effectiveSlug}
                onChange={e => { setSlugEdited(true); setSlug(e.target.value.toLowerCase()) }}
                maxLength={60}
                placeholder="heatrisk-eu"
                autoCapitalize="off"
                spellCheck={false}
              />
            </Field>
            <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <legend style={{ ...labelStyle, marginBottom: '0.5rem' }}>Project type</legend>
              {(Object.keys(PROJECT_TYPE_LABEL) as ProjectType[]).map(t => (
                <label key={t} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.7rem 0.85rem', border: `1px solid ${type === t ? 'var(--accent-border)' : 'var(--border-strong)'}`, borderRadius: 'var(--radius-xs)', background: type === t ? 'var(--accent-glow)' : 'transparent', cursor: 'pointer' }}>
                  <input type="radio" name="type" checked={type === t} onChange={() => setType(t)} />
                  <span style={{ fontSize: '0.9rem' }}>{PROJECT_TYPE_LABEL[t]}</span>
                </label>
              ))}
            </fieldset>
            <div><Button type="submit" disabled={!valid || saving}>{saving ? 'Creating…' : 'Create project'}</Button></div>
          </form>
        </Card>
      </div>
    </ProshoShell>
  )
}
