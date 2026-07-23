/**
 * Visitor key para chats públicos sin sesión (§4.3 del handoff de chats,
 * management/HANDOFF_DASHBOARD_CHATS_VIEW.md, gitignoreado): un uuid
 * generado una vez por browser y guardado en localStorage, mandado como
 * header X-Chat-Visitor. Identificación débil a propósito (quien tenga el
 * uuid lee esa conversación) -- mismo trade-off que cualquier chat de
 * soporte anónimo, documentado, no un bug.
 */
const KEY = 'pulpochat_visitor_key'

export function getVisitorKey() {
  let key = localStorage.getItem(KEY)
  if (!key) {
    key = (crypto.randomUUID ? crypto.randomUUID() : `v-${Date.now()}-${Math.random().toString(36).slice(2)}`)
    localStorage.setItem(KEY, key)
  }
  return key
}
