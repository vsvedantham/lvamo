import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { createApplication } from '../api/applications'
import { generateDocuments, getDocumentFileLink, getOpportunityDocuments, type DocumentItem, type GenerationMode, type OpportunityDocuments } from '../api/documents'
import { getOpportunity, type OpportunityDetail } from '../api/opportunity'
import { getMyProfile, JOB_ENGINE_LABELS, type JobEngine } from '../api/profile'
import { apiErrorMessage } from '../api/errors'

function MarkdownBlock({ content }: { content: string }) {
  return (
    <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit', fontSize: '0.875rem', lineHeight: 1.6, color: 'var(--text-1)', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: '6px', padding: '1.25rem', margin: 0 }}>
      {content}
    </pre>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button onClick={copy} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem', border: '1px solid #d1d5db', borderRadius: '6px', cursor: 'pointer', background: 'transparent' }}>
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

function DownloadButton({ content, filename }: { content: string; filename: string }) {
  const download = () => {
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <button onClick={download} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem', border: '1px solid #d1d5db', borderRadius: '6px', cursor: 'pointer', background: 'transparent' }}>
      Download .md
    </button>
  )
}

export default function DocumentDetail() {
  const { opportunityId } = useParams<{ opportunityId: string }>()
  const navigate = useNavigate()
  const [opp, setOpp] = useState<OpportunityDetail | null>(null)
  const [docs, setDocs] = useState<OpportunityDocuments | null>(null)
  const [activeTab, setActiveTab] = useState<'resume' | 'cover_letter'>('resume')
  const [mode, setMode] = useState<GenerationMode>('template')
  const [generating, setGenerating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [startingApp, setStartingApp] = useState(false)
  const [appStarted, setAppStarted] = useState(false)
  const [engine, setEngine] = useState<JobEngine | null>(null)
  const [openingPdf, setOpeningPdf] = useState(false)

  useEffect(() => {
    if (!opportunityId) return
    Promise.all([
      getOpportunity(opportunityId),
      getOpportunityDocuments(opportunityId),
      getMyProfile(),
    ]).then(([o, d, p]) => {
      setOpp(o)
      setDocs(d)
      setEngine(p.job_engine)
    }).catch(() => setError('Failed to load.')).finally(() => setLoading(false))
  }, [opportunityId])

  const generate = async () => {
    if (!opportunityId) return
    setGenerating(true)
    setError('')
    try {
      const result = await generateDocuments(opportunityId, mode)
      setDocs({
        opportunity_id: opportunityId,
        tailored_resume: result.tailored_resume,
        cover_letter: result.cover_letter,
      })
    } catch (err: any) {
      setError(apiErrorMessage(err, 'Generation failed.'))
    } finally {
      setGenerating(false)
    }
  }

  const startApplication = async () => {
    if (!opportunityId) return
    setStartingApp(true)
    try {
      await createApplication(opportunityId)
      setAppStarted(true)
    } catch (err: any) {
      if (err.response?.status === 409) {
        navigate('/applaut/applications')
      }
    } finally {
      setStartingApp(false)
    }
  }

  const activeDoc: DocumentItem | null | undefined =
    activeTab === 'resume' ? docs?.tailored_resume : docs?.cover_letter

  // Applaut's templates only write documents for Applaut Basic's own jobs;
  // an AI engine's job comes with its engine's CV and cover letter.
  const canGenerate = engine === 'basic' && opp !== null && !opp.is_private

  const openPdf = async (doc: DocumentItem) => {
    // Open the tab now (inside the click) so popup blockers allow it, then
    // point it at the short-lived signed link.
    const tab = window.open('', '_blank')
    setOpeningPdf(true)
    setError('')
    try {
      const { url } = await getDocumentFileLink(doc.id)
      if (tab) tab.location.href = url
      else window.location.href = url
    } catch {
      tab?.close()
      setError('Could not open the PDF. Please try again.')
    } finally {
      setOpeningPdf(false)
    }
  }

  const filename = activeTab === 'resume'
    ? `${opp?.company_name ?? 'resume'}_tailored_resume.md`
    : `${opp?.company_name ?? 'cover'}_cover_letter.md`

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      {/* Back link */}
      <Link to="/applaut/opportunities" style={{ fontSize: '0.875rem', color: '#6b7280', textDecoration: 'none' }}>
        ← Back to opportunities
      </Link>

      {/* Header */}
      <div style={{ margin: '1rem 0 1.5rem' }}>
        <h1 style={{ fontSize: '1.4rem', fontWeight: 700, margin: 0 }}>
          Documents
        </h1>
        {opp && (
          <p style={{ color: '#6b7280', fontSize: '0.875rem', margin: '0.25rem 0 0' }}>
            {opp.title} · {opp.company_name}
          </p>
        )}
      </div>

      {/* Generate controls (Applaut Basic) and document actions */}
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        {canGenerate && (<>
        <select
          value={mode}
          onChange={e => setMode(e.target.value as GenerationMode)}
          style={{ padding: '0.4rem 0.75rem', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '0.875rem' }}
        >
          <option value="template">Template-based</option>
          <option value="ai">AI (requires API key)</option>
        </select>
        <button
          onClick={generate}
          disabled={generating || loading}
          style={{ padding: '0.5rem 1.25rem', background: '#111827', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.875rem', opacity: generating ? 0.7 : 1 }}
        >
          {generating ? 'Generating…' : docs?.tailored_resume ? 'Regenerate' : 'Generate documents'}
        </button>
        </>)}
        {activeDoc?.has_file && (
          <button
            onClick={() => openPdf(activeDoc)}
            disabled={openingPdf}
            style={{ padding: '0.5rem 1.25rem', background: '#111827', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.875rem', opacity: openingPdf ? 0.7 : 1 }}
          >
            {openingPdf ? 'Opening…' : 'Open PDF'}
          </button>
        )}
        {activeDoc && (
          <>
            <CopyButton text={activeDoc.content} />
            {!activeDoc.has_file && <DownloadButton content={activeDoc.content} filename={filename} />}
          </>
        )}
        {appStarted ? (
          <Link
            to="/applaut/applications"
            style={{ padding: '0.4rem 1rem', background: '#059669', color: '#fff', borderRadius: '6px', textDecoration: 'none', fontSize: '0.875rem' }}
          >
            Application started ✓
          </Link>
        ) : (
          <button
            onClick={startApplication}
            disabled={startingApp || loading}
            style={{ padding: '0.4rem 1rem', background: '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.875rem', opacity: startingApp ? 0.7 : 1 }}
          >
            {startingApp ? 'Starting…' : 'Start application'}
          </button>
        )}
      </div>

      {error && (
        <p style={{ padding: '0.75rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', fontSize: '0.875rem', marginBottom: '1rem' }}>
          {error}
        </p>
      )}

      {loading ? (
        <p style={{ color: '#6b7280' }}>Loading…</p>
      ) : !docs?.tailored_resume && !docs?.cover_letter ? (
        <div style={{ padding: '3rem', textAlign: 'center', border: '1px dashed #d1d5db', borderRadius: '8px' }}>
          <p style={{ fontWeight: 600, marginBottom: '0.5rem' }}>No documents yet</p>
          <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>
            {canGenerate
              ? 'Click "Generate documents" to create a tailored resume and cover letter.'
              : engine && engine !== 'basic'
                ? `Your CV and cover letter for this job will appear here once ${JOB_ENGINE_LABELS[engine]} has written them.`
                : 'Documents for this job come from your job engine.'}
          </p>
        </div>
      ) : (
        <>
          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb', marginBottom: '1rem' }}>
            {([['resume', 'Tailored Resume'], ['cover_letter', 'Cover Letter']] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                style={{ padding: '0.5rem 1.25rem', background: 'transparent', border: 'none', borderBottom: activeTab === key ? '2px solid #111827' : '2px solid transparent', cursor: 'pointer', fontWeight: activeTab === key ? 600 : 400, fontSize: '0.9rem', marginBottom: '-1px' }}
              >
                {label}
              </button>
            ))}
          </div>

          {activeDoc ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
                  {activeDoc.engine === 'basic'
                    ? `Mode: ${activeDoc.generation_mode}`
                    : `Written by ${JOB_ENGINE_LABELS[activeDoc.engine]}${activeDoc.has_file ? ' · text version below, open the PDF for the formatted document' : ''}`}
                  {' · '}{new Date(activeDoc.created_at).toLocaleString()}
                </span>
              </div>
              <MarkdownBlock content={activeDoc.content} />
            </>
          ) : (
            <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>{canGenerate ? 'Not generated yet — click "Generate documents".' : 'Not available yet.'}</p>
          )}
        </>
      )}
    </div>
  )
}
