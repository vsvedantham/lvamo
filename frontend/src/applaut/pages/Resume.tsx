import { type ChangeEvent, type DragEvent, type KeyboardEvent, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  type CertificationEntry,
  type EducationEntry,
  type ExperienceEntry,
  type ExtractedContent,
  getMyResume,
  type Resume,
  updateExtractedContent,
  uploadResume,
} from '../api/resume'
import { apiErrorMessage } from '../api/errors'

const inputStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  padding: '0.5rem 0.75rem',
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-xs)',
  fontSize: '0.85rem',
  color: 'var(--text-1)',
  boxSizing: 'border-box',
  outline: 'none',
  fontFamily: 'inherit',
}

const labelStyle: React.CSSProperties = { fontSize: '0.75rem', fontWeight: 500, color: 'var(--text-2)', display: 'block', marginBottom: '0.3rem' }

function TagInput({ tags, onChange }: { tags: string[]; onChange: (t: string[]) => void }) {
  const [val, setVal] = useState('')
  const add = () => {
    const v = val.trim()
    if (v && !tags.includes(v)) onChange([...tags, v])
    setVal('')
  }
  return (
    <div>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <input value={val} onChange={e => setVal(e.target.value)} onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter') { e.preventDefault(); add() } }} style={{ ...inputStyle, flex: 1 }} placeholder="Type and press Enter" />
        <button type="button" onClick={add} style={{ padding: '0.4rem 0.875rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.825rem', whiteSpace: 'nowrap' }}>Add</button>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem', marginTop: '0.625rem' }}>
        {tags.map(t => (
          <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.2rem 0.625rem', background: 'var(--accent-glow)', border: '1px solid var(--accent-border)', borderRadius: '999px', fontSize: '0.775rem', color: 'var(--accent)' }}>
            {t}
            <button type="button" onClick={() => onChange(tags.filter(x => x !== t))} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--accent)', lineHeight: 1, fontSize: '0.9rem', opacity: 0.7 }}>×</button>
          </span>
        ))}
      </div>
    </div>
  )
}

