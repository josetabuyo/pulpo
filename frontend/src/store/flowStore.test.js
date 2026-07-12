import { describe, it, expect } from 'vitest'
import { createFlowStore } from './flowStore.js'
import { GRID_SIZE } from '../utils/grid.js'

function makeStore(withNode) {
  const store = createFlowStore()
  if (withNode) {
    store.setState({
      nodes: [{
        id: withNode,
        type: 'flowNode',
        position: { x: 0, y: 0 },
        width: 160,
        height: 40,
        data: { nodeType: 'send_message', config: {}, label: 'Enviar mensaje', color: '#1e293b', description: '' },
      }],
    })
  }
  return store
}

describe('flowStore — snapping a la grilla de atractores', () => {
  it('addNode cuantiza la posición recibida a la grilla', () => {
    const store = makeStore()
    const id = store.getState().addNode('send_message', { x: 47, y: 33 })
    const node = store.getState().nodes.find(n => n.id === id)
    expect(node.position).toEqual({ x: 40, y: 40 })
  })

  it('addNode deja intacta una posición ya alineada a la grilla', () => {
    const store = makeStore()
    const id = store.getState().addNode('send_message', { x: 100, y: 200 })
    const node = store.getState().nodes.find(n => n.id === id)
    expect(node.position).toEqual({ x: 100, y: 200 })
  })

  it('duplicateNode cuantiza la posición del nodo nuevo a la grilla', () => {
    const store = makeStore('orig')
    const id = store.getState().duplicateNode('orig', { x: 123, y: 9 })
    const node = store.getState().nodes.find(n => n.id === id)
    expect(node.position).toEqual({ x: 120, y: 0 })
  })

  it('updateEdgeBend cuantiza bendX/bendY a la grilla', () => {
    const store = makeStore()
    store.setState({
      edges: [{ id: 'e1', source: 'a', target: 'b' }],
    })
    store.getState().updateEdgeBend('e1', 47, 33)
    const edge = store.getState().edges.find(e => e.id === 'e1')
    expect(edge.data).toEqual({ bendX: 40, bendY: 40 })
  })

  it('updateEdgeBend con bendX null limpia el bend sin intentar cuantizarlo', () => {
    const store = makeStore()
    store.setState({
      edges: [{ id: 'e1', source: 'a', target: 'b', data: { bendX: 40, bendY: 40 } }],
    })
    store.getState().updateEdgeBend('e1', null, null)
    const edge = store.getState().edges.find(e => e.id === 'e1')
    expect(edge.data).toEqual({})
  })

  it('el tamaño de grilla usado por el store es el mismo que exporta utils/grid', () => {
    const store = makeStore()
    const id = store.getState().addNode('send_message', { x: GRID_SIZE * 3 + 1, y: 0 })
    const node = store.getState().nodes.find(n => n.id === id)
    expect(node.position.x).toBe(GRID_SIZE * 3)
  })
})
