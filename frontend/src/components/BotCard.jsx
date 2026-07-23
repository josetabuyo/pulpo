/**
 * BotCard — card de una bot con sus conexiones, flows y UIs.
 * Funciona en dos modos: 'admin' (dashboard) y 'bot' (portal del cliente).
 *
 * Las piezas viven en components/bot/:
 *   widgets.jsx           — StatusPill, CopyLinkBtn, dotColor, STATUS_LABELS
 *   ConnectionRow.jsx     — fila Telegram con menú contextual
 *   WaviConnections.jsx   — listado WhatsApp + picker de sesiones wavi
 *   GoogleConnections.jsx — listado Google Sheets + modal de alta
 *   BotConfigTab.jsx  — tab Configurar (nombre/contraseña)
 */
import { useState, useEffect } from 'react'
import FlowList from './FlowList.jsx'
import UIsList from './UIsList.jsx'
import { STATUS_LABELS, dotColor, CopyLinkBtn } from './bot/widgets.jsx'
import ConnectionRow from './bot/ConnectionRow.jsx'
import BotConfigTab from './bot/BotConfigTab.jsx'
import { GoogleSetupModal, GoogleConnectionsSection } from './bot/GoogleConnections.jsx'
import { WaviConnectionsList, WaviSessionPicker } from './bot/WaviConnections.jsx'
import RunsTab from './bot/RunsTab.jsx'
import BotUsersTab from './bot/BotUsersTab.jsx'
import ChatsTab from './bot/ChatsTab.jsx'

// Normaliza un bot del formato admin (/bots) al formato canónico de BotCard
export function normalizeBot(bot) {
  return {
    id: bot.id,
    name: bot.name,
    connections: [
      ...(bot.telegram ?? []).map(t => ({
        id: `${bot.id}-tg-${t.tokenId}`, type: 'telegram', number: t.tokenId, status: t.status,
        username: t.username || '', botName: t.botName || '', allowMass: t.allowMass ?? false,
      })),
      ...(bot.phones ?? []).map(p => ({
        id: p.sessionId, type: 'wavi', number: p.number, alias: p.alias, status: p.status,
      })),
    ],
  }
}

