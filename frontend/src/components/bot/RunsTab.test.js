import { describe, it, expect, vi } from 'vitest'
import { buildNodeLabelMap } from './RunsTab.jsx'

describe('buildNodeLabelMap — labels de steps dentro de NodoFlows expandidos', () => {
  it('resuelve un nodo normal por su label', async () => {
    const nodes = [{ id: 'n1', type: 'send_message', label: 'Enviar bienvenida' }]
    const map = await buildNodeLabelMap(nodes, 'bot1', vi.fn(), '', new Set())
    expect(map.n1).toBe('Enviar bienvenida')
  })

  it('namespacea y resuelve los nodos internos de un nodo_flow', async () => {
    const outer = [{ id: 'nf1', type: 'nodo_flow', config: { flow_id: 'sub1' } }]
    const apiCall = vi.fn().mockResolvedValue({
      definition: { nodes: [{ id: 'inner1', type: 'llm', label: 'Clasificar intención' }] },
    })
    const map = await buildNodeLabelMap(outer, 'bot1', apiCall, '', new Set())
    expect(map['nf1::inner1']).toBe('Clasificar intención')
    expect(apiCall).toHaveBeenCalledWith('GET', '/flows/bots/bot1/sub1', null)
  })

  it('genera labels de "Parámetro: X" para los set_state sintéticos, en el mismo orden que expandNodeFlows', async () => {
    const outer = [{
      id: 'nf1',
      type: 'nodo_flow',
      config: { flow_id: 'sub1', query: 'hola', output: 'result', routes: {} },
    }]
    const apiCall = vi.fn().mockResolvedValue({ definition: { nodes: [] } })
    const map = await buildNodeLabelMap(outer, 'bot1', apiCall, '', new Set())
    expect(map['nf1::__params__0']).toBe('Parámetro: query')
    expect(map['nf1::__params__1']).toBe('Parámetro: output')
  })

  it('no entra en loop infinito si el flow ya fue visitado (ciclo)', async () => {
    const outer = [{ id: 'nf1', type: 'nodo_flow', config: { flow_id: 'sub1' } }]
    const apiCall = vi.fn()
    const map = await buildNodeLabelMap(outer, 'bot1', apiCall, '', new Set(['sub1']))
    expect(map.nf1).toBeDefined()
    expect(apiCall).not.toHaveBeenCalled()
  })
})
