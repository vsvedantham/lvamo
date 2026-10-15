import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { useProshoAuth } from '../context/AuthContext'

// GitHub → backend → here, with a 2-minute login code in the URL fragment
// (never sent to a server). Swap it for an access token, then wipe it from
// the address bar and history.
export default function ProshoAuthCallback() {
  useDocumentTitle('Signing in… | ProSho')
  const { signInWithCode } = useProshoAuth()
  const navigate = useNavigate()
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return // StrictMode runs effects twice in dev
    started.current = true
    const code = new URLSearchParams(window.location.hash.slice(1)).get('code')
    window.history.replaceState(null, '', window.location.pathname)
    if (!code) {
      navigate('/prosho/login?error=failed', { replace: true })
      return
    }
    signInWithCode(code)
      .then(() => navigate('/prosho/dashboard', { replace: true }))
      .catch(() => navigate('/prosho/login?error=failed', { replace: true }))
  }, [navigate, signInWithCode])

  return <div style={{ padding: '2rem', color: 'var(--text-2)' }}>Signing in…</div>
}
