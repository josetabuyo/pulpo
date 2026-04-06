/**
 * NodeConfigPanel — panel lateral derecho para configurar el nodo seleccionado.
 *
 * Totalmente dinámico: el schema de cada nodo viene del backend via
 * GET /api/flow/node-types → typeMap[nodeType].schema
 *
 * Agregar un nodo nuevo = solo Python. El panel aparece solo.
 *
 * Tipos de campo soportados: string, textarea, select, float, bool, list.
 * Campos condicionales: show_if: { campo: valor } — se ocultan si no se cumple.
 */
import { useState, useEffect } from 'react'
import { useFlowStore } from '../store/flowStore.js'

// ─── Estilos base ─────────────────────────────────────────────────────────────

const S = {
  label: {
    fontSize: 10,
    color: '#64748b',
    fontWeight: 700,
    letterSpacing: '0.06em',
    marginBottom: 4,
    display: 'block',
  },
  hint: {
    fontSize: 10,
    color: '#475569',
    marginTop: 3,
  },
  input: {
    width: '100%',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 12,
    padding: '6px 9px',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    outline: 'none',
  },
  textarea: {
    width: '100%',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 12,
    padding: '6px 9px',
    resize: 'vertical',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    outline: 'none',
    minHeight: 80,
  },
  select: {
    width: '100%',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 12,
    padding: '6px 9px',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    outline: 'none',
    cursor: 'pointer',
  },
  checkRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  fieldWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
}

// ─── Visibilidad condicional ───────────────────────────────────────────────────

/**
 * show_if viene del backend como { campo: valor }.
 * El campo es visible si TODOS los pares se cumplen en config.
 */
function isVisible(field, config) {
  if (!field.show_if) return true
  return Object.entries(field.show_if).every(([k, v]) => config[k] === v)
}

// ─── Campo JSON editable ───────────────────────────────────────────────────────

function JsonField({ field, value, set, labelEl }) {
  const { hint } = field
  const [raw, setRaw]     = useState(JSON.stringify(value, null, 2))
  const [error, setError] = useState(null)

  // Sync externo → local (cuando el nodo cambia)
  useEffect(() => {
    setRaw(JSON.stringify(value, null, 2))
    setError(null)
  }, [JSON.stringify(value)])

  function handleChange(text) {
    setRaw(text)
    try {
      const parsed = JSON.parse(text)
      setError(null)
      set(parsed)
    } catch {
      setError('JSON inválido')
    }
  }

  return (
    <div style={S.fieldWrap}>
      {labelEl}
      <textarea
        style={{
          ...S.textarea,
          minHeight: 160,
          fontFamily: 'monospace',
          fontSize: 11,
          border: error ? '1px solid #ef4444' : S.textarea.border,
        }}
        value={raw}
        onChange={e => handleChange(e.target.value)}
        spellCheck={false}
      />
      {error && <span style={{ ...S.hint, color: '#ef4444' }}>{error}</span>}
      {!error && hint && <span style={S.hint}>{hint}</span>}
    </div>
  )
}

// ─── Render de un campo ───────────────────────────────────────────────────────

