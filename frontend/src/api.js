export function api(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }

  if (method === 'GET_BLOB') {
    return fetch('/api' + path, { headers, credentials: 'include' }).then(r => r.blob())
  }
  if (method === 'GET_TEXT') {
    return fetch('/api' + path, { headers, credentials: 'include' }).then(r => r.text())
  }

  return fetch('/api' + path, {
    method,
    headers,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  }).then(async r => {
    // 204 No Content (p.ej. DELETE) no trae body -- r.json() tira
    // SyntaxError sobre string vacío, lo que hacía que el caller nunca
    // llegara a actualizar su estado local tras un delete exitoso.
    if (r.status === 204) return r.ok ? null : { _status: r.status }
    const data = await r.json()
    if (!r.ok) return { ...data, _status: r.status }
    return data
  })
}

/**
 * Variante para polling/llamadas no críticas: nunca rechaza.
 * Los errores quedan en console.warn (rastro para debugging) y devuelve null.
 */
export function apiQuiet(method, path, body, label) {
  return api(method, path, body).catch(e => {
    console.warn('[api]', label || path, e)
    return null
  })
}
