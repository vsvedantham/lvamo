import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { useProshoAuth } from '../context/AuthContext'
import ProshoShell from '../components/ProshoShell'

export default function ProshoDashboard() {
  useDocumentTitle('Your projects | ProSho')
  const { user } = useProshoAuth()
  if (!user) return null

  return (
    <ProshoShell>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.35rem' }}>Your projects</h1>
      <p style={{ color: 'var(--text-2)', fontSize: '0.9rem' }}>
        Signed in as <strong style={{ color: 'var(--text-1)' }}>@{user.github_login}</strong>.
      </p>
    </ProshoShell>
  )
}