export default function BotCard({
  mode,         // 'admin' | 'bot'
  bot,          // { id, name, connections: [{id, type, number, status}] }
  apiCall,      // (method, path, body) => Promise — auth-agnostic
  onRefresh,    // callback cuando se produce algún cambio que el padre debe recargar
  onExpand,     // admin only — abre la card en popup fullscreen

  // Admin-only — abren modales en el padre:
  onEditBot, onDeleteBot,
  onAddTelegram,
  onDeleteTelegram, onReconnectTg,
  onReconnectWavi,

  // Drag & drop (admin only)
  onDragOver, onDragLeave, onDrop,
}) {
  const [activeTab, setActiveTab] = useState('connections')
  const [paused, setPaused] = useState(false)
  const [pauseLoading, setPauseLoading] = useState(false)
  const [hasSummarizer, setHasSummarizer] = useState(false)

  const botId = bot.id

  useEffect(() => {
    apiCall('GET', `/bot/${bot.id}/paused`, null)
      .then(r => { if (r?.paused !== undefined) setPaused(r.paused) })
      .catch(e => console.warn('[BotCard] paused', e))
  }, [bot.id])

  useEffect(() => {
    setHasSummarizer(false)
    apiCall('GET', `/flows/bots/${bot.id}/has-node/summarize`, null)
      .then(data => { if (data?.found) setHasSummarizer(true) })
      .catch(e => console.warn('[BotCard] has-node', e))
  }, [bot.id])

  async function togglePause() {
    setPauseLoading(true)
    try {
      const res = await apiCall('PUT', `/bot/${bot.id}/paused`, { paused: !paused })
      if (res?.ok) setPaused(!paused)
    } finally {
      setPauseLoading(false)
    }
  }

  // Bot mode: inline add forms for connections
  const [tgInput, setTgInput] = useState('')
  const [showGoogleModal, setShowGoogleModal] = useState(false)
  const [tgErr, setTgErr] = useState('')
  const [addingConn, setAddingConn] = useState(false)

  // Wavi (WhatsApp) add — admin mode
  const [showWaviPicker, setShowWaviPicker] = useState(false)

  async function handleAddWavi(sessionName) {
    setShowWaviPicker(false)
    await apiCall('POST', '/connections', { botId: botId, number: sessionName }).catch(() => null)
    onRefresh?.()
  }

  async function handleDeleteWavi(number) {
    if (!confirm(`¿Desconectar WhatsApp ${number} de esta bot?`)) return
    await apiCall('DELETE', `/connections/${number}`, null).catch(() => null)
    onRefresh?.()
  }

  async function handleReconnectWavi(number) {
    if (onReconnectWavi) {
      onReconnectWavi(number)  // abre el modal QR en el padre (admin dashboard)
      return
    }
    // fallback directo (sin modal QR)
    await apiCall('POST', `/wavi/sessions/${number}/connect`, null).catch(() => null)
    onRefresh?.()
  }

  async function handleAddTg(e) {
    e.preventDefault(); setTgErr('')
    const token = tgInput.trim(); if (!token) return
    setAddingConn(true)
    const res = await apiCall('POST', `/bot/${botId}/telegram`, { token }).catch(() => null)
    setAddingConn(false)
    if (!res?.ok) { setTgErr(res?.detail || 'Error al agregar'); return }
    if (res.requires_restart) setTgErr('Agregado. Requiere reinicio del servidor para activarse.')
    setTgInput(''); onRefresh?.()
  }

  async function handleToggleMass(conn) {
    await apiCall('PATCH', `/bots/${botId}/telegram/${conn.number}/settings`, { allow_mass: !conn.allowMass }).catch(() => null)
    onRefresh?.()
  }

  async function handleRemoveConn(conn) {
    if (!confirm(`¿Eliminar ${conn.number}?`)) return
    const tokenId = conn.id.split('-tg-')[1]
    await apiCall('DELETE', `/bot/${botId}/telegram/${tokenId}`, null).catch(() => null)
    onRefresh?.()
  }

  // Computed
  const conns = bot.connections ?? []
  const tgConns = conns.filter(c => c.type === 'telegram')
  const waviConns = conns.filter(c => c.type === 'wavi')

  const tabs = [
    { id: 'connections', label: 'Conexiones', count: conns.length },
    ...(hasSummarizer ? [{ id: 'uis', label: 'UIs', count: null }] : []),
    { id: 'flow', label: 'Flow', count: null },
    // GET /api/runs no filtra por bot todavía -- 403 para rol "scoped"
    // (ver proxy.ts::SCOPED_BOT_ROUTES), así que no tiene sentido mostrar
    // este tab en mode="bot" hasta que se porte ese filtro.
    ...(mode === 'admin' ? [{ id: 'runs', label: 'Ejecuciones', count: null }] : []),
    { id: 'config', label: 'Configurar', count: null },
    // Gestión de PulpoChat: acción de PRO o admin dueño del bot (a diferencia
    // de 'users', que sigue admin-only) -- visible en ambos modos, el
    // backend ya lo garantiza vía proxy.ts::SCOPED_BOT_ROUTES.
    { id: 'chats', label: 'Chats', count: null },
    ...(mode === 'admin' ? [{ id: 'users', label: 'Usuarios', count: null }] : []),
  ]

  return (
    <div
      className="ec-card"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {/* ─── Header ─── */}
      <div className="ec-header">
        <div className="ec-header-main">
          <div className="ec-header-info">
            <div className="ec-header-title-row">
              <span className="ec-bot-name">{bot.name}</span>
              <span className="ec-bot-id">{bot.id}</span>
              <CopyLinkBtn botId={bot.id} />
            </div>
          </div>
          <div className="ec-header-right">
            <div className="ec-status-dots">
              {conns.map((c, i) => (
                <span
                  key={i}
                  className="ec-status-dot"
                  style={{ background: dotColor(c.status) }}
                  title={`${c.type === 'wavi' ? 'WA' : 'TG'} ${c.number}: ${STATUS_LABELS[c.status] || c.status}`}
                />
              ))}
              {conns.length === 0 && <span style={{ fontSize: 11, color: '#94a3b8' }}>Sin canales</span>}
            </div>
            <div className="ec-header-actions">
              {/* Pausa visible en ambos modos */}
              <button
                className="btn-ghost btn-sm"
                onClick={togglePause}
                disabled={pauseLoading}
                title={paused ? 'Bot pausado — click para reanudar' : 'Pausar bot (sin desconectar)'}
                style={paused ? { color: '#f59e0b', borderColor: '#f59e0b' } : {}}
              >
                {pauseLoading ? '...' : paused ? '▶ Reanudar' : '⏸ Pausar'}
              </button>
              {mode === 'admin' && (
                <>
                  <button className="btn-ghost btn-sm" onClick={() => onExpand?.(bot)} title="Expandir">⤢</button>
                  <button className="btn-ghost btn-sm" onClick={() => onEditBot?.(bot)}>Editar</button>
                  <button
                    className="btn-danger btn-sm"
                    onClick={() => onDeleteBot?.(bot.id)}
                    title="Eliminar bot (pedirá confirmación)"
                    style={{ padding: '4px 7px', fontSize: 14 }}
                  >🗑</button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ─── Tabs ─── */}
      <div className="ec-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`ec-tab ${activeTab === tab.id ? 'ec-tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.count != null && <span className="ec-tab-badge">{tab.count}</span>}
          </button>
        ))}
      </div>

      {/* ─── Content ─── */}
      <div className="ec-content">

        {/* ── Connections ── */}
        {activeTab === 'connections' && (
          <div>
            {tgConns.length > 0 && (
              <div>
                <div className="ec-section-label ec-section-label--tg">Telegram</div>
                {tgConns.map(conn => (
                  <ConnectionRow
                    key={conn.id} conn={conn} mode={mode}
                    botId={botId} apiCall={apiCall}
                    onDelete={mode === 'admin' ? conn => onDeleteTelegram?.(conn) : conn => handleRemoveConn(conn)}
                    onReconnect={conn => onReconnectTg?.(conn)}
                    onToggleMass={handleToggleMass}
                  />
                ))}
              </div>
            )}

            <WaviConnectionsList conns={waviConns} mode={mode} onDelete={handleDeleteWavi} onReconnect={handleReconnectWavi} />

            {conns.length === 0 && mode === 'bot' && (
              <div className="empty" style={{ padding: '20px 0 8px' }}>Sin canales configurados</div>
            )}

            {/* Google Connections */}
            <GoogleConnectionsSection botId={botId} apiCall={apiCall} mode={mode} hideAddButton={mode === 'admin'} />

            {/* Add row */}
            {mode === 'admin' && (
              <div className="ec-add-row">
                <button className="btn-sm" style={{ background: '#e3f2fd', color: '#0d47a1' }} onClick={() => onAddTelegram?.(botId)}>+ Telegram</button>
                <button className="btn-sm" style={{ background: '#f0fdf4', color: '#15803d' }} onClick={() => setShowWaviPicker(true)}>+ WhatsApp</button>
                <button className="btn-sm" style={{ background: '#f0fdf4', color: '#15803d' }} onClick={() => setShowGoogleModal(true)}>+ Google Sheets</button>
              </div>
            )}

            {showWaviPicker && (
              <WaviSessionPicker
                apiCall={apiCall}
                onAssign={handleAddWavi}
                onClose={() => setShowWaviPicker(false)}
              />
            )}

            {mode === 'bot' && (
              <div className="ec-add-forms">
                <div className="ec-section-label" style={{ background: '#f8fafc', color: '#64748b', borderTop: '1px solid #e8e8f0' }}>Agregar canal</div>
                <div className="ec-add-form-row">
                  <form onSubmit={handleAddTg} style={{ display: 'flex', gap: 8, flex: 1 }}>
                    <input value={tgInput} onChange={e => setTgInput(e.target.value)}
                      placeholder="Token @BotFather (123456:ABC...)" style={{ flex: 1 }} />
                    <button type="submit" className="btn-sm" style={{ background: '#e3f2fd', color: '#0d47a1' }} disabled={addingConn}>+ TG</button>
                  </form>
                  <button
                    type="button"
                    className="btn-sm"
                    style={{ background: '#f0fdf4', color: '#15803d', alignSelf: 'center' }}
                    onClick={() => setShowGoogleModal(true)}
                  >+ Google Sheets</button>
                </div>
                {tgErr && <div style={{ fontSize: 13, color: tgErr.includes('reinicio') ? '#b45309' : '#c00', padding: '4px 20px' }}>{tgErr}</div>}
              </div>
            )}
            {showGoogleModal && (
              <GoogleSetupModal
                botId={botId} apiCall={apiCall}
                onClose={() => setShowGoogleModal(false)}
                onSaved={() => { setShowGoogleModal(false); onRefresh?.() }}
              />
            )}
          </div>
        )}

        {/* ── UIs ── */}
        {activeTab === 'uis' && (
          <UIsList botId={botId} apiCall={apiCall} />
        )}

        {/* ── Flow ── */}
        {activeTab === 'flow' && (
          <FlowList botId={botId} apiCall={apiCall} connections={conns} onGoToUIs={() => setActiveTab('uis')} />
        )}

        {/* ── Ejecuciones ── */}
        {activeTab === 'runs' && (
          <RunsTab botId={botId} apiCall={apiCall} />
        )}

        {/* ── Config ── */}
        {activeTab === 'config' && (
          <BotConfigTab
            botId={botId}
            botName={bot.name}
            apiCall={apiCall}
            onNameChange={() => onRefresh?.()}
          />
        )}

        {/* ── Chats (PulpoChat -- PRO/admin dueño del bot) ── */}
        {activeTab === 'chats' && (
          <ChatsTab botId={botId} apiCall={apiCall} />
        )}

        {/* ── Usuarios (admin-only) ── */}
        {activeTab === 'users' && mode === 'admin' && (
          <BotUsersTab botId={botId} apiCall={apiCall} />
        )}
      </div>

    </div>
  )
}
