/**
 * FlowHeader — barra superior del editor.
 *
 * Muestra: [←] [nombre] [switch activo] [Guardar] [Guardar como]
 * La conexión y el filtro de contactos viven en el NodeConfigPanel del trigger.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useOnSelectionChange } from '@xyflow/react'
import { useFlowStore } from '../store/flowStore.js'

export default function FlowHeader({ flow, apiCall, onSaved, onSavedAs, onBack }) {
  const [name, setName]   = useState(flow.name || '')
  const [saving, setSaving] = useState(false)
  const [saveErr, setSaveErr] = useState('')
  const [savingAs, setSavingAs] = useState(false)
  const [active, setActive] = useState(!!flow.active)
  const [togglingActive, setTogglingActive] = useState(false)
  const [selectedNodeIds, setSelectedNodeIds] = useState([])
  const [extracting, setExtracting] = useState(false)
  const [extractMsg, setExtractMsg] = useState('')

  useOnSelectionChange({
    onChange: useCallback(({ nodes }) => {
      setSelectedNodeIds(nodes.map(n => n.id))
    }, []),
  })

  const isDirty       = useFlowStore(s => s.isDirty)
  const version       = useFlowStore(s => s._version)
  const getDefinition = useFlowStore(s => s.getDefinition)
  const markClean     = useFlowStore(s => s.markClean)
  const loadFlow      = useFlowStore(s => s.loadFlow)
  const setMeta       = useFlowStore(s => s.setMeta)
  const canvasNodes   = useFlowStore(s => s.nodes)

  // NodoFlow (flow_kind === 'node_flow'): entry_node_id/output_key viven a
  // nivel raíz de `definition` (ver management/SPEC_NODOFLOW.md) — hasta ahora
  // solo se podían setear por CLI. Mismo patrón de persistencia que el switch
  // "Activo": PUT inmediato al cambiar + reflejar el cambio en el store (vía
  // setMeta) para que un "Guardar" posterior no lo pise con el valor viejo.
  const [entryNodeId, setEntryNodeId] = useState(flow.definition?.entry_node_id || '')
  const [outputKey, setOutputKeyInput] = useState(flow.definition?.output_key || 'reply')
  const [savingNodeFlowMeta, setSavingNodeFlowMeta] = useState(false)

  const [versions, setVersions] = useState(null)   // null = no cargadas aún
  const [versionIndex, setVersionIndex] = useState(-1) // -1 = viendo el flow en vivo
  const [navigating, setNavigating] = useState(false)
  const [autoSaveEnabled, setAutoSaveEnabled] = useState(() => {
    return localStorage.getItem('pulpo:autosave-enabled') !== 'false'
  })

  // Snapshot del estado "en vivo" tomado justo antes de empezar a navegar el
  // historial (primer ◀). `flow.definition` es la foto del fetch inicial al
  // abrir el editor — nunca se refresca — así que usarla para volver a -1
  // tiraba cualquier cambio hecho durante la sesión (auto o manual, incluso
  // ya persistido). liveSnapshotRef guarda el estado real justo antes de
  // navegar, para restaurarlo exacto al volver con ▶.
  const liveSnapshotRef = useRef(null)

  useEffect(() => { setActive(!!flow.active) }, [flow.id, flow.active])
  // Al cambiar de flow, descartar el historial de navegación cargado
  useEffect(() => { setVersions(null); setVersionIndex(-1); liveSnapshotRef.current = null }, [flow.id])
  useEffect(() => {
    setEntryNodeId(flow.definition?.entry_node_id || '')
    setOutputKeyInput(flow.definition?.output_key || 'reply')
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al cambiar de flow (mismo patrón que el efecto de `active` arriba)
  }, [flow.id])

  const nameRef = useRef(name)
  useEffect(() => { nameRef.current = name }, [name])

  const autoSaveTimer = useRef(null)

  // Todo guardado — automático o manual — snapshotea versión. Como el
  // autoguardado solo corre cuando isDirty (hubo cambios reales), auto y
  // manual quedan indistinguibles para el historial: ◀ ▶ navegan por igual
  // sin importar cuál de los dos disparó cada guardado.
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
        save_version: true,
      })
      markClean()
      setVersions(null); setVersionIndex(-1)
      onSaved?.()
    } catch {
      setSaveErr('Error al guardar')
    } finally {
      setSaving(false)
    }
  }, [apiCall, flow.bot_id, flow.id, getDefinition, markClean, onSaved])

  const toggleAutoSave = useCallback(() => {
    setAutoSaveEnabled(prev => {
      const next = !prev
      localStorage.setItem('pulpo:autosave-enabled', String(next))
      return next
    })
  }, [])

  // Auto-save: 2.5 s después del último cambio. No corre si el usuario lo
  // desactivó, ni mientras se está navegando por versiones guardadas (ahí
  // solo un click explícito en "Guardar" debe persistir).
  useEffect(() => {
    if (!isDirty || !autoSaveEnabled || versionIndex !== -1) return
    clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(() => handleSave(), 2500)
    return () => clearTimeout(autoSaveTimer.current)
  }, [version, isDirty, autoSaveEnabled, versionIndex])

  const ensureVersionsLoaded = useCallback(async () => {
    if (versions) return versions
    const list = await apiCall('GET', `/flows/bots/${flow.bot_id}/${flow.id}/versions`)
    setVersions(list)
    return list
  }, [apiCall, flow.bot_id, flow.id, versions])

  const goToIndex = useCallback(async (list, index) => {
    if (index === -1) {
      // Restaurar el snapshot tomado antes de empezar a navegar — no la foto
      // vieja de `flow.definition` (ver comentario en liveSnapshotRef arriba).
      loadFlow(liveSnapshotRef.current ?? flow.definition, undefined, { dirty: true })
      setVersionIndex(-1)
      return
    }
    const target = list[index]
    if (!target) return
    const full = await apiCall('GET', `/flows/bots/${flow.bot_id}/${flow.id}/versions/${target.id}`)
    loadFlow(full.definition, undefined, { dirty: true })
    setVersionIndex(index)
  }, [apiCall, flow.bot_id, flow.id, flow.definition, loadFlow])

  const handleBack = useCallback(async () => {
    setNavigating(true)
    try {
      const list = await ensureVersionsLoaded()
      const nextIndex = Math.min(versionIndex + 1, list.length - 1)
      if (nextIndex === versionIndex) return
      if (versionIndex === -1) liveSnapshotRef.current = getDefinition()
      await goToIndex(list, nextIndex)
    } finally {
      setNavigating(false)
    }
  }, [ensureVersionsLoaded, goToIndex, versionIndex, getDefinition])

  const handleForward = useCallback(async () => {
    setNavigating(true)
    try {
      const list = await ensureVersionsLoaded()
      const nextIndex = versionIndex - 1
      if (nextIndex < -1) return
      await goToIndex(list, nextIndex)
    } finally {
      setNavigating(false)
    }
  }, [ensureVersionsLoaded, goToIndex, versionIndex])

  const canGoBack    = !navigating && (versions === null || versionIndex < versions.length - 1)
  const canGoForward = !navigating && versionIndex > -1

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

  const persistNodeFlowMeta = useCallback(async (patch) => {
    setSavingNodeFlowMeta(true)
    try {
      const definition = { ...getDefinition(), ...patch }
      await apiCall('PUT', `/flows/bots/${flow.bot_id}/${flow.id}`, { definition })
      setMeta(patch)
      onSaved?.()
    } catch {
      // best-effort, igual que el resto de los controles del header — el
      // usuario ve el valor optimista y puede reintentar cambiándolo de nuevo
    } finally {
      setSavingNodeFlowMeta(false)
    }
  }, [apiCall, flow.bot_id, flow.id, getDefinition, setMeta, onSaved])

  const handleEntryNodeChange = useCallback((e) => {
    const value = e.target.value
    setEntryNodeId(value)
    persistNodeFlowMeta({ entry_node_id: value || undefined })
  }, [persistNodeFlowMeta])

  const handleOutputKeyBlur = useCallback(() => {
    const trimmed = outputKey.trim() || 'reply'
    if (trimmed !== outputKey) setOutputKeyInput(trimmed)
    if (trimmed !== (flow.definition?.output_key || 'reply')) {
      persistNodeFlowMeta({ output_key: trimmed })
    }
  }, [outputKey, flow.definition, persistNodeFlowMeta])

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

  // "Convertir selección en NodoFlow" — extrae los nodos seleccionados (2+) a un
  // flow nuevo reutilizable (flow_kind='node_flow'). No toca la selección original
  // (ver SPEC_NODOFLOW.md — fuera de alcance v1 reemplazarla por un nodo nodo_flow).
  const handleExtractNodoFlow = useCallback(async () => {
    const suggested = 'NodoFlow'
    const newName = (typeof window !== 'undefined' ? window.prompt('Nombre del NodoFlow:', suggested) : suggested)
    if (newName == null) return
    const trimmed = newName.trim()
    if (!trimmed) return

    setExtracting(true)
    setExtractMsg('')
    try {
      const created = await apiCall('POST', `/flows/bots/${flow.bot_id}/${flow.id}/extract-node-flow`, {
        node_ids: selectedNodeIds,
        name: trimmed,
      })
      if (created?.id) {
        setExtractMsg(`✓ NodoFlow "${created.name}" creado`)
      } else {
        setExtractMsg('Error al crear el NodoFlow')
      }
    } catch {
      setExtractMsg('Error al crear el NodoFlow')
    } finally {
      setExtracting(false)
      setTimeout(() => setExtractMsg(''), 5000)
    }
  }, [apiCall, flow.bot_id, flow.id, selectedNodeIds])

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

      {/* NodoFlow: entry_node_id / output_key — solo si flow_kind === 'node_flow' */}
      {flow.flow_kind === 'node_flow' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <span style={{ fontSize: 11, color: '#64748b', whiteSpace: 'nowrap' }}>Entrada</span>
          <select
            value={entryNodeId}
            onChange={handleEntryNodeChange}
            disabled={savingNodeFlowMeta}
            title="Nodo de entrada del sub-flow (vacío = se infiere por in-degree 0)"
            style={{ ...inputStyle, width: 150 }}
          >
            <option value="">(auto)</option>
            {canvasNodes.map(n => (
              <option key={n.id} value={n.id}>{n.data?.label || n.id}</option>
            ))}
          </select>
          <span style={{ fontSize: 11, color: '#64748b', whiteSpace: 'nowrap' }}>Output key</span>
          <input
            type="text"
            autoComplete="off"
            value={outputKey}
            onChange={e => setOutputKeyInput(e.target.value)}
            onBlur={handleOutputKeyBlur}
            disabled={savingNodeFlowMeta}
            placeholder="reply"
            title="Clave de state.data del sub-flow que se copia al padre (default: reply)"
            style={{ ...inputStyle, width: 90 }}
          />
        </div>
      )}

      {/* Guardar / Guardar como */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto', flexShrink: 0 }}>
        {extractMsg && (
          <span style={{ fontSize: 11, color: extractMsg.startsWith('✓') ? '#4ade80' : '#ef4444' }}>{extractMsg}</span>
        )}
        {selectedNodeIds.length >= 2 && (
          <button
            onClick={handleExtractNodoFlow}
            disabled={extracting}
            title="Extrae los nodos seleccionados a un NodoFlow reutilizable"
            style={{
              background: '#1e293b',
              border: '1px solid #0e7490',
              borderRadius: 6,
              color: '#22d3ee',
              fontSize: 13,
              padding: '5px 14px',
              cursor: extracting ? 'default' : 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {extracting ? 'Creando...' : `Convertir selección en NodoFlow (${selectedNodeIds.length})`}
          </button>
        )}
        {saveErr && <span style={{ fontSize: 11, color: '#ef4444' }}>{saveErr}</span>}
        {isDirty && !saveErr && <span style={{ fontSize: 11, color: '#f59e0b' }}>Sin guardar</span>}
        <button
          onClick={handleBack}
          disabled={!canGoBack}
          title="Versión anterior"
          style={{
            background: 'none',
            border: '1px solid #334155',
            borderRadius: 6,
            color: canGoBack ? '#e2e8f0' : '#475569',
            fontSize: 13,
            padding: '5px 10px',
            cursor: canGoBack ? 'pointer' : 'default',
          }}
        >◀</button>
        <button
          onClick={handleForward}
          disabled={!canGoForward}
          title="Versión siguiente"
          style={{
            background: 'none',
            border: '1px solid #334155',
            borderRadius: 6,
            color: canGoForward ? '#e2e8f0' : '#475569',
            fontSize: 13,
            padding: '5px 10px',
            cursor: canGoForward ? 'pointer' : 'default',
          }}
        >▶</button>
        <label
          title="Guardar automáticamente 2.5s después de cada cambio"
          style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#64748b', cursor: 'pointer', whiteSpace: 'nowrap' }}
        >
          <input
            type="checkbox"
            checked={autoSaveEnabled}
            onChange={toggleAutoSave}
            style={{ cursor: 'pointer' }}
          />
          Auto
        </label>
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
