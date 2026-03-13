export function api(method, path, body, password) {
  const headers = { 'Content-Type': 'application/json' }
  if (password) headers['x-password'] = password
  return fetch('/api' + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  }).then(r => r.json())
}

export async function connectAndPoll({ number, password, onQR, onReady, onError }) {
  let interval = null
  const stop = () => { if (interval) { clearInterval(interval); interval = null } }

  let res
  try {
    res = await fetch(`/api/connect/${number}`, {
      method: 'POST',
      headers: { 'x-password': password },
    }).then(r => r.json())
  } catch {
    onError('Error de red. Verificá la conexión.')
    return stop
  }

  if (res.error) { onError(res.error); return stop }

  const sessionId = res.sessionId

  interval = setInterval(async () => {
    try {
      const data = await fetch(`/api/qr/${sessionId}`, {
        headers: { 'x-password': password },
      }).then(r => r.json())

      if (data.status === 'ready') { stop(); onReady(); return }
      if (data.status === 'failed' || data.status === 'disconnected') {
        stop(); onError('Error al conectar. Intentá de nuevo.'); return
      }
      if (data.qr) onQR(data.qr)
    } catch {}
  }, 3000)

  return stop
}
