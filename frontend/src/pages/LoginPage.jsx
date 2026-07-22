import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function LoginPage() {
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => { document.title = 'Pulpo — Admin' }, [])

  // Si ya hay una sesión de Google válida, saltar directo al dashboard.
  useEffect(() => {
    fetch('/api/auth/session')
      .then(res => res.json())
      .then(session => {
        if (session?.user) navigate('/dashboard')
      })
      .catch(() => {})
  }, [navigate])

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('error')) {
      setError('Tu cuenta de Google no tiene acceso a este panel.')
    }
  }, [])

  // Auth.js v5 no soporta un GET directo a /api/auth/signin/google (tira
  // "UnknownAction: Unsupported action") -- el flujo real es el que hace
  // next-auth/react's signIn(): pedir un CSRF token y POSTear con él, la
  // respuesta trae la URL real de Google a la que recién ahí se navega.
  async function loginWithGoogle() {
    const { csrfToken } = await fetch('/api/auth/csrf').then(r => r.json())
    const res = await fetch('/api/auth/signin/google', {
      method: 'POST',
      // Sin este header, Auth.js responde con un 302 real hacia Google en vez
      // de JSON {url} -- un fetch no puede seguir ese redirect (bloqueado por
      // CORS, Google no manda Access-Control-Allow-Origin), por eso el
      // request se ve fallar en el navegador aunque el backend esté bien.
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Auth-Return-Redirect': '1',
      },
      body: new URLSearchParams({ csrfToken, callbackUrl: '/dashboard' }),
    })
    const { url } = await res.json()
    if (url) window.location.href = url
  }

  return (
    <div className="login-screen">
      <div className="login-box">
        <h1>🔐 Admin</h1>
        <p>Ingresá con tu cuenta de Google</p>
        <div className="login-error">{error}</div>
        <button
          type="button"
          className="btn-primary"
          onClick={loginWithGoogle}
          style={{ width: '100%', padding: 11 }}
        >
          Continuar con Google
        </button>
      </div>
    </div>
  )
}
