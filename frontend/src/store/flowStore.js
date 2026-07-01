import { createStore, useStore } from 'zustand'
import { applyNodeChanges, applyEdgeChanges, addEdge } from '@xyflow/react'
import { createContext, useContext } from 'react'

export const FlowStoreContext = createContext(null)

export function useFlowStore(selector) {
  const store = useContext(FlowStoreContext)
  if (!store) throw new Error('useFlowStore fuera de FlowStoreContext.Provider')
  return useStore(store, selector)
}

// Tipos de nodo disponibles en la paleta (los que el usuario puede arrastrar).
// El orden importa: así aparecen en la paleta.
export const PALETTE_TYPES = [
  'whatsapp_trigger',
  'telegram_trigger',
  'api_trigger',
  'message_join',
  'gate',
  'router',
  'llm',
  'send_message',
  'vector_search',
  'fetch',
  'transcribe_audio',
  'save_attachment',
  'summarize',
  'set_state',
  'save_contact',
  'check_contact',
  'fetch_sheet',
  'search_sheet',
  'gsheet',
]
// Nota: luganense_flow eliminado — era un mega-nodo legacy, reemplazado por nodos individuales

// Config por defecto al crear un nodo nuevo desde la paleta
const DEFAULT_CONFIGS = {
  message_trigger:   { connection_id: '', contact_phone: '', message_pattern: '' },
  whatsapp_trigger:  { connection_id: '', contact_filter: { include_all_known: false, include_unknown: false, included: [], excluded: [] }, message_pattern: '', cooldown_hours: 4 },
  telegram_trigger:  { connection_id: '', contact_filter: { include_all_known: false, include_unknown: false, included: [], excluded: [] }, message_pattern: '', cooldown_hours: 4 },
  api_trigger:       {},
  message_join:      {},
  gate:              {},
  router:          { prompt: '', routes: [], fallback: '', model: 'best:instruction|local-first' },
  llm:             { prompt: '', model: 'best:instruction|local-first', temperature: 0.3, output: 'reply' },
  send_message:    { to: '', message: '' },
  vector_search:   { collection: '' },
  fetch:           { source: '' },
  transcribe_audio: {},
  save_attachment:  { delete_audio_after_transcription: false },
  summarize:        {},
  set_state:        { field: '', value: '' },
  save_contact:    { name_field: 'contact_name', phone_field: 'contact_phone', notes_field: 'contact_notes', update_if_exists: true },
  check_contact:   { route_known: 'conocido', route_unknown: 'desconocido' },
}

/**
 * Convierte el ID de un nodo en un label legible.
 * "expandir_consulta"  → "Expandir consulta"
 * "node_1234567890"    → null (fallback al label del tipo)
 * "message_trigger_1"  → null (sufijo numérico → fallback)
 * "__end__"            → null (nodo interno → fallback)
 * "main_node"          → null (nombre genérico → fallback)
 */
function humanizeId(id) {
  if (/^node_\d+$/.test(id)) return null   // auto-generado
  if (/^__/.test(id)) return null           // interno LangGraph
  if (/_\d+$/.test(id)) return null         // sufijo numérico (message_trigger_1)
  if (id === 'main_node') return null        // genérico
  return id.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())
}

/**
 * Convierte un nodo del formato DB al formato React Flow.
 *
 * DB:  { id, type: "reply", position, config }
 * RF:  { id, type: "flowNode", position, data: { nodeType: "reply", config, label?, color? } }
 *
 * `typeMap` es el resultado del endpoint /api/flow/node-types: { [id]: { label, color, description } }
 */
export function dbNodeToRF(node, typeMap = {}) {
  const meta = typeMap[node.type] || typeMap['generic'] || {}
  // Mezclar defaults: los valores guardados en DB tienen prioridad, pero los
  // campos faltantes toman el default de DEFAULT_CONFIGS. Esto evita que campos
  // nuevos (ej: cooldown_hours) queden undefined en flows creados antes de que
  // el campo existiera, causando que el backend los ignore (trata undefined como 0).
  const defaultConfig = DEFAULT_CONFIGS[node.type] || {}
  return {
    id: node.id,
    type: 'flowNode',
    position: node.position || { x: 0, y: 0 },
    width: 160,
    height: 40,
    data: {
      nodeType:    node.type,
      config:      { ...defaultConfig, ...(node.config || {}) },
      label:       node.label || humanizeId(node.id) || meta.label || node.type,
      color:       meta.color       || '#1e293b',
      description: meta.description || '',
    },
  }
}

/**
 * Convierte el estado del store al formato definition que va a la DB.
 */
function nodesToDefinition(rfNodes, rfEdges) {
  return {
    nodes: rfNodes.map(n => ({
      id:       n.id,
      type:     n.data.nodeType,
      position: n.position,
      config:   n.data.config || {},
      label:    n.data.label || undefined,
    })),
    edges: rfEdges.map(e => ({
      id:     e.id,
      source: e.source,
      target: e.target,
      label:  e.label || null,
    })),
    viewport: { x: 0, y: 0, zoom: 1 },
  }
}

/**
 * Para cada nodo router, asigna la primera ruta sin usar a las edges
 * salientes que no tienen label. No modifica edges que ya tienen label.
 */
