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
  'message_join',
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
  message_join:      {},
  router:          { prompt: '', routes: [], fallback: '', model: 'llama-3.3-70b-versatile' },
  llm:             { prompt: '', model: 'llama-3.3-70b-versatile', temperature: 0.3, output: 'reply' },
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

export function createFlowStore() {
  return createStore((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  isDirty: false,
  typeMap: {},  // { [type_id]: { label, color, description } }

  setTypeMap: (typeMap) => set({ typeMap }),

  loadFlow: (definition, typeMap) => {
    const tm = typeMap || get().typeMap
    set({
      nodes: (definition?.nodes || []).map(n => dbNodeToRF(n, tm)),
      edges: (definition?.edges || []).map(e => ({ ...e })),
      selectedNodeId: null,
      isDirty: false,
    })
  },

  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

  updateNodeConfig: (nodeId, config) => set(state => ({
    nodes: state.nodes.map(n =>
      n.id === nodeId ? { ...n, data: { ...n.data, config } } : n
    ),
    isDirty: true,
  })),

  updateNodeLabel: (nodeId, label) => set(state => ({
    nodes: state.nodes.map(n =>
      n.id === nodeId ? { ...n, data: { ...n.data, label } } : n
    ),
    isDirty: true,
  })),

  onNodesChange: (changes) => set(state => ({
    nodes: applyNodeChanges(changes, state.nodes),
    isDirty: true,
  })),

  onEdgesChange: (changes) => set(state => ({
    edges: applyEdgeChanges(changes, state.edges),
    isDirty: true,
  })),

  onConnect: (connection) => set(state => ({
    edges: addEdge({ ...connection, id: `e-${Date.now()}` }, state.edges),
    isDirty: true,
  })),

  addNode: (nodeType, position) => {
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
    }))
    return id
  },

  deleteNode: (nodeId) => set(state => ({
    nodes: state.nodes.filter(n => n.id !== nodeId),
    edges: state.edges.filter(e => e.source !== nodeId && e.target !== nodeId),
    selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
    isDirty: true,
  })),

  markClean: () => set({ isDirty: false }),

  reset: () => set({ nodes: [], edges: [], selectedNodeId: null, isDirty: false }),

  getDefinition: () => nodesToDefinition(get().nodes, get().edges),
  }))
}
