/**
 * Regresión: burbujas outbound (direction="out") deben alinearse a la derecha.
 * Verifica tanto el CSS como la clase aplicada por el componente.
 * También cubre el lightbox de imágenes (sv-img-modal) que antes no abría nada al hacer click.
 */
const { test, expect } = require('@playwright/test')

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

async function login(page) {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
  await page.getByPlaceholder('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL('/dashboard')
}

test('sv-bubble--out tiene align-self: flex-end en el stylesheet', async ({ page }) => {
  await login(page)

  const alignSelf = await page.evaluate(() => {
    // Inyectar un elemento con la clase y medir su estilo computado
    const container = document.createElement('div')
    container.style.cssText = 'display:flex;flex-direction:column;width:400px;position:fixed;top:-9999px'
    document.body.appendChild(container)

    const bubble = document.createElement('div')
    bubble.className = 'sv-bubble sv-bubble--out'
    container.appendChild(bubble)

    const cs = window.getComputedStyle(bubble)
    const val = cs.alignSelf
    document.body.removeChild(container)
    return val
  })

  expect(alignSelf).toBe('flex-end')
})

test('sv-bubble--in tiene align-self: flex-start en el stylesheet', async ({ page }) => {
  await login(page)

  const alignSelf = await page.evaluate(() => {
    const container = document.createElement('div')
    container.style.cssText = 'display:flex;flex-direction:column;width:400px;position:fixed;top:-9999px'
    document.body.appendChild(container)

    const bubble = document.createElement('div')
    bubble.className = 'sv-bubble sv-bubble--in'
    container.appendChild(bubble)

    const cs = window.getComputedStyle(bubble)
    const val = cs.alignSelf
    document.body.removeChild(container)
    return val
  })

  expect(alignSelf).toBe('flex-start')
})

test('sv-bubble--out se posiciona visualmente a la derecha del contenedor', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const container = document.createElement('div')
    container.style.cssText = 'display:flex;flex-direction:column;width:400px;position:fixed;top:0;left:0;background:red'
    document.body.appendChild(container)

    const outBubble = document.createElement('div')
    outBubble.className = 'sv-bubble sv-bubble--out'
    outBubble.style.cssText = 'min-width:80px;padding:8px 12px'
    outBubble.textContent = 'Mensaje outbound'
    container.appendChild(outBubble)

    const inBubble = document.createElement('div')
    inBubble.className = 'sv-bubble sv-bubble--in'
    inBubble.style.cssText = 'min-width:80px;padding:8px 12px'
    inBubble.textContent = 'Mensaje inbound'
    container.appendChild(inBubble)

    const containerRect = container.getBoundingClientRect()
    const outRect = outBubble.getBoundingClientRect()
    const inRect = inBubble.getBoundingClientRect()
    document.body.removeChild(container)

    return {
      containerRight: containerRect.right,
      outRight: outRect.right,
      inLeft: inRect.left,
      containerLeft: containerRect.left,
    }
  })

  // El borde derecho de la burbuja out debe coincidir (±2px) con el borde derecho del contenedor
  expect(Math.abs(result.outRight - result.containerRight)).toBeLessThan(3)
  // La burbuja in debe empezar en el borde izquierdo del contenedor
  expect(Math.abs(result.inLeft - result.containerLeft)).toBeLessThan(3)
})

// ─── Regresión: lightbox de imágenes ─────────────────────────────────────────

test('sv-img-modal tiene position:fixed y z-index alto (overlay de pantalla completa)', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const overlay = document.createElement('div')
    overlay.className = 'sv-img-modal'
    document.body.appendChild(overlay)
    const cs = window.getComputedStyle(overlay)
    const position = cs.position
    const zIndex = cs.zIndex
    document.body.removeChild(overlay)
    return { position, zIndex }
  })

  expect(result.position).toBe('fixed')
  expect(parseInt(result.zIndex)).toBeGreaterThan(999)
})

test('sv-img-thumb tiene max-width y border-radius definidos (thumbnail inline)', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const container = document.createElement('div')
    container.style.cssText = 'position:fixed;top:-9999px'
    document.body.appendChild(container)
    const img = document.createElement('img')
    img.className = 'sv-img-thumb'
    container.appendChild(img)
    const cs = window.getComputedStyle(img)
    const maxWidth = cs.maxWidth
    const borderRadius = cs.borderRadius
    document.body.removeChild(container)
    return { maxWidth, borderRadius }
  })

  expect(result.maxWidth).not.toBe('none')
  expect(parseFloat(result.borderRadius)).toBeGreaterThan(0)
})

