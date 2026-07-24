import { describe, it, expect, vi, afterEach } from 'vitest'
import { api } from './api.js'

describe('api — respuesta 204 sin body', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('DELETE con 204 resuelve sin intentar parsear JSON (no tira)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: () => { throw new Error('no debería llamarse a .json() en un 204') },
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api('DELETE', '/flows/bots/b1/f1', null)).resolves.toBeNull()
  })

  it('un 204 con !ok igual resuelve (no rechaza) con el status', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 204,
      json: () => { throw new Error('no debería llamarse a .json() en un 204') },
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api('DELETE', '/flows/bots/b1/f1', null)).resolves.toEqual({ _status: 204 })
  })

  it('respuestas normales con body siguen parseando JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'f1', name: 'demo' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api('GET', '/flows/bots/b1/f1', null)).resolves.toEqual({ id: 'f1', name: 'demo' })
  })
})
