/**
 * useFbSession — renueva las cookies de Facebook abriendo un browser en el server.
 *
 * Flujo: POST /fb/refresh-session → polling de /fb/session-status hasta ok/error
 * con corte a los MAX_WAIT_MS. Todos los timers se limpian al desmontar
 * (antes el interval quedaba vivo si salías del dashboard durante el login).
 */
import { useState, useRef, useEffect, useCallback } from 'react'

const POLL_MS = 3_000        // intervalo de chequeo del estado del login
const MAX_WAIT_MS = 130_000  // corte si el login nunca se completa
const IDLE_LABEL = 'FB Sesión'

export function useFbSession(call) {
  const [label, setLabel] = useState(IDLE_LABEL)
  const [running, setRunning] = useState(false)
  const timers = useRef([])

  const clearTimers = useCallback(() => {
    timers.current.forEach(t => { clearInterval(t); clearTimeout(t) })
    timers.current = []
  }, [])

  useEffect(() => clearTimers, [clearTimers])

  function reset() {
    setLabel(IDLE_LABEL)
    setRunning(false)
  }

  function finish(text, delayMs) {
    setLabel(text)
    const t = setTimeout(reset, delayMs)
    timers.current.push(t)
  }

  const start = useCallback(async (pageId = 'luganense') => {
    if (running) return
    setRunning(true)
    setLabel('Abriendo browser…')
    try {
      const res = await call('POST', `/fb/refresh-session?page_id=${pageId}`, {})
      if (!res.ok) {
        finish('⚠ ' + (res.message || 'Error'), 5000)
        return
      }
      setLabel('Esperando login…')
      const poll = setInterval(async () => {
        try {
          const st = await call('GET', `/fb/session-status?page_id=${pageId}`, null)
          if (st.state === 'ok') {
            clearInterval(poll)
            finish('✓ Sesión renovada', 4000)
          } else if (st.state === 'error') {
            clearInterval(poll)
            finish('⚠ ' + (st.message || 'Error'), 5000)
          }
        } catch (e) {
          console.warn('[useFbSession] status', e)
          clearInterval(poll)
          reset()
        }
      }, POLL_MS)
      timers.current.push(poll)
      const cutoff = setTimeout(() => { clearInterval(poll); reset() }, MAX_WAIT_MS)
      timers.current.push(cutoff)
    } catch (e) {
      console.warn('[useFbSession] refresh', e)
      finish('⚠ Error', 4000)
    }
  }, [call, running])

  return { fbLabel: label, fbRunning: running, startFbSession: start }
}
