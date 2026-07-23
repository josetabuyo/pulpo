/**
 * ChatPage — página pública/allowlist standalone del chat de un bot, estilo
 * ChatGPT. Ruta SIN RequireAuth (precedente: /embed/flow/:botId ya es
 * pública en el SPA, ver App.jsx) -- esta página decide sola si hace falta
 * login, pidiendo GET /api/chat/{botId}/config primero (siempre público) y
 * dejando que las rutas de conversaciones devuelvan 401 login_required si
 * hace falta. Ver management/HANDOFF_DASHBOARD_CHATS_VIEW.md §4.6/§5.2
 * (gitignoreado) para el diseño completo.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { chatApi } from '../lib/chatApi.js'
import ChatSidebar from '../components/chat/ChatSidebar.jsx'
import ChatThread from '../components/chat/ChatThread.jsx'
import ChatComposer from '../components/chat/ChatComposer.jsx'
import ChatBanners from '../components/chat/ChatBanners.jsx'
import './../components/chat/chat.css'

const POLL_MS = 2000
const TERMINAL_STATUSES = new Set(['completed', 'handed_off', 'error', 'waiting_gate', null])

// Auth.js v5 no soporta GET directo a /api/auth/signin/google -- mismo
// flujo CSRF+POST que frontend/src/pages/LoginPage.jsx.
async function loginWithGoogle(callbackUrl) {
  const { csrfToken } = await fetch('/api/auth/csrf').then(r => r.json())
  const res = await fetch('/api/auth/signin/google', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Auth-Return-Redirect': '1',
    },
    body: new URLSearchParams({ csrfToken, callbackUrl }),
  })
  const { url } = await res.json()
  if (url) window.location.href = url
}

export default function ChatPage() {
  const { botId, conversationId } = useParams()
  const navigate = useNavigate()

  const [config, setConfig] = useState(null)
  const [configError, setConfigError] = useState('')
  const [needsLogin, setNeedsLogin] = useState(false)
  const [conversations, setConversations] = useState([])
  const [messages, setMessages] = useState([])
  const [runStatus, setRunStatus] = useState(null)
  const [sendError, setSendError] = useState('')
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [mobileBannersOpen, setMobileBannersOpen] = useState(false)

  const lastIdRef = useRef(0)
  const pollRef = useRef(null)

  // ── Config pública ──
  useEffect(() => {
    let cancelled = false
    chatApi.getConfig(botId).then(res => {
      if (cancelled) return
      if (res._status === 404) { setConfigError('Este chat no existe.'); return }
      if (!res._ok) { setConfigError('No se pudo cargar la configuración del chat.'); return }
      setConfig(res)
      document.title = res.title || 'PulpoChat'
    })
    return () => { cancelled = true }
  }, [botId])

  // ── Conversaciones propias (dispara login_required si hace falta) ──
  const loadConversations = useCallback(async () => {
    const res = await chatApi.listConversations(botId)
    if (res._status === 401) { setNeedsLogin(true); return null }
    if (!res._ok) return null
    setNeedsLogin(false)
    setConversations(Array.isArray(res) ? res : [])
    return res
  }, [botId])

  useEffect(() => {
    if (!config || !config.enabled) return
    loadConversations()
  }, [config, loadConversations])

  // ── Sin conversationId: abrir la última o crear una ──
  useEffect(() => {
    if (!config || !config.enabled || needsLogin || conversationId) return
    let cancelled = false
    ;(async () => {
      const list = await loadConversations()
      if (cancelled || !list) return
      if (list.length > 0) {
        navigate(`/chat/${botId}/c/${list[0].id}`, { replace: true })
      } else {
        const created = await chatApi.createConversation(botId)
        if (!cancelled && created._ok) navigate(`/chat/${botId}/c/${created.id}`, { replace: true })
      }
    })()
    return () => { cancelled = true }
  }, [config, needsLogin, conversationId, botId, navigate, loadConversations])

  // ── Polling de mensajes de la conversación activa ──
  useEffect(() => {
    if (!conversationId || needsLogin) return
    lastIdRef.current = 0
    setMessages([])
    setRunStatus(null)

    let cancelled = false
    async function poll() {
      const res = await chatApi.getMessages(botId, conversationId, lastIdRef.current || undefined)
      if (cancelled) return
      if (!res._ok) return
      if (res.messages?.length) {
        setMessages(prev => [...prev, ...res.messages])
        lastIdRef.current = res.messages[res.messages.length - 1].id
      }
      setRunStatus(res.run_status ?? null)
    }
    poll()
    pollRef.current = setInterval(poll, POLL_MS)
    return () => { cancelled = true; clearInterval(pollRef.current) }
  }, [botId, conversationId, needsLogin])

  async function handleSend(text) {
    setSendError('')
    const res = await chatApi.sendMessage(botId, conversationId, text)
    if (!res._ok) { setSendError(res.error || 'No se pudo enviar el mensaje'); return }
    setRunStatus('running')
    // Empuja un poll inmediato en vez de esperar el próximo intervalo.
    chatApi.getMessages(botId, conversationId, lastIdRef.current || undefined).then(r => {
      if (r._ok && r.messages?.length) {
        setMessages(prev => [...prev, ...r.messages])
        lastIdRef.current = r.messages[r.messages.length - 1].id
      }
      if (r._ok) setRunStatus(r.run_status ?? null)
    })
  }

  function handleNewConversation() {
    chatApi.createConversation(botId).then(res => {
      if (res._ok) navigate(`/chat/${botId}/c/${res.id}`)
    })
  }

  if (configError) {
    return (
      <div className="pulpochat">
        <div className="pc-fullscreen-msg">{configError}</div>
      </div>
    )
  }

  if (!config) {
    return (
      <div className="pulpochat">
        <div className="pc-fullscreen-msg">Cargando...</div>
      </div>
    )
  }

  if (!config.enabled) {
    return (
      <div className="pulpochat">
        <div className="pc-fullscreen-msg">Este chat está deshabilitado por el momento.</div>
      </div>
    )
  }

  if (needsLogin) {
    return (
      <div className="pulpochat" style={config.theme_vars || {}}>
        {config.custom_css && <style>{config.custom_css}</style>}
        <div className="pc-login-screen">
          <div className="pc-login-box">
            <h1>{config.title}</h1>
            <p>Necesitás iniciar sesión para chatear.</p>
            <button
              className="pc-login-btn"
              onClick={() => loginWithGoogle(`/chat/${botId}${conversationId ? `/c/${conversationId}` : ''}`)}
            >
              Continuar con Google
            </button>
          </div>
        </div>
      </div>
    )
  }

  const disabled = !conversationId || runStatus === 'running'

  return (
    <div className="pulpochat" style={config.theme_vars || {}}>
      {config.custom_css && <style>{config.custom_css}</style>}

      <div className="pc-layout">
        <ChatSidebar
          title={config.title}
          conversations={conversations}
          activeId={conversationId}
          onSelect={id => { navigate(`/chat/${botId}/c/${id}`); setMobileSidebarOpen(false) }}
          onNew={() => { handleNewConversation(); setMobileSidebarOpen(false) }}
          open={mobileSidebarOpen}
        />

        <div className="pc-main">
          <div className="pc-mobile-bar">
            <button onClick={() => setMobileSidebarOpen(o => !o)}>☰ Conversaciones</button>
            <button onClick={() => setMobileBannersOpen(o => !o)}>🖼 Info</button>
          </div>
          <div className="pc-main-header">
            <div className="pc-main-title">{config.title}</div>
          </div>
          <ChatThread messages={messages} runStatus={runStatus} error={sendError} />
          <ChatComposer disabled={disabled} onSend={handleSend} />
        </div>

        <ChatBanners banners={config.banners} open={mobileBannersOpen} />
      </div>
    </div>
  )
}
