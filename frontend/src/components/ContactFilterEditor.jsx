/**
 * ContactFilterEditor — editor unificado de filtro de contactos.
 *
 * Orden de la lista:
 *   1. Con estado explícito (excluido/incluido) — siempre visible
 *   2. Con actividad (has_messages) sin estado — siempre visible
 *   3. Sin actividad y sin estado — colapsado por defecto
 *
 * Props:
 *   value     — { include_all_known, include_unknown, included[], excluded[] }
 *   onChange  — (newValue) => void
 *   contacts  — [{ id, name, channels, ... }]  (contactos registrados en DB)
 *   suggested — [{ name, phone, has_messages }] (vistos en conversaciones)
 */
import { useState, useCallback } from 'react'

export const DEFAULT_FILTER = {
  include_all_known: false,
  include_unknown: false,
  included: [],
  excluded: [],
}

const T = {
  section: {
    fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
    color: '#475569', padding: '8px 0 4px', display: 'block',
  },
  row: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '4px 0', borderBottom: '1px solid rgba(15,23,42,0.8)',
  },
  name: {
    flex: 1, fontSize: 12, color: '#cbd5e1',
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  check: { flexShrink: 0, width: 13, height: 13, cursor: 'pointer' },
  lbl: { fontSize: 11, color: '#94a3b8', cursor: 'pointer', margin: 0 },
}

function badge(state) {
  const base = { fontSize: 10, padding: '2px 6px', borderRadius: 4, cursor: 'pointer', fontWeight: 500, flexShrink: 0 }
  if (state === 'excluded') return { ...base, background: 'rgba(220,38,38,.15)', color: '#f87171', border: '1px solid rgba(220,38,38,.3)' }
  if (state === 'included') return { ...base, background: 'rgba(34,197,94,.15)', color: '#4ade80', border: '1px solid rgba(34,197,94,.3)' }
  if (state === 'excl-btn') return { ...base, fontWeight: 400, background: 'transparent', color: '#ef4444', border: '1px solid rgba(239,68,68,.25)' }
  if (state === 'incl-btn') return { ...base, fontWeight: 400, background: 'transparent', color: '#22c55e', border: '1px solid rgba(34,197,94,.25)' }
  return { ...base, fontWeight: 400, background: 'transparent', color: '#475569', border: '1px solid #1e293b' }
}

