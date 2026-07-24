/**
 * BotCard — card de una bot con sus triggers, flows y UIs.
 * Funciona en dos modos: 'admin' (dashboard) y 'bot' (portal del cliente).
 *
 * Las piezas viven en components/bot/:
 *   widgets.jsx        — StatusPill, CopyLinkBtn, dotColor, STATUS_LABELS
 *   TriggersTab.jsx     — tab Triggers (reemplaza a la vieja "Conexiones",
 *                         2026-07-23): lista los nodos trigger de todos los
 *                         flows, con pausar/configurar/simular. La gestión
 *                         de credenciales de canal (Telegram/Wavi/Google) ya
 *                         no vive acá -- cada nodo es dueño de su propia
 *                         config, editable desde el editor de Flow (ver
 *                         "Configurar" en TriggersTab, que abre ese nodo ahí).
 *   BotConfigTab.jsx    — tab Configurar (solo nombre/farewell/ttl del bot)
 */
import { useState, useEffect } from 'react'
import FlowList from './FlowList.jsx'
import UIsList from './UIsList.jsx'
import { STATUS_LABELS, dotColor, CopyLinkBtn } from './bot/widgets.jsx'
import TriggersTab from './bot/TriggersTab.jsx'
import BotConfigTab from './bot/BotConfigTab.jsx'
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

  // Drag & drop (admin only)
  onDragOver, onDragLeave, onDrop,
}) {
  const [activeTab, setActiveTab] = useState('triggers')
  const [paused, setPaused] = useState(false)
  const [pauseLoading, setPauseLoading] = useState(false)
  const [hasSummarizer, setHasSummarizer] = useState(false)
  // Deep-link "Configurar" desde TriggersTab -- abre la tab Flow con el
  // flow/nodo puntual ya seleccionado (ver FlowList.jsx/FlowEditor.jsx).
  const [flowOpenRequest, setFlowOpenRequest] = useState(null)

  function handleConfigureTriggerNode(flowId, nodeId) {
    setFlowOpenRequest({ flowId, nodeId })
    setActiveTab('flow')
  }

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

  // Computed
  const conns = bot.connections ?? []

  const tabs = [
    { id: 'triggers', label: 'Triggers', count: null },
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
              {conns.length === 0 && <span style={{ fontSize: 11, color: 'var(--text-subtle)' }}>Sin canales</span>}
            </div>
            <div className="ec-header-actions">
              {/* Pausa visible en ambos modos */}
              <button
                className="btn-ghost btn-sm"
                onClick={togglePause}
                disabled={pauseLoading}
                title={paused ? 'Bot pausado — click para reanudar' : 'Pausar bot (sin desconectar)'}
                style={paused ? { color: 'var(--warning)', borderColor: 'var(--warning)' } : {}}
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

        {/* ── Triggers (reemplaza a la vieja "Conexiones") ── */}
        {activeTab === 'triggers' && (
          <TriggersTab botId={botId} apiCall={apiCall} onConfigureNode={handleConfigureTriggerNode} />
        )}

        {/* ── UIs ── */}
        {activeTab === 'uis' && (
          <UIsList botId={botId} apiCall={apiCall} />
        )}

        {/* ── Flow ── */}
        {activeTab === 'flow' && (
          <FlowList
            botId={botId} apiCall={apiCall} connections={conns}
            onGoToUIs={() => setActiveTab('uis')}
            openRequest={flowOpenRequest}
            onOpenRequestConsumed={() => setFlowOpenRequest(null)}
          />
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
