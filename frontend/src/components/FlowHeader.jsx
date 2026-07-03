/**
 * FlowHeader — barra superior del editor.
 *
 * Muestra: [←] [nombre] [switch activo] [Guardar] [Guardar como]
 * La conexión y el filtro de contactos viven en el NodeConfigPanel del trigger.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useFlowStore } from '../store/flowStore.js'

export default function FlowHeader({ flow, apiCall, onSaved, onSavedAs, onBack }) {
  const [name, setName]   = useState(flow.name || '')
  const [saving, setSaving] = useState(false)
  const [saveErr, setSaveErr] = useState('')
  const [savingAs, setSavingAs] = useState(false)
  const [active, setActive] = useState(!!flow.active)
  const [togglingActive, setTogglingActive] = useState(false)

  const isDirty       = useFlowStore(s => s.isDirty)
  const version       = useFlowStore(s => s._version)
  const getDefinition = useFlowStore(s => s.getDefinition)
  const markClean     = useFlowStore(s => s.markClean)

  useEffect(() => { setActive(!!flow.active) }, [flow.id, flow.active])

  const nameRef = useRef(name)
  useEffect(() => { nameRef.current = name }, [name])

  const autoSaveTimer = useRef(null)

  const handleSave = useCallback(async (nameOverride) => {
    const saveName = (nameOverride ?? nameRef.current).trim()
    if (!saveName) { setSaveErr('El nombre es obligatorio'); return }
    setSaving(true)
    setSaveErr('')
    try {
      const definition = getDefinition()
      await apiCall('PUT', `/flows/bots/${flow.bot_id}/${flow.id}`, {
        name: saveName,
        definition,
      })
      markClean()
      onSaved?.()
    } catch {
      setSaveErr('Error al guardar')
    } finally {
      setSaving(false)
    }
  }, [apiCall, flow.bot_id, flow.id, getDefinition, markClean, onSaved])

  // Auto-save: 2.5 s después del último cambio
  useEffect(() => {
    if (!isDirty) return
    clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => handleSave(), 2500)
    return () => clearTimeout(autoSaveTimer.current)
  }, [version, isDirty])

  const handleToggleActive = useCallback(async () => {
    const next = !active
    setActive(next)          // optimista
    setTogglingActive(true)
    try {
      await apiCall('PUT', `/flows/bots/${flow.bot_id}/${flow.id}`, { active: next })
      onSaved?.()
    } catch {
      setActive(!next)       // revertir si falló
    } finally {
      setTogglingActive(false)
    }
  }, [active, apiCall, flow.bot_id, flow.id, onSaved])

  const handleSaveAs = useCallback(async () => {
    const suggested = `${nameRef.current.trim() || flow.name || 'Flow'} (copia)`
    const newName = (typeof window !== 'undefined' ? window.prompt('Nombre del nuevo flow:', suggested) : suggested)
    if (newName == null) return
    const trimmed = newName.trim()
    if (!trimmed) return

    setSavingAs(true)
    setSaveErr('')
    try {
      const definition = getDefinition()
      const newFlow = await apiCall('POST', `/flows/bots/${flow.bot_id}`, {
        name: trimmed,
        definition,
        connection_id: flow.connection_id,
        contact_phone: flow.contact_phone,
        contact_filter: flow.contact_filter,
      })
      if (newFlow?.id) {
        // El duplicado arranca inactivo — no queremos que responda en paralelo al original.
        await apiCall('PUT', `/flows/bots/${newFlow.bot_id}/${newFlow.id}`, { active: false })
        newFlow.active = false
        onSavedAs?.(newFlow)
      }
    } catch {
      setSaveErr('Error al guardar como')
    } finally {
      setSavingAs(false)
    }
  }, [apiCall, flow.bot_id, flow.connection_id, flow.contact_phone, flow.contact_filter, flow.name, getDefinition, onSavedAs])

  const inputStyle = {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    fontSize: 13,
    padding: '5px 8px',
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '8px 12px',
      background: '#0f172a',
      borderBottom: '1px solid #1e293b',
      flexShrink: 0,
      minWidth: 0,
    }}>
      {/* Volver */}
      <button
        onClick={onBack}
        style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: '0 2px', flexShrink: 0 }}
        title="Volver"
      >←</button>

      {/* Nombre */}
      <input
        type="text"
        autoComplete="off"
        value={name}
        onChange={e => setName(e.target.value)}
        placeholder="Nombre del flow"
        style={{ ...inputStyle, width: 220, flexShrink: 1 }}
      />

      {/* Switch activo/inactivo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        <span style={{ fontSize: 11, color: '#64748b', whiteSpace: 'nowrap' }}>
          {active ? 'Activo' : 'Inactivo'}
        </span>
        <button
          role="switch"
          aria-checked={active}
          title={active ? 'Desactivar flow' : 'Activar flow'}
          onClick={handleToggleActive}
          disabled={togglingActive}
          className={`ec-toggle ec-toggle--green ${active ? 'ec-toggle--on' : 'ec-toggle--off'}`}
        />
      </div>

      {/* Guardar / Guardar como */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto', flexShrink: 0 }}>
        {saveErr && <span style={{ fontSize: 11, color: '#ef4444' }}>{saveErr}</span>}
        {isDirty && !saveErr && <span style={{ fontSize: 11, color: '#f59e0b' }}>Sin guardar</span>}
        <button
          onClick={() => { clearTimeout(autoSaveTimer.current); handleSave() }}
          disabled={saving}
          style={{
            background: isDirty ? '#16a34a' : '#1e293b',
            border: '1px solid ' + (isDirty ? '#16a34a' : '#334155'),
            borderRadius: 6,
            color: isDirty ? '#fff' : '#64748b',
            fontSize: 13,
            padding: '5px 14px',
            cursor: saving ? 'default' : 'pointer',
            fontWeight: isDirty ? 600 : 400,
            transition: 'all 0.15s',
            whiteSpace: 'nowrap',
          }}
        >
          {saving ? 'Guardando...' : 'Guardar'}
        </button>
        <button
          onClick={handleSaveAs}
          disabled={savingAs}
          title="Duplicar este flow con otro nombre"
          style={{
            background: '#1e293b',
            border: '1px solid #334155',
            borderRadius: 6,
            color: '#e2e8f0',
            fontSize: 13,
            padding: '5px 14px',
            cursor: savingAs ? 'default' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {savingAs ? 'Guardando...' : 'Guardar como'}
        </button>
      </div>
    </div>
  )
}