function ExperienceEditor({ entries, onChange }: { entries: ExperienceEntry[]; onChange: (e: ExperienceEntry[]) => void }) {
  const update = (i: number, field: keyof ExperienceEntry, value: string) =>
    onChange(entries.map((e, idx) => idx === i ? { ...e, [field]: value } : e))
  const remove = (i: number) => onChange(entries.filter((_, idx) => idx !== i))
  const add = () => onChange([...entries, { title: '', company: '', location: '', start_date: '', end_date: '', description: '' }])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
      {entries.map((e, i) => (
        <div key={i} style={{ padding: '1rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.625rem' }}>
            <div><label style={labelStyle}>Title</label><input value={e.title} onChange={ev => update(i, 'title', ev.target.value)} style={inputStyle} /></div>
            <div><label style={labelStyle}>Company</label><input value={e.company} onChange={ev => update(i, 'company', ev.target.value)} style={inputStyle} /></div>
            <div><label style={labelStyle}>Location</label><input value={e.location ?? ''} onChange={ev => update(i, 'location', ev.target.value)} style={inputStyle} /></div>
            <div><label style={labelStyle}>Start</label><input value={e.start_date ?? ''} onChange={ev => update(i, 'start_date', ev.target.value)} placeholder="YYYY-MM" style={inputStyle} /></div>
            <div><label style={labelStyle}>End</label><input value={e.end_date ?? ''} onChange={ev => update(i, 'end_date', ev.target.value)} placeholder="YYYY-MM or blank" style={inputStyle} /></div>
          </div>
          <div><label style={labelStyle}>Description</label><textarea value={e.description ?? ''} onChange={ev => update(i, 'description', ev.target.value)} rows={2} style={{ ...inputStyle, resize: 'vertical' }} /></div>
          <button type="button" onClick={() => remove(i)} style={{ alignSelf: 'flex-end', fontSize: '0.775rem', color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>Remove</button>
        </div>
      ))}
      <button type="button" onClick={add} style={{ alignSelf: 'flex-start', fontSize: '0.825rem', color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>+ Add entry</button>
    </div>
  )
}

function EducationEditor({ entries, onChange }: { entries: EducationEntry[]; onChange: (e: EducationEntry[]) => void }) {
  const update = (i: number, field: keyof EducationEntry, value: string) =>
    onChange(entries.map((e, idx) => idx === i ? { ...e, [field]: value } : e))
  const remove = (i: number) => onChange(entries.filter((_, idx) => idx !== i))
  const add = () => onChange([...entries, { degree: '', institution: '', field: '', start_date: '', end_date: '' }])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
      {entries.map((e, i) => (
        <div key={i} style={{ padding: '1rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.625rem' }}>
            <div><label style={labelStyle}>Degree</label><input value={e.degree} onChange={ev => update(i, 'degree', ev.target.value)} style={inputStyle} /></div>
            <div><label style={labelStyle}>Institution</label><input value={e.institution} onChange={ev => update(i, 'institution', ev.target.value)} style={inputStyle} /></div>
            <div><label style={labelStyle}>Field of study</label><input value={e.field ?? ''} onChange={ev => update(i, 'field', ev.target.value)} style={inputStyle} /></div>
            <div><label style={labelStyle}>Start</label><input value={e.start_date ?? ''} onChange={ev => update(i, 'start_date', ev.target.value)} placeholder="YYYY" style={inputStyle} /></div>
            <div><label style={labelStyle}>End</label><input value={e.end_date ?? ''} onChange={ev => update(i, 'end_date', ev.target.value)} placeholder="YYYY or blank" style={inputStyle} /></div>
          </div>
          <button type="button" onClick={() => remove(i)} style={{ alignSelf: 'flex-end', fontSize: '0.775rem', color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>Remove</button>
        </div>
      ))}
      <button type="button" onClick={add} style={{ alignSelf: 'flex-start', fontSize: '0.825rem', color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>+ Add entry</button>
    </div>
  )
}

function CertEditor({ entries, onChange }: { entries: CertificationEntry[]; onChange: (e: CertificationEntry[]) => void }) {
  const update = (i: number, field: keyof CertificationEntry, value: string) =>
    onChange(entries.map((e, idx) => idx === i ? { ...e, [field]: value } : e))
  const remove = (i: number) => onChange(entries.filter((_, idx) => idx !== i))
  const add = () => onChange([...entries, { name: '', issuer: '', date: '' }])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
      {entries.map((e, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: '0.5rem', alignItems: 'end', padding: '0.75rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)' }}>
          <div><label style={labelStyle}>Name</label><input value={e.name} onChange={ev => update(i, 'name', ev.target.value)} style={inputStyle} /></div>
          <div><label style={labelStyle}>Issuer</label><input value={e.issuer ?? ''} onChange={ev => update(i, 'issuer', ev.target.value)} style={inputStyle} /></div>
          <div><label style={labelStyle}>Date</label><input value={e.date ?? ''} onChange={ev => update(i, 'date', ev.target.value)} placeholder="YYYY-MM" style={inputStyle} /></div>
          <button type="button" onClick={() => remove(i)} style={{ fontSize: '1rem', color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', padding: '0.5rem 0', alignSelf: 'flex-end' }}>×</button>
        </div>
      ))}
      <button type="button" onClick={add} style={{ alignSelf: 'flex-start', fontSize: '0.825rem', color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>+ Add entry</button>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-1)', marginBottom: '0.75rem', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border)' }}>{title}</h2>
      {children}
    </div>
  )
}

export default function ResumePage() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [existing, setExisting] = useState<Resume | null>(null)
  const [checking, setChecking] = useState(true)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const [skills, setSkills] = useState<string[]>([])
  const [languages, setLanguages] = useState<string[]>([])
  const [experience, setExperience] = useState<ExperienceEntry[]>([])
  const [education, setEducation] = useState<EducationEntry[]>([])
  const [certifications, setCertifications] = useState<CertificationEntry[]>([])

  useEffect(() => {
    getMyResume()
      .then(r => { setExisting(r); populateFromResume(r) })
      .catch(() => setExisting(null))
      .finally(() => setChecking(false))
  }, [])

  const populateFromResume = (r: Resume) => {
    const c = r.content_extracted
    if (!c) return
    setSkills(c.skills ?? [])
    setLanguages(c.languages ?? [])
    setExperience(c.experience ?? [])
    setEducation(c.education ?? [])
    setCertifications(c.certifications ?? [])
  }

  const handleFile = async (file: File) => {
    setError('')
    setUploading(true)
    try {
      const r = await uploadResume(file)
      setExisting(r)
      populateFromResume(r)
    } catch (err: any) {
      setError(apiErrorMessage(err, 'Upload failed. Please try again.'))
    } finally {
      setUploading(false)
    }
  }

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      await updateExtractedContent({ skills, languages, experience, education, certifications })
      navigate('/applaut/dashboard')
    } catch (err: any) {
      setError(apiErrorMessage(err, 'Save failed. Please try again.'))
    } finally {
      setSaving(false)
    }
  }

  if (checking) return <p style={{ color: 'var(--text-2)' }}>Loading…</p>

  return (
    <div style={{ maxWidth: '680px' }}>
      <div style={{ marginBottom: '1.75rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 0.25rem', color: 'var(--text-1)' }}>Master Resume</h1>
        <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', margin: 0 }}>
          {existing
            ? `Currently using: ${existing.file_name} (v${existing.version}). Upload a new file to replace it.`
            : "Upload your resume and we'll extract your profile automatically."}
        </p>
      </div>

      {error && (
        <div style={{ padding: '0.75rem 1rem', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-xs)', marginBottom: '1.25rem' }}>
          <p style={{ color: 'var(--danger)', fontSize: '0.85rem', margin: 0 }}>{error}</p>
        </div>
      )}

      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--border-strong)'}`,
          borderRadius: 'var(--radius)',
          padding: '2.5rem 2rem',
          textAlign: 'center',
          cursor: uploading ? 'not-allowed' : 'pointer',
          background: dragging ? 'var(--accent-glow)' : 'var(--bg-surface)',
          marginBottom: '2rem',
          transition: 'border-color 0.15s, background 0.15s',
        }}
      >
        <input ref={fileInputRef} type="file" accept=".pdf,.docx" onChange={onFileChange} style={{ display: 'none' }} disabled={uploading} />
        {uploading ? (
          <div>
            <p style={{ color: 'var(--text-2)', margin: '0 0 0.25rem', fontWeight: 500 }}>Uploading and extracting…</p>
            <p style={{ color: 'var(--text-3)', fontSize: '0.825rem', margin: 0 }}>This may take a few seconds.</p>
          </div>
        ) : (
          <div>
            <div style={{ width: '40px', height: '40px', background: 'var(--accent-glow)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 0.875rem', fontSize: '1.25rem' }}>
              📄
            </div>
            <p style={{ fontWeight: 600, margin: '0 0 0.3rem', color: 'var(--text-1)', fontSize: '0.9rem' }}>Drop your resume here or click to browse</p>
            <p style={{ color: 'var(--text-3)', fontSize: '0.8rem', margin: 0 }}>PDF or DOCX · max 5 MB</p>
          </div>
        )}
      </div>

      {existing && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
          <Section title="Skills"><TagInput tags={skills} onChange={setSkills} /></Section>
          <Section title="Languages"><TagInput tags={languages} onChange={setLanguages} /></Section>
          <Section title="Experience"><ExperienceEditor entries={experience} onChange={setExperience} /></Section>
          <Section title="Education"><EducationEditor entries={education} onChange={setEducation} /></Section>
          <Section title="Certifications"><CertEditor entries={certifications} onChange={setCertifications} /></Section>

          <div style={{ display: 'flex', gap: '0.75rem', paddingTop: '0.5rem' }}>
            <button
              onClick={() => navigate('/applaut/dashboard')}
              style={{ flex: 1, padding: '0.625rem', background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-1)', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.9rem' }}
            >
              Cancel
            </button>
            <button
              onClick={save}
              disabled={saving}
              style={{ flex: 1, padding: '0.625rem', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 'var(--radius-xs)', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 600, opacity: saving ? 0.7 : 1 }}
            >
              {saving ? 'Saving…' : 'Confirm & save'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
