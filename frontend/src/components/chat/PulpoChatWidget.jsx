/**
 * PulpoChatWidget — el chat en sí (config pública, directorio + historial,
 * thread, composer, banners, polling). Compartido entre:
 *   - ChatPage.jsx     (standalone, fullscreen, URL sincroniza conversationId)
 *   - ChatsTab.jsx      (embebido dentro de la card del bot, sin tocar la URL)
 *
 * 2026-07-23: extraído de ChatPage.jsx al pasar Chats de "1 config por bot"
 * a lista -- antes esta UI solo existía standalone. El manejo de
 * conversationId es interno (useState); si el caller quiere reflejarlo en
 * la URL (uso standalone), pasa `initialConversationId` +
 * `onConversationChange`. En uso embebido ninguno de los dos hace falta.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { chatApi } from '../../lib/chatApi.js'
import ChatThread from './ChatThread.jsx'
import ChatComposer from './ChatComposer.jsx'
import ChatBanners from './ChatBanners.jsx'
import ChatDirectory from './ChatDirectory.jsx'
import InfoBanner from './InfoBanner.jsx'
import './chat.css'

const POLL_MS = 2000

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

export default function PulpoChatWidget({
  botId,
  chatId,
  initialConversationId = null,
  onConversationChange,
  fullscreen = true,
}) {
  const [conversationId, setConversationIdState] = useState(initialConversationId)
  const [config, setConfig] = useState(null)
  const [configError, setConfigError] = useState('')
  const [needsLogin, setNeedsLogin] = useState(false)
  const [conversations, setConversations] = useState([])
  const [messages, setMessages] = useState([])
  const [runStatus, setRunStatus] = useState(null)
  const [sendError, setSendError] = useState('')
  // En compacto (≤1180px, ver chat.css) directorio y publicidad son
  // mutuamente excluyentes -- pedido explícito 2026-08-11 ("si se muestra
  // la der, se esconde la izq, y al revés"): un solo panel lateral abierto
  // a la vez, nunca los dos. Default 'ads' (publicidad, como antes de hoy);
  // terminar una acción del directorio (elegir conversación, etc.) vuelve
  // a 'ads' en vez de simplemente cerrar. En desktop (>1180px) este estado
  // no importa -- ahí ambos rails siempre se ven completos sin importar
  // openPanel (ver chat.css).
  const [openPanel, setOpenPanel] = useState('ads')
  const mobileDirOpen = openPanel === 'dir'

  const lastIdRef = useRef(0)
  const pollRef = useRef(null)

  // El caller (ChatPage) puede controlar conversationId vía la URL --
  // sincronizamos cuando cambia desde afuera (navegación externa).
  useEffect(() => {
    if (initialConversationId !== conversationId) setConversationIdState(initialConversationId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialConversationId])

  function setConversationId(id) {
    setConversationIdState(id)
    onConversationChange?.(id)
  }

  // ── Config pública ──
  useEffect(() => {
    let cancelled = false
    chatApi.getConfig(botId, chatId).then(res => {
      if (cancelled) return
      if (res._status === 404) { setConfigError('Este chat no existe.'); return }
      if (!res._ok) { setConfigError('No se pudo cargar la configuración del chat.'); return }
      setConfig(res)
      if (fullscreen) document.title = res.title || 'PulpoChat'
    })
    return () => { cancelled = true }
  }, [botId, chatId, fullscreen])

  // ── Conversaciones propias (dispara login_required si hace falta) ──
  const loadConversations = useCallback(async () => {
    const res = await chatApi.listConversations(botId, chatId)
    if (res._status === 401) { setNeedsLogin(true); return null }
    if (!res._ok) return null
    setNeedsLogin(false)
    setConversations(Array.isArray(res) ? res : [])
    return res
  }, [botId, chatId])

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
        setConversationId(list[0].id)
      } else {
        const created = await chatApi.createConversation(botId, chatId)
        if (!cancelled && created._ok) setConversationId(created.id)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config, needsLogin, conversationId, botId, chatId, loadConversations])

  // ── Polling de mensajes de la conversación activa ──
  useEffect(() => {
    if (!conversationId || needsLogin) return
    lastIdRef.current = 0
    setMessages([])
    setRunStatus(null)

    let cancelled = false
    async function poll() {
      const res = await chatApi.getMessages(botId, chatId, conversationId, lastIdRef.current || undefined)
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
  }, [botId, chatId, conversationId, needsLogin])

  async function handleSend(text) {
    setSendError('')
    const res = await chatApi.sendMessage(botId, chatId, conversationId, text)
    if (!res._ok) { setSendError(res.error || 'No se pudo enviar el mensaje'); return }
    setRunStatus('running')
    // Empuja un poll inmediato en vez de esperar el próximo intervalo.
    chatApi.getMessages(botId, chatId, conversationId, lastIdRef.current || undefined).then(r => {
      if (r._ok && r.messages?.length) {
        setMessages(prev => [...prev, ...r.messages])
        lastIdRef.current = r.messages[r.messages.length - 1].id
      }
      if (r._ok) setRunStatus(r.run_status ?? null)
    })
  }

  function handleNewConversation() {
    chatApi.createConversation(botId, chatId).then(res => {
      if (res._ok) setConversationId(res.id)
    })
  }

  const wrapperClass = fullscreen ? 'pulpochat pulpochat--fullscreen' : 'pulpochat pulpochat--embedded'

  // Branding "fácil" (chat_configs.branding, ver ChatForm) mapeado a los
  // mismos --pc-* que ya existen en chat.css -- theme_vars (el escape hatch
  // avanzado) se aplica DESPUÉS, así siempre puede pisar un campo puntual.
  const branding = config?.branding || {}
  const brandingVars = {}
  if (branding.bgColor) brandingVars['--pc-bg'] = branding.bgColor
  if (branding.bgImageUrl) brandingVars['--pc-bg-image'] = `url(${branding.bgImageUrl})`
  if (branding.textColor) brandingVars['--pc-text'] = branding.textColor
  if (branding.accentColor) {
    brandingVars['--pc-accent'] = branding.accentColor
    brandingVars['--pc-accent-bright'] = branding.accentColor
  }
  if (branding.fontFamily) brandingVars['fontFamily'] = branding.fontFamily
  const themedStyle = { ...brandingVars, ...(config?.theme_vars || {}) }

  if (configError) {
    return <div className={wrapperClass}><div className="pc-fullscreen-msg">{configError}</div></div>
  }

  if (!config) {
    return <div className={wrapperClass}><div className="pc-fullscreen-msg">Cargando...</div></div>
  }

  if (!config.enabled) {
    return <div className={wrapperClass}><div className="pc-fullscreen-msg">Este chat está deshabilitado por el momento.</div></div>
  }

  if (needsLogin) {
    const callbackUrl = `/chat/${botId}/${chatId}${conversationId ? `/c/${conversationId}` : ''}`
    return (
      <div className={wrapperClass} style={themedStyle}>
        {config.custom_css && <style>{config.custom_css}</style>}
        <div className="pc-login-screen">
          <div className="pc-login-box">
            {branding.headerBannerUrl
              ? <img className="pc-login-banner" src={branding.headerBannerUrl} alt="" />
              : branding.logoUrl && <img className="pc-login-logo" src={branding.logoUrl} alt="" />}
            <h1>{config.title}</h1>
            <p>Necesitás iniciar sesión para chatear.</p>
            <button className="pc-login-btn" onClick={() => loginWithGoogle(callbackUrl)}>
              Continuar con Google
            </button>
          </div>
        </div>
      </div>
    )
  }

  const disabled = !conversationId || runStatus === 'running'
  // El cliente elige UNA de las dos: banner ancho (como una portada de
  // Facebook) o logo chico + título en texto -- ver ChatForm, "headerMode".
  // Si carga banner, gana -- header sin texto, la identidad va en la imagen.
  const hasHeaderBanner = Boolean(branding.headerBannerUrl)

  return (
    <div className={wrapperClass} style={themedStyle}>
      {config.custom_css && <style>{config.custom_css}</style>}

      <div className="pc-layout">
        <div className={`pc-header ${hasHeaderBanner ? 'pc-header--banner' : ''}`}>
          {hasHeaderBanner && (
            <img
              className="pc-header-banner-img"
              src={branding.headerBannerUrl}
              alt={config.title || ''}
              style={{
                objectPosition: `center ${Number.isFinite(branding.headerBannerPosition) ? branding.headerBannerPosition : 50}%`,
                '--pc-header-zoom': Number.isFinite(branding.headerBannerZoom) ? branding.headerBannerZoom : 1,
              }}
            />
          )}
          <div className="pc-header-id">
            {!hasHeaderBanner && branding.logoUrl && <img className="pc-header-logo" src={branding.logoUrl} alt="" />}
            <span className="pc-header-title">{config.title}</span>
          </div>
        </div>

        <InfoBanner infoBanner={config.info_banner} />

        <div className={`pc-body ${mobileDirOpen ? 'pc-body--dir-open' : ''}`}>
          <ChatDirectory
            botId={botId}
            chatId={chatId}
            directory={config.directory}
            open={mobileDirOpen}
            onToggle={() => setOpenPanel(p => p === 'dir' ? 'ads' : 'dir')}
            conversations={conversations}
            activeConversationId={conversationId}
            onSelectConversation={id => { setConversationId(id); setOpenPanel('ads') }}
            onNewConversation={() => { handleNewConversation(); setOpenPanel('ads') }}
          />

          <div className="pc-main">
            <ChatThread messages={messages} runStatus={runStatus} error={sendError} />
            <ChatComposer disabled={disabled} onSend={handleSend} />
          </div>

          <ChatBanners
            ads={config.ads}
            banners={config.banners}
            open={openPanel === 'ads'}
            onToggle={() => setOpenPanel(p => p === 'ads' ? 'dir' : 'ads')}
          />
        </div>
      </div>
    </div>
  )
}
