import { describe, it, expect } from 'vitest'
import { computeNavIndex } from './TestCasesTab.jsx'

describe('computeNavIndex — límites de navegación ▲/▼ en el reporte de un caso', () => {
  it('avanza al siguiente índice con "next"', () => {
    expect(computeNavIndex(0, 3, 'next')).toBe(1)
  })

  it('retrocede al índice anterior con "prev"', () => {
    expect(computeNavIndex(1, 3, 'prev')).toBe(0)
  })

  it('devuelve null al intentar "prev" desde el primer elemento', () => {
    expect(computeNavIndex(0, 3, 'prev')).toBeNull()
  })

  it('devuelve null al intentar "next" desde el último elemento', () => {
    expect(computeNavIndex(2, 3, 'next')).toBeNull()
  })

  it('devuelve null con una lista de un solo elemento en cualquier dirección', () => {
    expect(computeNavIndex(0, 1, 'next')).toBeNull()
    expect(computeNavIndex(0, 1, 'prev')).toBeNull()
  })
})
