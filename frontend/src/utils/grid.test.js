import { describe, it, expect } from 'vitest'
import { NODE_WIDTH, GRID_SIZE, snapValue, snapPoint } from './grid.js'

describe('grid', () => {
  it('el tamaño de celda es un octavo del ancho del chip del nodo', () => {
    expect(GRID_SIZE).toBe(NODE_WIDTH / 8)
    expect(GRID_SIZE).toBe(20)
  })

  it('snapValue cuantiza al múltiplo de grilla más cercano', () => {
    expect(snapValue(0)).toBe(0)
    expect(snapValue(9)).toBe(0)
    expect(snapValue(10)).toBe(20) // empate redondea hacia arriba (Math.round)
    expect(snapValue(11)).toBe(20)
    expect(snapValue(29)).toBe(20)
    expect(snapValue(31)).toBe(40)
    expect(snapValue(200)).toBe(200)
  })

  it('snapValue funciona con valores negativos (sin devolver -0)', () => {
    expect(Object.is(snapValue(-9), 0)).toBe(true)
    expect(snapValue(-11)).toBe(-20)
    expect(snapValue(-30)).toBe(-20)
  })

  it('snapValue acepta un tamaño de grilla custom', () => {
    expect(snapValue(12, 10)).toBe(10)
    expect(snapValue(16, 10)).toBe(20)
  })

  it('snapPoint cuantiza x e y independientemente', () => {
    expect(snapPoint({ x: 47, y: 33 })).toEqual({ x: 40, y: 40 })
    expect(snapPoint({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 })
    expect(snapPoint({ x: -5, y: 137 })).toEqual({ x: 0, y: 140 })
  })
})