function Field({ field, config, onChange }) {
  const { key, label, type, hint, rows = 4, options = [], required } = field
  const value = config[key] ?? field.default ?? (type === 'bool' ? false : type === 'list' ? [] : type === 'json' ? [] : '')

  function set(val) { onChange({ ...config, [key]: val }) }

  const labelEl = (
    <label style={S.label}>
      {label.toUpperCase()}{required && <span style={{ color: '#ef4444' }}> *</span>}
    </label>
  )

  if (type === 'json') return (
    <JsonField field={field} value={value} set={set} labelEl={labelEl} />
  )

  if (type === 'textarea') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <textarea
        style={S.textarea}
        rows={rows}
        value={value}
        onChange={e => set(e.target.value)}
        placeholder={hint || ''}
      />
    </div>
  )

  if (type === 'select') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <select style={S.select} value={value} onChange={e => set(e.target.value)}>
        {options.map(o => {
          const val = typeof o === 'object' ? o.value : o
          const lbl = typeof o === 'object' ? o.label : o
          return <option key={val} value={val}>{lbl}</option>
        })}
      </select>
    </div>
  )

  if (type === 'float') return (
    <div style={S.fieldWrap}>
      {labelEl}
      <input
        style={S.input}
        type="number"
        step="0.1"
        value={value}
        onChange={e => set(parseFloat(e.target.value) || 0)}
      />
    </div>
  )

  if (type === 'bool') return (
    <div style={S.fieldWrap}>
      <div style={S.checkRow}>
        <input
          id={key}
          type="checkbox"
          checked={!!value}
          onChange={e => set(e.target.checked)}
          style={{ accentColor: '#6b21a8', cursor: 'pointer' }}
        />
        <label htmlFor={key} style={{ ...S.label, margin: 0, cursor: 'pointer', fontSize: 12, color: '#cbd5e1', fontWeight: 400, letterSpacing: 0 }}>
          {label}
        </label>
      </div>
    </div>
  )

  if (type === 'list') {
    const csv = Array.isArray(value) ? value.join(', ') : value
    return (
      <div style={S.fieldWrap}>
        {labelEl}
        <input
          style={S.input}
          type="text"
          value={csv}
          onChange={e => set(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
          placeholder={hint || 'val1, val2, val3'}
        />
        {hint && <span style={S.hint}>{hint}</span>}
      </div>
    )
  }

  // string (default)
  return (
    <div style={S.fieldWrap}>
      {labelEl}
      <input
        style={S.input}
        type="text"
        value={value}
        onChange={e => set(e.target.value)}
        placeholder={hint || ''}
      />
      {hint && <span style={S.hint}>{hint}</span>}
    </div>
  )
}

// ─── Info especial: Sumarizador ────────────────────────────────────────────────

function SummarizeInfo({ empresaId }) {
  const path = `data/summaries/${empresaId || '<empresa_id>'}/`
  const url  = `http://localhost:8000/api/summarizer/${empresaId || ''}`
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.5 }}>
        Acumula cada mensaje entrante en un archivo <code style={{ color: '#94a3b8' }}>.md</code> por contacto.
        No produce reply — es un efecto de lado.
      </div>
      <div style={S.fieldWrap}>
        <span style={S.label}>RUTA DE ARCHIVOS</span>
        <code style={{ fontSize: 11, color: '#7dd3fc', background: '#0f172a', padding: '5px 8px', borderRadius: 5, wordBreak: 'break-all' }}>
          {path}
        </code>
      </div>
      {empresaId && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 12, color: '#818cf8', textDecoration: 'none' }}
        >
          Ver resúmenes acumulados →
        </a>
      )}
    </div>
  )
}

// ─── Formulario principal ──────────────────────────────────────────────────────

function ConfigForm({ node, schema, empresaId }) {
  const updateNodeConfig  = useFlowStore(s => s.updateNodeConfig)
  const deleteNode        = useFlowStore(s => s.deleteNode)
  const setSelectedNodeId = useFlowStore(s => s.setSelectedNodeId)
  const { nodeType, config, label, color } = node.data

  const isFixed = nodeType === 'start' || nodeType === 'end'

  function handleChange(newConfig) { updateNodeConfig(node.id, newConfig) }
  function handleDelete() { if (!isFixed) deleteNode(node.id) }

  const visibleFields = (schema || []).filter(f => isVisible(f, config))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', flex: 1 }}>{label}</span>
        <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>{nodeType}</span>
        <button
          onClick={() => setSelectedNodeId(null)}
          style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 2 }}
          title="Cerrar"
        >×</button>
      </div>

      <div style={{ borderTop: '1px solid #1e293b', paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 12, flex: 1, overflowY: 'auto' }}>

        {nodeType === 'summarize' && <SummarizeInfo empresaId={empresaId} />}

        {visibleFields.map(field => (
          <Field key={field.key} field={field} config={config} onChange={handleChange} />
        ))}

        {nodeType !== 'summarize' && visibleFields.length === 0 && (
          <div style={{ fontSize: 12, color: '#475569' }}>
            Este nodo no tiene configuración adicional.
          </div>
        )}
      </div>

      {!isFixed && (
        <div style={{ marginTop: 'auto', paddingTop: 8 }}>
          <button
            onClick={handleDelete}
            style={{
              width: '100%',
              padding: '6px 12px',
              background: 'transparent',
              border: '1px solid #7f1d1d',
              borderRadius: 6,
              color: '#ef4444',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            Eliminar nodo
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Export ───────────────────────────────────────────────────────────────────

export default function NodeConfigPanel({ empresaId }) {
  const nodes          = useFlowStore(s => s.nodes)
  const typeMap        = useFlowStore(s => s.typeMap)
  const selectedNodeId = useFlowStore(s => s.selectedNodeId)
  const selectedNode   = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null

  if (!selectedNode) {
    return (
      <div style={{
        width: 260,
        background: '#0f172a',
        borderLeft: '1px solid #1e293b',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}>
        <div style={{ fontSize: 12, color: '#334155', textAlign: 'center', padding: 16 }}>
          Doble clic en un nodo para configurarlo
        </div>
      </div>
    )
  }

  const schema = typeMap[selectedNode.data.nodeType]?.schema || []

  return (
    <div style={{
      width: 260,
      background: '#0f172a',
      borderLeft: '1px solid #1e293b',
      padding: 14,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
    }}>
      <ConfigForm
        node={selectedNode}
        schema={schema}
        empresaId={empresaId}
      />
    </div>
  )
}