export default function ContactFilterEditor({
  value = DEFAULT_FILTER,
  onChange,
  contacts = [],
  suggested = [],
  onBootstrap,   // (contactName) => Promise — importar historial WA
}) {
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [manualInput, setManualInput] = useState('')
  const [bootstrapping, setBootstrapping] = useState({})

  function addManual() {
    const v = manualInput.trim()
    if (!v) return
    include(v)
    setManualInput('')
  }
  const cf = { ...DEFAULT_FILTER, ...value }

  function getState(name) {
    if ((cf.excluded || []).includes(name)) return 'excluded'
    if ((cf.included || []).includes(name)) return 'included'
    return 'neutral'
  }

  function exclude(name) {
    onChange({
      ...cf,
      excluded: [...new Set([...(cf.excluded || []), name])],
      included: (cf.included || []).filter(x => x !== name),
    })
  }

  function include(name) {
    onChange({
      ...cf,
      included: [...new Set([...(cf.included || []), name])],
      excluded: (cf.excluded || []).filter(x => x !== name),
    })
  }

  function clearState(name) {
    onChange({
      ...cf,
      included: (cf.included || []).filter(x => x !== name),
      excluded: (cf.excluded || []).filter(x => x !== name),
    })
  }

  // Construir lista unificada
  const allItems = [
    ...contacts.map(c => ({ key: c.name, name: c.name, sub: null, active: true, isContact: true })),
    ...suggested.map(s => {
      const name = s.name || s.phone
      return { key: name, name, sub: null, active: !!s.has_messages, isContact: false }
    }),
  ]

  // Deduplicar (puede que un sugerido ya esté como contacto)
  const seen = new Set()
  const deduped = allItems.filter(item => {
    if (seen.has(item.key)) return false
    seen.add(item.key)
    return true
  })

  // Agregar orphans (guardados en filtro pero no en listas actuales)
  const allKeys = new Set(deduped.map(i => i.key))
  const orphanIncluded = (cf.included || []).filter(p => !allKeys.has(p))
  const orphanExcluded = (cf.excluded || []).filter(p => !allKeys.has(p))

  const q = search.toLowerCase()
  const filtered = deduped.filter(i => !q || i.name.toLowerCase().includes(q))

  // Grupos
  const withState   = filtered.filter(i => getState(i.name) !== 'neutral')
  const activeNoState = filtered.filter(i => getState(i.name) === 'neutral' && i.active)
  const inactiveNoState = filtered.filter(i => getState(i.name) === 'neutral' && !i.active)

  const orphans = [...orphanIncluded, ...orphanExcluded].filter(p => !q || p.toLowerCase().includes(q))

  const isEmpty = !cf.include_all_known && !cf.include_unknown
    && !(cf.included || []).length && !(cf.excluded || []).length

  async function handleBootstrap(name) {
    if (!onBootstrap || bootstrapping[name]) return
    setBootstrapping(b => ({ ...b, [name]: true }))
    try { await onBootstrap(name) } finally {
      setBootstrapping(b => ({ ...b, [name]: false }))
    }
  }

  function Row({ name, sub, isRegistered = true }) {
    const state = getState(name)
    const isOrphan = !isRegistered && state === 'included'
    return (
      <div style={T.row}>
        <span style={T.name} title={name}>
          {name}
          {sub && <span style={{ fontSize: 10, color: '#64748b', marginLeft: 4 }}>{sub}</span>}
        </span>
        {isOrphan && onBootstrap && (
          <span
            style={{ ...badge('neutral'), fontSize: 10, color: '#38bdf8', border: '1px solid rgba(56,189,248,.3)', cursor: bootstrapping[name] ? 'default' : 'pointer', opacity: bootstrapping[name] ? 0.5 : 1 }}
            onClick={() => handleBootstrap(name)}
            title="Importar historial de WhatsApp"
          >
            {bootstrapping[name] ? '...' : '↓ historial'}
          </span>
        )}
        {state !== 'neutral' ? (
          <span style={badge(state)} onClick={() => clearState(name)} title="Click para quitar">
            {state === 'excluded' ? 'Excluido ✕' : 'Incluido ✕'}
          </span>
        ) : (
          <>
            <span style={badge('incl-btn')} onClick={() => include(name)}>+</span>
            <span style={badge('excl-btn')} onClick={() => exclude(name)}>Excl</span>
          </>
        )}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>

      {/* Agregar número manual */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
        <input
          placeholder="Agregar número o nombre..."
          value={manualInput}
          onChange={e => setManualInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addManual()}
          style={{
            flex: 1, fontSize: 11, padding: '5px 8px',
            background: '#0f172a', border: '1px solid #1e293b',
            borderRadius: 4, color: '#cbd5e1', boxSizing: 'border-box',
          }}
        />
        <button
          onClick={addManual}
          disabled={!manualInput.trim()}
          style={{
            fontSize: 11, padding: '4px 10px', borderRadius: 4, cursor: 'pointer',
            background: manualInput.trim() ? 'rgba(34,197,94,.15)' : 'transparent',
            border: '1px solid rgba(34,197,94,.3)', color: '#4ade80',
            opacity: manualInput.trim() ? 1 : 0.4,
          }}
        >
          + Incluir
        </button>
      </div>

      {/* Toggles globales */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 8, flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
          <input type="checkbox" style={T.check} checked={!!cf.include_all_known}
            onChange={e => onChange({ ...cf, include_all_known: e.target.checked })} />
          <span style={T.lbl}>Todos los conocidos</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
          <input type="checkbox" style={T.check} checked={!!cf.include_unknown}
            onChange={e => onChange({ ...cf, include_unknown: e.target.checked })} />
          <span style={T.lbl}>Desconocidos</span>
        </label>
      </div>

      {/* Buscador */}
      {deduped.length > 6 && (
        <input
          placeholder="Buscar..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            fontSize: 11, padding: '4px 8px', marginBottom: 4,
            background: '#0f172a', border: '1px solid #1e293b',
            borderRadius: 4, color: '#cbd5e1', width: '100%', boxSizing: 'border-box',
          }}
        />
      )}

      {/* Grupo 1: con estado definido */}
      {(withState.length > 0 || orphans.length > 0) && (
        <>
          <span style={T.section}>CON ESTADO ({withState.length + orphans.length})</span>
          {withState.map(i => <Row key={i.key} name={i.name} sub={i.sub} />)}
          {orphans.map(p => <Row key={p} name={p} isRegistered={false} />)}
        </>
      )}

      {/* Grupo 2: activos sin estado */}
      {activeNoState.length > 0 && (
        <>
          <span style={T.section}>ACTIVOS ({activeNoState.length})</span>
          {activeNoState.map(i => <Row key={i.key} name={i.name} sub={i.sub} />)}
        </>
      )}

      {/* Grupo 3: sin actividad — colapsado */}
      {inactiveNoState.length > 0 && (
        <>
          <button
            onClick={() => setShowInactive(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4, marginTop: 6,
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '4px 0', width: '100%',
            }}
          >
            <span style={{ ...T.section, padding: 0, margin: 0 }}>
              {showInactive ? '▾' : '▸'} SIN ACTIVIDAD ({inactiveNoState.length})
            </span>
          </button>
          {showInactive && inactiveNoState.map(i => <Row key={i.key} name={i.name} sub={i.sub} />)}
        </>
      )}

      {isEmpty && (
        <div style={{
          marginTop: 6, fontSize: 10, color: '#ef4444',
          background: 'rgba(239,68,68,.08)', borderRadius: 4, padding: '4px 6px',
        }}>
          ⚠ Sin filtro activo — el flow no responderá a nadie
        </div>
      )}
    </div>
  )
}
