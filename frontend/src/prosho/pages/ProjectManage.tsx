import { type FormEvent, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import {
  apiErrorMessage, getProject, PROJECT_TYPE_LABEL, updateProject,
  type DemoKind, type Project, type ProjectUpdate, type Visibility,
} from '../api/projects'
import ProshoShell from '../components/ProshoShell'
import { Banner, Button, Card, Field, hintStyle, publicPagePath, publicPageUrl, VisibilityPill } from '../components/ui'

const VISIBILITY_OPTIONS: { value: Visibility; label: string; help: string }[] = [
  { value: 'private', label: 'Private', help: 'Only you can see the page.' },
  { value: 'unlisted', label: 'Unlisted', help: 'Anyone with the link can see it — good for sharing with your supervisor or examiners. Not listed anywhere.' },
  { value: 'public', label: 'Public', help: 'Listed in the ProSho gallery. Needs your supervisor’s agreement first.' },
]

const DEMO_KINDS: { value: DemoKind; label: string }[] = [
  { value: 'streamlit', label: 'Streamlit app' },
  { value: 'url', label: 'Website / other link' },
  { value: 'video', label: 'Video' },
]

type Status = { kind: 'error' | 'success'; text: string } | null

export default function ProshoProjectManage() {
  const { id = '' } = useParams()
  const [project, setProject] = useState<Project | null>(null)
  const [loadError, setLoadError] = useState('')
  useDocumentTitle(`${project?.title ?? 'Project'} | ProSho`)

  useEffect(() => {
    getProject(id).then(setProject).catch(err => setLoadError(apiErrorMessage(err, 'Project not found.')))
  }, [id])

  if (loadError) {
    return (
      <ProshoShell>
        <Banner kind="error">{loadError}</Banner>
        <Link to="/prosho/dashboard" style={{ color: 'var(--accent)' }}>Back to your projects</Link>
      </ProshoShell>
    )
  }
  if (!project) return <ProshoShell><p style={{ color: 'var(--text-2)' }}>Loading…</p></ProshoShell>

  return (
    <ProshoShell>
      <p style={{ marginBottom: '1rem' }}><Link to="/prosho/dashboard" style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>← Your projects</Link></p>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.5rem' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 700, overflowWrap: 'anywhere' }}>{project.title}</h1>
            <VisibilityPill visibility={project.visibility} />
          </div>
          <p style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>{PROJECT_TYPE_LABEL[project.project_type]}</p>
        </div>
        <Link to={publicPagePath(project.slug)} style={{ padding: '0.55rem 1rem', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-xs)', color: 'var(--text-1)', fontSize: '0.85rem', textDecoration: 'none' }}>
          View page ↗
        </Link>
      </div>

      {project.manifest_managed && (
        <Banner kind="info">Title, summary, problem and demo come from <code>prosho.yaml</code> in your repo — edit them there and push.</Banner>
      )}

      <VisibilityCard project={project} onSaved={setProject} />
      <DetailsCard project={project} onSaved={setProject} />
      <DemoCard project={project} onSaved={setProject} />
      <Card title="GitHub repository">
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem' }}>
          {project.repo_full_name ?? 'Connecting a repo is coming next — it will read your prosho.yaml on every push.'}
        </p>
      </Card>
    </ProshoShell>
  )
}

function useSave(project: Project, onSaved: (p: Project) => void) {
  const [status, setStatus] = useState<Status>(null)
  const [saving, setSaving] = useState(false)
  const save = async (body: ProjectUpdate, successText = 'Saved.') => {
    setSaving(true)
    setStatus(null)
    try {
      onSaved(await updateProject(project.id, body))
      setStatus({ kind: 'success', text: successText })
    } catch (err) {
      setStatus({ kind: 'error', text: apiErrorMessage(err) })
    } finally {
      setSaving(false)
    }
  }
  return { status, saving, save }
}

function StatusBanner({ status }: { status: Status }) {
  return status ? <Banner kind={status.kind}>{status.text}</Banner> : null
}

function VisibilityCard({ project, onSaved }: { project: Project; onSaved: (p: Project) => void }) {
  const [visibility, setVisibility] = useState<Visibility>(project.visibility)
  const [supervisorOk, setSupervisorOk] = useState(project.supervisor_ok_at !== null)
  const { status, saving, save } = useSave(project, onSaved)

  const dirty = visibility !== project.visibility || supervisorOk !== (project.supervisor_ok_at !== null)
  const blocked = visibility === 'public' && !supervisorOk

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save({ visibility, supervisor_confirmed: supervisorOk })
  }

  return (
    <Card title="Who can see the page" aside={<span style={hintStyle}>{publicPageUrl(project.slug)}</span>}>
      <StatusBanner status={status} />
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
        {VISIBILITY_OPTIONS.map(o => (
          <label key={o.value} style={{ display: 'flex', gap: '0.7rem', alignItems: 'flex-start', padding: '0.8rem 0.9rem', border: `1px solid ${visibility === o.value ? 'var(--accent-border)' : 'var(--border-strong)'}`, borderRadius: 'var(--radius-xs)', background: visibility === o.value ? 'var(--accent-glow)' : 'transparent', cursor: 'pointer' }}>
            <input type="radio" name="visibility" checked={visibility === o.value} onChange={() => setVisibility(o.value)} style={{ marginTop: '0.2rem' }} />
            <span>
              <span style={{ display: 'block', fontWeight: 600, fontSize: '0.9rem' }}>{o.label}</span>
              <span style={{ display: 'block', color: 'var(--text-2)', fontSize: '0.8rem', marginTop: '0.15rem', lineHeight: 1.5 }}>{o.help}</span>
            </span>
          </label>
        ))}
        <label style={{ display: 'flex', gap: '0.6rem', alignItems: 'flex-start', marginTop: '0.4rem', cursor: 'pointer' }}>
          <input type="checkbox" checked={supervisorOk} onChange={e => setSupervisorOk(e.target.checked)} style={{ marginTop: '0.2rem' }} />
          <span style={{ fontSize: '0.875rem', lineHeight: 1.5 }}>
            My supervisor has agreed this project can be public.
            {project.supervisor_ok_at && <span style={{ ...hintStyle, display: 'block' }}>Confirmed {new Date(project.supervisor_ok_at).toLocaleDateString()}</span>}
          </span>
        </label>
        {blocked && <p style={{ ...hintStyle, color: 'var(--warn)' }}>Tick the supervisor box to make the page public.</p>}
        <div style={{ marginTop: '0.4rem' }}><Button type="submit" disabled={!dirty || blocked || saving}>{saving ? 'Saving…' : 'Save visibility'}</Button></div>
      </form>
    </Card>
  )
}

function DetailsCard({ project, onSaved }: { project: Project; onSaved: (p: Project) => void }) {
  const [title, setTitle] = useState(project.title)
  const [slug, setSlug] = useState(project.slug)
  const [university, setUniversity] = useState(project.university ?? '')
  const [programme, setProgramme] = useState(project.programme ?? '')
  const { status, saving, save } = useSave(project, onSaved)

  // Re-sync when the project changes underneath (e.g. after another card saves).
  useEffect(() => {
    setTitle(project.title); setSlug(project.slug)
    setUniversity(project.university ?? ''); setProgramme(project.programme ?? '')
  }, [project])

  const body: ProjectUpdate = {}
  if (!project.manifest_managed && title.trim() !== project.title) body.title = title.trim()
  if (slug !== project.slug) body.slug = slug
  if (university.trim() !== (project.university ?? '')) body.university = university.trim() || null
  if (programme.trim() !== (project.programme ?? '')) body.programme = programme.trim() || null
  const dirty = Object.keys(body).length > 0

  return (
    <Card title="Details">
      <StatusBanner status={status} />
      <form onSubmit={e => { e.preventDefault(); save(body) }} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
        <Field label="Title" hint={project.manifest_managed ? 'Set in prosho.yaml.' : undefined}>
          <input value={title} onChange={e => setTitle(e.target.value)} maxLength={200} disabled={project.manifest_managed} />
        </Field>
        <Field label="Page address" hint={project.published_at ? 'Fixed — this page has been shared.' : `lvamo.com/prosho/${slug || '…'}`}>
          <input value={slug} onChange={e => setSlug(e.target.value.toLowerCase())} maxLength={60} disabled={!!project.published_at} autoCapitalize="off" spellCheck={false} />
        </Field>
        <Field label="University">
          <input value={university} onChange={e => setUniversity(e.target.value)} maxLength={200} placeholder="UE Potsdam" />
        </Field>
        <Field label="Programme">
          <input value={programme} onChange={e => setProgramme(e.target.value)} maxLength={200} placeholder="MSc Data Science" />
        </Field>
        <div><Button type="submit" disabled={!dirty || saving}>{saving ? 'Saving…' : 'Save details'}</Button></div>
      </form>
    </Card>
  )
}

function DemoCard({ project, onSaved }: { project: Project; onSaved: (p: Project) => void }) {
  const [kind, setKind] = useState<DemoKind | ''>(project.demo_kind ?? '')
  const [url, setUrl] = useState(project.demo_url ?? '')
  const { status, saving, save } = useSave(project, onSaved)
  useEffect(() => { setKind(project.demo_kind ?? ''); setUrl(project.demo_url ?? '') }, [project])

  const locked = project.manifest_managed
  const dirty = kind !== (project.demo_kind ?? '') || url.trim() !== (project.demo_url ?? '')
  const valid = (kind === '' && url.trim() === '') || (kind !== '' && /^https?:\/\//i.test(url.trim()))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save(kind === '' ? { demo_kind: null, demo_url: null } : { demo_kind: kind, demo_url: url.trim() })
  }

  return (
    <Card title="Demo">
      <StatusBanner status={status} />
      <form onSubmit={submit} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
        <Field label="Kind" hint={locked ? 'Set in prosho.yaml.' : undefined}>
          <select value={kind} onChange={e => setKind(e.target.value as DemoKind | '')} disabled={locked}>
            <option value="">No demo</option>
            {DEMO_KINDS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>
        </Field>
        <Field label="Link" hint="Must start with https://">
          <input value={url} onChange={e => setUrl(e.target.value)} maxLength={500} placeholder="https://your-app.streamlit.app" disabled={locked || kind === ''} inputMode="url" />
        </Field>
        {!locked && <div><Button type="submit" disabled={!dirty || !valid || saving}>{saving ? 'Saving…' : 'Save demo'}</Button></div>}
      </form>
    </Card>
  )
}