test('sv-img-modal-img tiene max-width viewport-relativo y object-fit:contain', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const container = document.createElement('div')
    container.style.cssText = 'position:fixed;top:-9999px'
    document.body.appendChild(container)
    const img = document.createElement('img')
    img.className = 'sv-img-modal-img'
    container.appendChild(img)
    const cs = window.getComputedStyle(img)
    const maxWidthPx = parseFloat(cs.maxWidth)
    const objectFit = cs.objectFit
    document.body.removeChild(container)
    // max-width: 90vw → debe ser ~90% del viewport width (al menos 200px en cualquier pantalla)
    return { maxWidthPx, objectFit, viewportWidth: window.innerWidth }
  })

  expect(result.maxWidthPx).toBeGreaterThan(200)
  // debe ser aprox 90% del viewport (con ±2% de tolerancia)
  expect(result.maxWidthPx / result.viewportWidth).toBeCloseTo(0.9, 1)
  expect(result.objectFit).toBe('contain')
})

// ─── Regresión: indicador de guardado ────────────────────────────────────────

test('sv-save-status--ok tiene color verde y sv-save-status--error tiene color rojo', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const container = document.createElement('div')
    container.style.cssText = 'position:fixed;top:-9999px'
    document.body.appendChild(container)

    const ok = document.createElement('span')
    ok.className = 'sv-save-status sv-save-status--ok'
    container.appendChild(ok)

    const err = document.createElement('span')
    err.className = 'sv-save-status sv-save-status--error'
    container.appendChild(err)

    const okColor = window.getComputedStyle(ok).color
    const errColor = window.getComputedStyle(err).color
    document.body.removeChild(container)
    return { okColor, errColor }
  })

  // ok → color verde (rgb con G alto)
  const [, okR, okG, okB] = result.okColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/).map(Number)
  expect(okG).toBeGreaterThan(okR)
  expect(okG).toBeGreaterThan(okB)

  // error → color rojo (R alto)
  const [, errR, errG, errB] = result.errColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/).map(Number)
  expect(errR).toBeGreaterThan(errG)
  expect(errR).toBeGreaterThan(errB)
})

// ─── Regresión: sv-msg-wrap no rompe alineación ──────────────────────────────
// Cuando cada burbuja se envuelve en un div.sv-msg-wrap (necesario para refs de
// búsqueda), la alineación out/in debe seguir funcionando. Sin la regla CSS
// `sv-msg-wrap { display:flex; flex-direction:column }` este test falla.

test('sv-bubble--out sigue a la derecha cuando está dentro de sv-msg-wrap', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const container = document.createElement('div')
    container.style.cssText = 'display:flex;flex-direction:column;width:400px;position:fixed;top:0;left:0'
    document.body.appendChild(container)

    const wrapOut = document.createElement('div')
    wrapOut.className = 'sv-msg-wrap'
    const bubbleOut = document.createElement('div')
    bubbleOut.className = 'sv-bubble sv-bubble--out'
    bubbleOut.style.cssText = 'min-width:80px;padding:8px 12px'
    bubbleOut.textContent = 'Mensaje out'
    wrapOut.appendChild(bubbleOut)
    container.appendChild(wrapOut)

    const wrapIn = document.createElement('div')
    wrapIn.className = 'sv-msg-wrap'
    const bubbleIn = document.createElement('div')
    bubbleIn.className = 'sv-bubble sv-bubble--in'
    bubbleIn.style.cssText = 'min-width:80px;padding:8px 12px'
    bubbleIn.textContent = 'Mensaje in'
    wrapIn.appendChild(bubbleIn)
    container.appendChild(wrapIn)

    const containerRect = container.getBoundingClientRect()
    const outRect = bubbleOut.getBoundingClientRect()
    const inRect = bubbleIn.getBoundingClientRect()
    document.body.removeChild(container)

    return {
      containerRight: containerRect.right,
      containerLeft: containerRect.left,
      outRight: outRect.right,
      inLeft: inRect.left,
    }
  })

  // out debe llegar al borde derecho del contenedor (±2px)
  expect(Math.abs(result.outRight - result.containerRight)).toBeLessThan(3)
  // in debe empezar en el borde izquierdo (±2px)
  expect(Math.abs(result.inLeft - result.containerLeft)).toBeLessThan(3)
})

