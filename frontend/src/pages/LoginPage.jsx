import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

export default function LoginPage() {
  const [pwd, setPwd] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  // Auto-login si hay contraseña guardada
  useEffect(() => {
    const saved = sessionStorage.getItem('admin_pwd')
    if (!saved) return
    api('POST', '/auth', { password: saved })
      .then(res => {
        if (res.ok && res.role === 'admin') navigate('/dashboard')
        else sessionStorage.removeItem('admin_pwd')
      })
      .catch(() => {})
  }, [navigate])

  async function doLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await api('POST', '/auth', { password: pwd })
      if (!res.ok || res.role !== 'admin') {
        setError('Contraseña incorrecta')
        return
      }
      sessionStorage.setItem('admin_pwd', pwd)
      navigate('/dashboard')
    } catch {
      setError('Error de red')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-box">
        <h1>🔐 Admin</h1>
        <p>Ingresá la contraseña de administrador</p>
        <div className="login-error">{error}</div>
        <form onSubmit={doLogin}>
          <input
            type="password"
            placeholder="Contraseña"
            value={pwd}
            onChange={e => setPwd(e.target.value)}
            autoFocus
            style={{ width: '100%', marginBottom: 12 }}
          />
          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
            style={{ width: '100%', padding: 11 }}
          >
            {loading ? 'Verificando...' : 'Entrar'}
          </button>
        </form>
      </div>
    </div>
  )
}
