import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { chatApi } from './chatApi.js'

// vitest.config.js corre estos tests en environment:'node' (sin DOM, ver
// CLAUDE.md "unit tests de lógica pura, sin browser") -- chatApi.js llama a
// getVisitorKey() (chatVisitor.js), que lee localStorage. Un stub mínimo en
// memoria alcanza, no hace falta jsdom para esto.
function stubLocalStorage() {
  const store = new Map()
  vi.stubGlobal('localStorage', {
    getItem: (k) => store.get(k) ?? null,
    setItem: (k, v) => store.set(k, v),
  })
}

describe('chatApi.sendMessage — attachment_url opcional', () => {
  beforeEach(stubLocalStorage)
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sin attachmentUrl no manda esa clave en el body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ run_id: 'r1', resumed: false }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await chatApi.sendMessage('bot1', 'chat1', 'conv1', 'hola')

    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body).toEqual({ message: 'hola' })
  })

  it('con attachmentUrl la incluye como attachment_url', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ run_id: 'r1', resumed: false }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await chatApi.sendMessage('bot1', 'chat1', 'conv1', '', 'https://blob/x.png')

    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body).toEqual({ message: '', attachment_url: 'https://blob/x.png' })
  })
})

describe('chatApi.uploadAttachment', () => {
  beforeEach(stubLocalStorage)
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sube el archivo como multipart (FormData, sin Content-Type manual) y devuelve _ok/_status', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ url: 'https://blob/x.png' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const file = new File(['x'], 'factura.png', { type: 'image/png' })
    const result = await chatApi.uploadAttachment('bot1', 'chat1', 'conv1', file)

    expect(result).toEqual({ url: 'https://blob/x.png', _status: 201, _ok: true })
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/chat/bot1/chat1/conversations/conv1/attachments')
    expect(opts.body).toBeInstanceOf(FormData)
    expect(opts.headers['Content-Type']).toBeUndefined()
  })
})
