import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { resolveHomePath } from '../lib/session.js'

// Gates admin/bot routes (/dashboard, /bot*) behind a real Google session,
// checked via NextAuth's /api/auth/session (proxied to the Next.js backend
// -- see frontend/vercel.json).
//
// Paso 1 de Pulpo PRO/Lite (2026-07-22, ver web/auth.ts): además de
// autenticación, ahora también autoriza por rol/ruta -- un "scoped" no
// puede entrar a /dashboard (eso es admin-only), y solo puede entrar a
// /bot/:botId si ese id está en su session.user.botIds. El backend
// (proxy.ts) es el enforcement real; esto es para no mostrarle a un
// cliente una UI que igual le va a fallar con 403 en cada request.
export default function RequireAuth({ children }) {
  const [status, setStatus] = useState('checking') // checking | authed
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    let cancelled = false
    fetch('/api/auth/session')
      .then(res => res.json())
      .then(session => {
        if (cancelled) return
        if (!session?.user) { navigate('/'); return }

        const { role, botIds = [] } = session.user
        const path = location.pathname

        if (path.startsWith('/dashboard') && role !== 'admin') {
          navigate(resolveHomePath(session.user), { replace: true })
          return
        }

        const botMatch = path.match(/^\/bot\/([^/]+)$/)
        if (botMatch && botMatch[1] !== 'nueva' && role === 'scoped' && !botIds.includes(botMatch[1])) {
          navigate(resolveHomePath(session.user), { replace: true })
          return
        }

        setStatus('authed')
      })
      .catch(() => { if (!cancelled) navigate('/') })
    return () => { cancelled = true }
  }, [navigate, location.pathname])

  if (status !== 'authed') return null
  return children
}
