import { describe, it, expect } from 'vitest'
import { buildExecutionTrace } from './executionTrace.js'

const EDGES = [
  { id: 'e1', source: 'start', target: 'router1' },
  { id: 'e2', source: 'router1', target: 'a', label: 'ruta_a' },
  { id: 'e3', source: 'router1', target: 'b', label: 'ruta_b' },
  { id: 'e4', source: 'a', target: 'end' },
  { id: 'e5', source: 'b', target: 'end' },
]

describe('buildExecutionTrace', () => {
  it('marca como recorridos los nodos por los que pasó la corrida', () => {
    const steps = [{ node_id: 'start' }, { node_id: 'router1', branch_taken: 'ruta_a' }, { node_id: 'a' }, { node_id: 'end' }]
    const { nodeIds } = buildExecutionTrace(steps, EDGES)
    expect(nodeIds).toEqual(new Set(['start', 'router1', 'a', 'end']))
  })

  it('resalta solo la edge de la rama tomada en un router, no las otras salidas', () => {
    const steps = [{ node_id: 'start' }, { node_id: 'router1', branch_taken: 'ruta_a' }, { node_id: 'a' }, { node_id: 'end' }]
    const { edgeIds } = buildExecutionTrace(steps, EDGES)
    expect(edgeIds).toEqual(new Set(['e1', 'e2', 'e4']))
    expect(edgeIds.has('e3')).toBe(false) // ruta_b no se tomó
  })

  it('con la otra rama, resalta la otra edge', () => {
    const steps = [{ node_id: 'start' }, { node_id: 'router1', branch_taken: 'ruta_b' }, { node_id: 'b' }, { node_id: 'end' }]
    const { edgeIds } = buildExecutionTrace(steps, EDGES)
    expect(edgeIds).toEqual(new Set(['e1', 'e3', 'e5']))
  })

  it('sin steps, no resalta nada', () => {
    const { nodeIds, edgeIds } = buildExecutionTrace([], EDGES)
    expect(nodeIds.size).toBe(0)
    expect(edgeIds.size).toBe(0)
  })

  it('nodo_flow: colapsa los steps internos (id compuesto padre::interno) al nodo top-level', () => {
    const flowEdges = [
      { id: 'e1', source: 'start', target: 'sub_flow_node' },
      { id: 'e2', source: 'sub_flow_node', target: 'end' },
    ]
    const steps = [
      { node_id: 'start' },
      { node_id: 'sub_flow_node::__params__0' },
      { node_id: 'sub_flow_node::sf_start_1' },
      { node_id: 'sub_flow_node::node_check' },
      { node_id: 'sub_flow_node::sf_end' },
      { node_id: 'end' },
    ]
    const { nodeIds, edgeIds } = buildExecutionTrace(steps, flowEdges)
    expect(nodeIds).toEqual(new Set(['start', 'sub_flow_node', 'end']))
    expect(edgeIds).toEqual(new Set(['e1', 'e2']))
  })

  it('nodo_flow con salida nombrada (padre::sf_end_<ruta>): resalta la edge de esa ruta, no las otras', () => {
    // Bug real (2026-07-27): un nodo_flow con rutas nombradas (ej. el
    // clasificador de necesidad vía LLM: found/not_found) no setea
    // `branch_taken` en ningún step propio -- la ruta queda en el id del
    // último substep interno, "padre::sf_end_<ruta>". Sin extraerla, solo
    // la edge de ENTRADA al nodo_flow quedaba resaltada, nunca la de salida.
    const flowEdges = [
      { id: 'e1', source: 'start', target: 'clasificador' },
      { id: 'e2', source: 'clasificador', target: 'found_node', label: 'found' },
      { id: 'e3', source: 'clasificador', target: 'not_found_node', label: 'not_found' },
    ]
    const steps = [
      { node_id: 'start' },
      { node_id: 'clasificador::__params__0' },
      { node_id: 'clasificador::sf_start_1' },
      { node_id: 'clasificador::node_llm' },
      { node_id: 'clasificador::sf_end_found' },
      { node_id: 'found_node' },
    ]
    const { nodeIds, edgeIds } = buildExecutionTrace(steps, flowEdges)
    expect(nodeIds).toEqual(new Set(['start', 'clasificador', 'found_node']))
    expect(edgeIds).toEqual(new Set(['e1', 'e2']))
    expect(edgeIds.has('e3')).toBe(false) // not_found no se tomó
  })

  it('un nodo router visitado dos veces (turnos distintos) con ramas distintas resalta ambas edges', () => {
    const steps = [
      { node_id: 'start' }, { node_id: 'router1', branch_taken: 'ruta_a' }, { node_id: 'a' },
      { node_id: 'router1', branch_taken: 'ruta_b' }, { node_id: 'b' }, { node_id: 'end' },
    ]
    const { edgeIds } = buildExecutionTrace(steps, EDGES)
    expect(edgeIds.has('e2')).toBe(true)
    expect(edgeIds.has('e3')).toBe(true)
  })
})
