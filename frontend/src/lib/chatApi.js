import { getVisitorKey } from './chatVisitor.js'

/**
 * Cliente HTTP del runtime del chat (/api/chat/**) -- deliberadamente
 * separado de api.js (ese es para el dashboard autenticado por sesión). Acá
 * la sesión es opcional: siempre mandamos credentials:'include' (por si hay
 * sesión de Google) Y el header X-Chat-Visitor (por si no la hay) -- el
 * backend decide cuál importa, ver web/lib/auth/chat-access.ts.
 */
async function call(method, path, body) {
  const res = await fetch('/api' + path, {
    method,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Chat-Visitor': getVisitorKey(),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  return { ...data, _status: res.status, _ok: res.ok }
}

export const chatApi = {
  getConfig: (botId) => call('GET', `/chat/${botId}/config`),
  listConversations: (botId) => call('GET', `/chat/${botId}/conversations`),
  createConversation: (botId) => call('POST', `/chat/${botId}/conversations`, {}),
  getMessages: (botId, conversationId, afterId) =>
    call('GET', `/chat/${botId}/conversations/${conversationId}/messages${afterId ? `?after=${afterId}` : ''}`),
  sendMessage: (botId, conversationId, message) =>
    call('POST', `/chat/${botId}/conversations/${conversationId}/messages`, { message }),
}