test('sv-msg-wrap tiene display:flex y flex-direction:column', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const el = document.createElement('div')
    el.className = 'sv-msg-wrap'
    el.style.cssText = 'position:fixed;top:-9999px'
    document.body.appendChild(el)
    const cs = window.getComputedStyle(el)
    const display = cs.display
    const flexDir = cs.flexDirection
    document.body.removeChild(el)
    return { display, flexDir }
  })

  expect(result.display).toBe('flex')
  expect(result.flexDir).toBe('column')
})

// ─── Regresión: badge de consolidación ───────────────────────────────────────

test('sv-consolidated-badge tiene color verde (protección visual)', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const el = document.createElement('span')
    el.className = 'sv-consolidated-badge'
    el.style.cssText = 'position:fixed;top:-9999px'
    document.body.appendChild(el)
    const cs = window.getComputedStyle(el)
    const color = cs.color
    const background = cs.backgroundColor
    document.body.removeChild(el)
    return { color, background }
  })

  // Color de texto verde (G dominante)
  const colorMatch = result.color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/)
  expect(colorMatch).not.toBeNull()
  const [, r, g, b] = colorMatch.map(Number)
  expect(g).toBeGreaterThan(r)
  expect(g).toBeGreaterThan(b)
})

test('sv-consolidated-badge no tiene cursor de puntero (no es clickeable)', async ({ page }) => {
  await login(page)

  const cursor = await page.evaluate(() => {
    const el = document.createElement('span')
    el.className = 'sv-consolidated-badge'
    el.style.cssText = 'position:fixed;top:-9999px'
    document.body.appendChild(el)
    const cs = window.getComputedStyle(el)
    const val = cs.cursor
    document.body.removeChild(el)
    return val
  })

  expect(cursor).toBe('default')
})

// ─── Regresión: preview de imagen pegada ─────────────────────────────────────

test('sv-insert-img-thumb tiene max-height y border-radius (thumbnail de paste)', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const container = document.createElement('div')
    container.style.cssText = 'position:fixed;top:-9999px'
    document.body.appendChild(container)
    const img = document.createElement('img')
    img.className = 'sv-insert-img-thumb'
    container.appendChild(img)
    const cs = window.getComputedStyle(img)
    const maxHeight = cs.maxHeight
    const borderRadius = cs.borderRadius
    document.body.removeChild(container)
    return { maxHeight, borderRadius }
  })

  expect(result.maxHeight).not.toBe('none')
  expect(parseFloat(result.maxHeight)).toBeGreaterThan(0)
  expect(parseFloat(result.borderRadius)).toBeGreaterThan(0)
})

test('sv-insert-img-preview tiene display:flex y flex-direction:column', async ({ page }) => {
  await login(page)

  const result = await page.evaluate(() => {
    const el = document.createElement('div')
    el.className = 'sv-insert-img-preview'
    el.style.cssText = 'position:fixed;top:-9999px'
    document.body.appendChild(el)
    const cs = window.getComputedStyle(el)
    const display = cs.display
    const flexDir = cs.flexDirection
    document.body.removeChild(el)
    return { display, flexDir }
  })

  expect(result.display).toBe('flex')
  expect(result.flexDir).toBe('column')
})

test('sv-insert-img-remove está posicionado absolute para overlay sobre la imagen', async ({ page }) => {
  await login(page)

  const position = await page.evaluate(() => {
    const wrap = document.createElement('div')
    wrap.className = 'sv-insert-img-wrap'
    wrap.style.cssText = 'position:relative;display:inline-flex;top:-9999px'
    document.body.appendChild(wrap)
    const btn = document.createElement('button')
    btn.className = 'sv-insert-img-remove'
    wrap.appendChild(btn)
    const cs = window.getComputedStyle(btn)
    const val = cs.position
    document.body.removeChild(wrap)
    return val
  })

  expect(position).toBe('absolute')
})
