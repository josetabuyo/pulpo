/**
 * Fila de una conexión Telegram con menú contextual (desconectar/reconectar/eliminar).
 */
import { useState, useEffect, useRef } from 'react'
import { StatusPill } from './widgets.jsx'

export default function ConnectionRow({ conn, mode, simMode, botId, apiCall, onDelete, onReconnect }) {
  const [localStatus, setLocalStatus] = useState(conn.status)
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0, openUp: false })
  const menuRef = useRef(null)
  const menuBtnRef = useRef(null)

  useEffect(() => {
    if (!menuOpen) return
    function onOutside(e) { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false) }
    document.addEventListener('mousedown', onOutside)
    return () => document.removeEventListener('mousedown', onOutside)
  }, [menuOpen])

  function openMenu() {
    const rect = menuBtnRef.current?.getBoundingClientRect()
    if (!rect) { setMenuOpen(true); return }
    const menuHeight = 120
    const spaceBelow = window.innerHeight - rect.bottom
    const openUp = spaceBelow < menuHeight
    setMenuPos({ top: openUp ? rect.top - 4 : rect.bottom + 4, left: rect.right, openUp })
    setMenuOpen(true)
  }

  useEffect(() => setLocalStatus(conn.status), [conn.status])

  const displayId = conn.username ? `@${conn.username}` : conn.botName || conn.number
  const connected = localStatus === 'ready'

  return (
    <div className="ec-conn-row ec-conn-row--tg"
      draggable={mode === 'admin'}
      onDragStart={mode === 'admin' ? e => {
        e.dataTransfer.setData('type', 'telegram')
        e.dataTransfer.setData('sourceBotId', botId)
        e.dataTransfer.setData('tokenId', conn.number)
        e.currentTarget.classList.add('dragging')
      } : undefined}
      onDragEnd={mode === 'admin' ? e => e.currentTarget.classList.remove('dragging') : undefined}
    >
      <div className="ec-conn-main">
        <span className="ec-chan-badge ec-chan-badge--tg">TG</span>
        <span className="ec-conn-id">{displayId}</span>
        {simMode && <span className="ec-sim-badge">SIM</span>}
        <StatusPill status={localStatus} isTg={true} />
        <div className="ec-conn-actions">
          <div style={{ position: 'relative' }}>
            <button
              ref={menuBtnRef}
              className="btn-ghost btn-sm"
              onClick={() => menuOpen ? setMenuOpen(false) : openMenu()}
              title="Opciones"
              style={{ padding: '4px 8px', fontWeight: 600 }}
            >⋯</button>

            {menuOpen && (
              <div ref={menuRef} style={{
                position: 'fixed',
                top: menuPos.openUp ? undefined : menuPos.top,
                bottom: menuPos.openUp ? window.innerHeight - menuPos.top : undefined,
                left: menuPos.left - 180,
                zIndex: 9999,
                background: '#1e293b', border: '1px solid #334155', borderRadius: 6,
                boxShadow: '0 8px 24px rgba(0,0,0,.6)', minWidth: 190, padding: '4px 0',
              }}>
                {mode === 'admin' && connected && (
                  <button className="conn-menu-item conn-menu-item--danger" onClick={() => { setMenuOpen(false) }}>
                    Desconectar
                  </button>
                )}
                {mode === 'admin' && ['stopped', 'failed', 'disconnected'].includes(localStatus) && !simMode && (
                  <button className="conn-menu-item" onClick={() => { onReconnect?.(conn); setMenuOpen(false) }}>
                    Reconectar
                  </button>
                )}
                {mode === 'admin' && (
                  <>
                    <div style={{ margin: '4px 0', borderTop: '1px solid #334155' }} />
                    <button className="conn-menu-item conn-menu-item--danger" onClick={() => { onDelete?.(conn); setMenuOpen(false) }}>
                      🗑 Eliminar conexión
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
