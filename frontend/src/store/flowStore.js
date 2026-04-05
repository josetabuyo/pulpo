import { create } from 'zustand'
import { applyNodeChanges, applyEdgeChanges, addEdge } from '@xyflow/react'

// Tipos de nodo disponibles en la paleta (los que el usuario puede arrastrar).
// El orden importa: así aparecen en la paleta.
export const PALETTE_TYPES = ['message_trigger', 'reply', 'llm_respond', 'summarize', 'luganense_flow']

// Config por defecto al crear un nodo nuevo desde la paleta
const DEFAULT_CONFIGS = {
  message_trigger: { connection_id: '', contact_phone: '', message_pattern: '' },
  reply:          { message: '' },
  llm_respond:    { prompt: '' },
  summarize:      {},
  luganense_flow: {},
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
  return {
    id: node.id,
    type: 'flowNode',
    position: node.position || { x: 0, y: 0 },
    width: 160,
    height: 40,
    data: {
      nodeType:    node.type,
      config:      node.config || {},
      label:       meta.label       || node.type,
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

export const useFlowStore = create((set, get) => ({
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
