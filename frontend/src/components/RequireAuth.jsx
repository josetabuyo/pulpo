import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

// Gates admin routes (/dashboard, /bot*) behind a real Google session,
// checked via NextAuth's /api/auth/session (proxied to the Next.js backend
// -- see frontend/vercel.json). Replaces the old sessionStorage['admin_pwd']
// check that used to live inline in DashboardPage's useEffect.
export default function RequireAuth({ children }) {
  const [status, setStatus] = useState('checking') // checking | authed
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false
    fetch('/api/auth/session')
      .then(res => res.json())
      .then(session => {
        if (cancelled) return
        if (session?.user) setStatus('authed')
        else navigate('/')
      })
      .catch(() => { if (!cancelled) navigate('/') })
    return () => { cancelled = true }
  }, [navigate])

  if (status !== 'authed') return null
  return children
}
