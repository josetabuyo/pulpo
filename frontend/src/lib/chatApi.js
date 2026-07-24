import { getVisitorKey } from './chatVisitor.js'

/**
 * Cliente HTTP del runtime del chat (/api/chat/{botId}/{chatId}/**) --
 * deliberadamente separado de api.js (ese es para el dashboard autenticado
 * por sesión). Acá la sesión es opcional: siempre mandamos
 * credentials:'include' (por si hay sesión de Google) Y el header
 * X-Chat-Visitor (por si no la hay) -- el backend decide cuál importa, ver
 * web/lib/auth/chat-access.ts.
 *
 * 2026-07-23: un bot puede tener N chats -- todas las rutas de runtime
 * quedan bajo `/chat/{botId}/{chatId}/...` (antes `/chat/{botId}/...`, un
 * único chat implícito por bot).
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
  getConfig: (botId, chatId) => call('GET', `/chat/${botId}/${chatId}/config`),
  listConversations: (botId, chatId) => call('GET', `/chat/${botId}/${chatId}/conversations`),
  createConversation: (botId, chatId) => call('POST', `/chat/${botId}/${chatId}/conversations`, {}),
  getMessages: (botId, chatId, conversationId, afterId) =>
    call('GET', `/chat/${botId}/${chatId}/conversations/${conversationId}/messages${afterId ? `?after=${afterId}` : ''}`),
  sendMessage: (botId, chatId, conversationId, message) =>
    call('POST', `/chat/${botId}/${chatId}/conversations/${conversationId}/messages`, { message }),
}
