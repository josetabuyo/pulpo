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

// Gestión de publicidad de un chat (ChatsTab/ChatForm, sesión autenticada
// vía apiCall del dashboard -- ver web/app/api/bots/[botId]/chat-configs/
// [chatId]/ads/**). El camino público bot-key (publish/unpublish) es cosa
// del sistema EXTERNO del cliente, no de este dashboard -- no tiene cliente
// JS acá.
export const chatAdsApi = {
  list: (apiCall, botId, chatId) => apiCall('GET', `/bots/${botId}/chat-configs/${chatId}/ads`, null),
  create: (apiCall, botId, chatId, body) => apiCall('POST', `/bots/${botId}/chat-configs/${chatId}/ads`, body),
  update: (apiCall, botId, chatId, adId, body) =>
    apiCall('PATCH', `/bots/${botId}/chat-configs/${chatId}/ads/${adId}`, body),
  setPublished: (apiCall, botId, chatId, adId, published) =>
    apiCall('PATCH', `/bots/${botId}/chat-configs/${chatId}/ads/${adId}`, { published }),
  remove: (apiCall, botId, chatId, adId) => apiCall('DELETE', `/bots/${botId}/chat-configs/${chatId}/ads/${adId}`, null),
}
