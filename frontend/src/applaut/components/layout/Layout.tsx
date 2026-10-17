import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import Logo from '../../../components/Logo'
import BrandedPage from '../../../components/BrandedPage'
import {
  getNotifications,
  markAllRead,
  markRead,
  type AppNotification,
} from '../../api/notifications'

const PUBLIC_PATHS = ['/applaut', '/applaut/login', '/applaut/register']
const MOBILE_BREAKPOINT = 768
const SIDEBAR_W_MOBILE = 260

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= MOBILE_BREAKPOINT)
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`)
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return isMobile
}

const IconDashboard = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" />
  </svg>
)
const IconSearch = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
)
const IconBriefcase = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
  </svg>
)
const IconFile = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
  </svg>
)
const IconBell = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
  </svg>
)
const IconSettings = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
)
const IconLogout = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
  </svg>
)
const IconX = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function NotificationPanel({ isMobile }: { isMobile: boolean }) {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [unread, setUnread] = useState(0)
  const ref = useRef<HTMLDivElement>(null)

  const load = async () => {
    try {
      const res = await getNotifications()
      setNotifications(res.items)
      setUnread(res.unread_count)
    } catch { /* not authenticated yet */ }
  }

  useEffect(() => {
    if (!user) return
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [user])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleMarkAllRead = async () => {
    await markAllRead()
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
    setUnread(0)
  }

  const handleMarkRead = async (id: string) => {
    await markRead(id)
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
    setUnread(prev => Math.max(0, prev - 1))
  }

  // On mobile: popup floats above button inside sidebar (absolute)
  // On desktop: popup floats to the right of sidebar (fixed)
  const popupStyle: React.CSSProperties = isMobile
    ? {
        position: 'absolute',
        bottom: '100%',
        left: 0,
        right: 0,
        marginBottom: '0.5rem',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius)',
        boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
        zIndex: 100,
        overflow: 'hidden',
      }
    : {
        position: 'fixed',
        left: 'var(--sidebar-w)',
        bottom: '3rem',
        width: '320px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius)',
        boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
        zIndex: 100,
        overflow: 'hidden',
      }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        aria-label="Notifications"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          width: '100%',
          padding: '0.625rem 0.75rem',
          minHeight: '44px',
          background: 'transparent',
          border: 'none',
          borderRadius: 'var(--radius-xs)',
          color: 'var(--text-2)',
          fontSize: '0.85rem',
          cursor: 'pointer',
          transition: 'background 0.15s, color 0.15s',
        }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-elevated)'; e.currentTarget.style.color = 'var(--text-1)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-2)' }}
      >
        <IconBell />
        <span>Notifications</span>
        {unread > 0 && (
          <span style={{ marginLeft: 'auto', padding: '0.1rem 0.4rem', background: 'var(--accent)', color: '#fff', borderRadius: '999px', fontSize: '0.7rem', fontWeight: 700, lineHeight: '1.4' }}>
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div style={popupStyle}>
          <div style={{ padding: '0.875rem 1rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>Notifications</span>
            {unread > 0 && (
              <button onClick={handleMarkAllRead} style={{ fontSize: '0.75rem', color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>
                Mark all read
              </button>
            )}
          </div>
          <div style={{ maxHeight: '320px', overflowY: 'auto' }}>
            {notifications.length === 0 ? (
              <p style={{ padding: '1.5rem 1rem', color: 'var(--text-2)', fontSize: '0.875rem', textAlign: 'center' }}>No notifications yet</p>
            ) : notifications.map(n => (
              <div
                key={n.id}
                onClick={() => !n.is_read && handleMarkRead(n.id)}
                style={{
                  padding: '0.75rem 1rem',
                  borderBottom: '1px solid var(--border)',
                  background: n.is_read ? 'transparent' : 'var(--accent-glow)',
                  cursor: n.is_read ? 'default' : 'pointer',
                }}
              >
                <p style={{ fontSize: '0.8rem', margin: '0 0 0.2rem', color: n.is_read ? 'var(--text-2)' : 'var(--text-1)' }}>{n.title}{n.body ? ` — ${n.body}` : ''}</p>
                <p style={{ fontSize: '0.7rem', color: 'var(--text-3)', margin: 0 }}>{timeAgo(n.created_at)}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const navItems = [
  { to: '/applaut/dashboard', label: 'Dashboard', icon: <IconDashboard /> },
  { to: '/applaut/opportunities', label: 'Opportunities', icon: <IconSearch /> },
  { to: '/applaut/applications', label: 'Applications', icon: <IconBriefcase /> },
  { to: '/applaut/resume', label: 'Resume', icon: <IconFile /> },
  { to: '/applaut/settings', label: 'Settings', icon: <IconSettings /> },
]

function Sidebar({ isMobile, open, onClose }: { isMobile: boolean; open: boolean; onClose: () => void }) {
  const { user, logout } = useAuth()

  return (
    <aside style={{
      position: 'fixed',
      top: 0,
      left: 0,
      width: isMobile ? `${SIDEBAR_W_MOBILE}px` : 'var(--sidebar-w)',
      height: '100vh',
      background: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      zIndex: 60,
      transform: isMobile && !open ? 'translateX(-100%)' : 'translateX(0)',
      transition: 'transform 0.25s ease',
    }}>
      {/* Header: logo + close button on mobile */}
      <div style={{ padding: '1.125rem 1rem', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Link to="/" title="Back to LVAMO" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Logo />
          <div>
            <p style={{ fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.12em', color: 'var(--accent)', textTransform: 'uppercase', lineHeight: 1 }}>LVAMO</p>
            <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-1)', lineHeight: 1.4 }}>Applaut</p>
          </div>
        </Link>
        {isMobile && (
          <button
            onClick={onClose}
            aria-label="Close navigation"
            style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', padding: '0.25rem', borderRadius: '4px', display: 'flex', alignItems: 'center', minWidth: '44px', minHeight: '44px', justifyContent: 'center' }}
          >
            <IconX />
          </button>
        )}
      </div>

      {/* Nav links */}
      <nav style={{ flex: 1, padding: '0.625rem 0.5rem', display: 'flex', flexDirection: 'column', gap: '0.125rem', overflowY: 'auto' }}>
        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={isMobile ? onClose : undefined}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: '0.625rem',
              padding: '0.625rem 0.75rem',
              minHeight: '44px',
              borderRadius: 'var(--radius-xs)',
              fontSize: '0.9rem',
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--accent)' : 'var(--text-2)',
              background: isActive ? 'var(--accent-glow)' : 'transparent',
              textDecoration: 'none',
              transition: 'background 0.15s, color 0.15s',
            })}
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer: notifications + user */}
      <div style={{ padding: '0.5rem', borderTop: '1px solid var(--border)' }}>
        <NotificationPanel isMobile={isMobile} />
        <div style={{ padding: '0.5rem 0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.125rem', minHeight: '44px' }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <p style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-1)', lineHeight: 1.2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.name}</p>
            <p style={{ fontSize: '0.7rem', color: 'var(--text-3)', lineHeight: 1.2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user?.email}</p>
          </div>
          <button
            onClick={logout}
            title="Log out"
            aria-label="Log out"
            style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', padding: '0.25rem', borderRadius: '4px', display: 'flex', alignItems: 'center', flexShrink: 0, marginLeft: '0.5rem', minWidth: '44px', minHeight: '44px', justifyContent: 'center', transition: 'color 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--danger)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
          >
            <IconLogout />
          </button>
        </div>
      </div>
    </aside>
  )
}

function TopBar({ onOpen }: { onOpen: () => void }) {
  return (
    <header style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      height: '54px',
      background: 'var(--bg-sidebar)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 1rem',
      gap: '0.75rem',
      zIndex: 50,
    }}>
      <button
        onClick={onOpen}
        aria-label="Open navigation"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '5px',
          padding: '0.625rem',
          minWidth: '44px',
          minHeight: '44px',
          justifyContent: 'center',
          alignItems: 'center',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--text-2)',
          borderRadius: 'var(--radius-xs)',
        }}
      >
        {[0, 1, 2].map(i => (
          <span key={i} style={{ display: 'block', width: '18px', height: '2px', background: 'currentColor', borderRadius: '1px' }} />
        ))}
      </button>
      <Link to="/" title="Back to LVAMO" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <Logo />
        <div>
          <p style={{ fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.12em', color: 'var(--accent)', textTransform: 'uppercase', lineHeight: 1 }}>LVAMO</p>
          <p style={{ fontSize: '0.825rem', fontWeight: 600, color: 'var(--text-1)', lineHeight: 1.3 }}>Applaut</p>
        </div>
      </Link>
    </header>
  )
}

function PublicLayout() {
  return (
    <BrandedPage>
      <Outlet />
    </BrandedPage>
  )
}

export default function Layout() {
  const { pathname } = useLocation()
  const isPublic = PUBLIC_PATHS.includes(pathname)
  const isMobile = useIsMobile()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Close sidebar on navigation
  useEffect(() => setSidebarOpen(false), [pathname])

  // Prevent body scroll when mobile sidebar is open
  useEffect(() => {
    document.body.style.overflow = isMobile && sidebarOpen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [isMobile, sidebarOpen])

  if (isPublic) return <PublicLayout />

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Backdrop — mobile only */}
      {isMobile && sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            zIndex: 55,
          }}
        />
      )}

      <Sidebar isMobile={isMobile} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Mobile top bar */}
      {isMobile && <TopBar onOpen={() => setSidebarOpen(true)} />}

      <main style={{
        marginLeft: isMobile ? 0 : 'var(--sidebar-w)',
        flex: 1,
        padding: isMobile ? '4.5rem 1rem 2rem' : '2rem 2.5rem',
        minHeight: '100vh',
        maxWidth: isMobile ? '100vw' : 'calc(100vw - var(--sidebar-w))',
        width: '100%',
      }}>
        <Outlet />
      </main>
    </div>
  )
}
