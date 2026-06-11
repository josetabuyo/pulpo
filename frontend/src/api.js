export function api(method, path, body, password) {
  const headers = { 'Content-Type': 'application/json' }
  if (password) headers['x-password'] = password

  if (method === 'GET_BLOB') {
    return fetch('/api' + path, { headers }).then(r => r.blob())
  }
  if (method === 'GET_TEXT') {
    return fetch('/api' + path, { headers }).then(r => r.text())
  }

  return fetch('/api' + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  }).then(async r => {
    const data = await r.json()
    if (!r.ok) return { ...data, _status: r.status }
    return data
  })
}

/**
 * Variante para polling/llamadas no críticas: nunca rechaza.
 * Los errores quedan en console.warn (rastro para debugging) y devuelve null.
 */
export function apiQuiet(method, path, body, password, label) {
  return api(method, path, body, password).catch(e => {
    console.warn('[api]', label || path, e)
    return null
  })
}
