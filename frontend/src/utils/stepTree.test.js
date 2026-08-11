import { describe, it, expect } from 'vitest'
import { buildStepTree, maxTreeDepth } from './stepTree.js'

function step(node_id) {
  return { node_id, id: node_id }
}

describe('buildStepTree — jerarquía de nodo_flow anidados sin límite de profundidad', () => {
  it('árbol plano cuando no hay namespacing', () => {
    const tree = buildStepTree([step('a'), step('b'), step('c')])
    expect(tree.map(n => n.id)).toEqual(['a', 'b', 'c'])
    expect(tree.every(n => n.depth === 0 && n.children.length === 0)).toBe(true)
  })

  it('anida steps de un nodo_flow bajo su padre', () => {
    const tree = buildStepTree([step('nf1'), step('nf1::inner1'), step('nf1::inner2'), step('after')])
    expect(tree).toHaveLength(2)
    expect(tree[0].id).toBe('nf1')
    expect(tree[0].children.map(c => c.id)).toEqual(['nf1::inner1', 'nf1::inner2'])
    expect(tree[1].id).toBe('after')
  })

  it('soporta anidamiento arbitrario (nodo_flow dentro de nodo_flow)', () => {
    const tree = buildStepTree([
      step('nf1'),
      step('nf1::nf2'),
      step('nf1::nf2::inner'),
      step('nf1::after_nf2'),
    ])
    expect(tree[0].id).toBe('nf1')
    expect(tree[0].children[0].id).toBe('nf1::nf2')
    expect(tree[0].children[0].children[0].id).toBe('nf1::nf2::inner')
    expect(tree[0].children[0].depth).toBe(1)
    expect(tree[0].children[0].children[0].depth).toBe(2)
    expect(tree[0].children[1].id).toBe('nf1::after_nf2')
    expect(maxTreeDepth(tree)).toBe(2)
  })

  it('anida bajo el ancestro abierto más profundo aunque un nivel intermedio nunca haya logueado step propio', () => {
    // "nf1::nf2" nunca aparece como step propio -- el compiler saltó directo
    // a su subflow_start. "nf1::nf2::inner" no es descendiente de
    // "nf1::nf2::start" (no comparte ese prefijo completo), así que cuelga
    // como hermano bajo "nf1", que sigue siendo el ancestro abierto válido.
    const tree = buildStepTree([step('nf1'), step('nf1::nf2::start'), step('nf1::nf2::inner')])
    expect(tree[0].children.map(c => c.id)).toEqual(['nf1::nf2::start', 'nf1::nf2::inner'])
  })

  it('cierra la rama y vuelve a nivel raíz cuando el próximo step no comparte prefijo', () => {
    const tree = buildStepTree([step('nf1'), step('nf1::inner'), step('sibling')])
    expect(tree.map(n => n.id)).toEqual(['nf1', 'sibling'])
  })
})
