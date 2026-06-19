const TOKEN_KEY = 'bot_access_token'

export function getAccessToken() {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearAccessToken() {
  sessionStorage.removeItem(TOKEN_KEY)
}

async function refreshAccessToken() {
  const res = await fetch('/api/bot/refresh', { method: 'POST', credentials: 'include' })
  if (!res.ok) return null
  const data = await res.json()
  if (data.access_token) {
    setAccessToken(data.access_token)
    return data.access_token
  }
  return null
}

/**
 * Wrapper de fetch que:
 * - Agrega Authorization: Bearer <token>
 * - Si recibe 401, intenta refresh automático y reintenta
 * - Si refresh falla, limpia el token y devuelve la respuesta 401 original
 */
export async function authFetch(url, options = {}) {
  const token = getAccessToken()
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(url, { ...options, headers, credentials: 'include' })

  if (res.status === 401) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`
      return fetch(url, { ...options, headers, credentials: 'include' })
    }
    clearAccessToken()
  }

  return res
}