function autoAssignRouterLabels(rfNodes, rfEdges) {
  const routerNodes = rfNodes.filter(n => n.data?.nodeType === 'router')
  if (!routerNodes.length) return rfEdges

  const edgeUpdates = new Map() // edgeId → label
  for (const router of routerNodes) {
    const routes = router.data.config?.routes || []
    if (!routes.length) continue
    const outEdges = rfEdges.filter(e => e.source === router.id)
    const usedLabels = new Set(outEdges.filter(e => e.label).map(e => e.label))
    let available = routes.filter(r => !usedLabels.has(r))
    for (const edge of outEdges) {
      if (edge.label || !available.length) continue
      edgeUpdates.set(edge.id, available.shift())
    }
  }

  if (!edgeUpdates.size) return rfEdges
  return rfEdges.map(e => edgeUpdates.has(e.id) ? { ...e, label: edgeUpdates.get(e.id) } : e)
}

export function createFlowStore() {
  return createStore((set, get) => {
    function pushToHistory() {
      const { nodes, edges, _history } = get()
      const snapshot = {
        nodes: nodes.map(n => ({ ...n, data: { ...n.data } })),
        edges: edges.map(e => ({ ...e })),
      }
      const next = [..._history, snapshot]
      if (next.length > 50) next.shift()
      set({ _history: next })
    }

    return {
    nodes: [],
    edges: [],
    selectedNodeId: null,
    isDirty: false,
    typeMap: {},  // { [type_id]: { label, color, description } }
    _history: [],
    _version: 0,

    setTypeMap: (typeMap) => set({ typeMap }),

    loadFlow: (definition, typeMap) => {
      const tm = typeMap || get().typeMap
      const rfNodes = (definition?.nodes || []).map(n => dbNodeToRF(n, tm))
      const rfEdges = (definition?.edges || []).map(e => ({ ...e }))
      // Reparar edges sin label salientes de nodos router
      const repairedEdges = autoAssignRouterLabels(rfNodes, rfEdges)
      set({
        nodes: rfNodes,
        edges: repairedEdges,
        selectedNodeId: null,
        isDirty: false,
        _history: [],
        _version: 0,
      })
    },

    setSelectedNodeId: (id) => set({ selectedNodeId: id }),

    updateNodeConfig: (nodeId, config) => set(state => ({
      nodes: state.nodes.map(n =>
        n.id === nodeId ? { ...n, data: { ...n.data, config } } : n
      ),
      isDirty: true,
      _version: state._version + 1,
    })),

    updateNodeLabel: (nodeId, label) => set(state => ({
      nodes: state.nodes.map(n =>
        n.id === nodeId ? { ...n, data: { ...n.data, label } } : n
      ),
      isDirty: true,
      _version: state._version + 1,
    })),

    onNodesChange: (changes) => set(state => ({
      nodes: applyNodeChanges(changes, state.nodes),
      isDirty: true,
      _version: state._version + 1,
    })),

    onEdgesChange: (changes) => {
      const hasRemove = changes.some(c => c.type === 'remove')
      if (hasRemove) pushToHistory()
      set(state => ({
        edges: applyEdgeChanges(changes, state.edges),
        isDirty: true,
        _version: state._version + 1,
      }))
    },

    onConnect: (connection) => {
      pushToHistory()
      set(state => {
        const sourceNode = state.nodes.find(n => n.id === connection.source)
        let label
        if (sourceNode?.data?.nodeType === 'router') {
          const routes = sourceNode.data.config?.routes || []
          const usedLabels = new Set(
            state.edges.filter(e => e.source === connection.source && e.label).map(e => e.label)
          )
          label = routes.find(r => !usedLabels.has(r))
        }
        return {
          edges: addEdge({ ...connection, id: `e-${Date.now()}`, ...(label ? { label } : {}) }, state.edges),
          isDirty: true,
          _version: state._version + 1,
        }
      })
    },

    addNode: (nodeType, position) => {
      pushToHistory()
      const { typeMap } = get()
      const meta = typeMap[nodeType] || typeMap['generic'] || {}
      const id = `node_${Date.now()}`
      const newNode = {
        id,
        type: 'flowNode',
        position,
        width: 160,
        height: 40,
        data: {
          nodeType,
          config:      DEFAULT_CONFIGS[nodeType] || {},
          label:       meta.label       || nodeType,
          color:       meta.color       || '#1e293b',
          description: meta.description || '',
        },
      }
      set(state => ({
        nodes: [...state.nodes, newNode],
        isDirty: true,
        _version: state._version + 1,
      }))
      return id
    },

    deleteNode: (nodeId) => {
      pushToHistory()
      set(state => ({
        nodes: state.nodes.filter(n => n.id !== nodeId),
        edges: state.edges.filter(e => e.source !== nodeId && e.target !== nodeId),
        selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
        isDirty: true,
        _version: state._version + 1,
      }))
    },

    undo: () => {
      const { _history } = get()
      if (!_history.length) return
      const prev = _history[_history.length - 1]
      set(state => ({
        nodes: prev.nodes,
        edges: prev.edges,
        _history: state._history.slice(0, -1),
        isDirty: true,
        _version: state._version + 1,
      }))
    },

    markClean: () => set({ isDirty: false }),

    reset: () => set({ nodes: [], edges: [], selectedNodeId: null, isDirty: false, _history: [], _version: 0 }),

    getDefinition: () => nodesToDefinition(get().nodes, get().edges),
    }
  })
}
