const { test, expect } = require('@playwright/test')

async function login(page) {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
  await page.getByPlaceholder('Contraseña').fill('admin')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL('/dashboard')
}

// ── Sección Monitor inline ────────────────────────────────────────────────────

test('sección Monitor visible en el dashboard', async ({ page }) => {
  await login(page)
  await expect(page.locator('.mon-inline')).toBeVisible()
})

test('monitor tiene tabs de fuente backend y frontend', async ({ page }) => {
  await login(page)
  await expect(page.getByRole('button', { name: 'backend' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'frontend' })).toBeVisible()
})

test('monitor tiene selector de ventana de tiempo', async ({ page }) => {
  await login(page)
  for (const label of ['15m', '30m', '1h', '3h']) {
    await expect(page.getByRole('button', { name: label })).toBeVisible()
  }
})

test('monitor tiene botón Pausar', async ({ page }) => {
  await login(page)
  await expect(page.getByRole('button', { name: /Pausar/ })).toBeVisible()
})

test('monitor muestra cuatro stat cards', async ({ page }) => {
  await login(page)
  const cards = page.locator('.mon-stat')
  await expect(cards).toHaveCount(4)
})

// ── Log en tiempo real ────────────────────────────────────────────────────────

test('el log muestra líneas del backend', async ({ page }) => {
  await login(page)
  await expect(page.locator('.mon-line').first()).toBeVisible({ timeout: 5000 })
  const count = await page.locator('.mon-line').count()
  expect(count).toBeGreaterThan(0)
})

test('el contador de líneas muestra un número mayor a 0', async ({ page }) => {
  await login(page)
  await page.waitForTimeout(2500)
  const counter = page.locator('.mon-count')
  await expect(counter).toBeVisible()
  const text = await counter.textContent()
  const n = parseInt(text)
  expect(n).toBeGreaterThan(0)
})

// ── Filtro ────────────────────────────────────────────────────────────────────

test('filtro reduce las líneas mostradas', async ({ page }) => {
  await login(page)
  await page.waitForTimeout(2500)

  const totalText = await page.locator('.mon-count').textContent()
  const total = parseInt(totalText)

  await page.locator('.mon-filter').fill('GET /api/bots')
  await page.waitForTimeout(300)

  const filteredText = await page.locator('.mon-count').textContent()
  const filtered = parseInt(filteredText)
  expect(filtered).toBeLessThan(total)
})

test('filtro sin coincidencias muestra 0 líneas y mensaje vacío', async ({ page }) => {
  await login(page)
  await page.locator('.mon-filter').fill('xXxNOEXISTExXx')
  await page.waitForTimeout(300)
  await expect(page.locator('.mon-empty')).toBeVisible()
})

// ── Pausar ────────────────────────────────────────────────────────────────────

test('pausar cambia el botón a Reanudar y muestra badge PAUSADO', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Pausar/ }).click()
  await expect(page.getByRole('button', { name: /Reanudar/ })).toBeVisible()
  await expect(page.locator('.mon-paused-badge')).toBeVisible()
})

// ── Colapsar sección ──────────────────────────────────────────────────────────

test('colapsar y expandir la sección Monitor', async ({ page }) => {
  await login(page)
  await expect(page.locator('.mon-inline')).toBeVisible()

  // Colapsar
  await page.getByRole('button', { name: /Colapsar/ }).first().click()
  await expect(page.locator('.mon-inline')).not.toBeVisible()

  // Expandir
  await page.getByRole('button', { name: /Expandir/ }).first().click()
  await expect(page.locator('.mon-inline')).toBeVisible()
})

// ── Simulador (solo en modo sim) ──────────────────────────────────────────────

test('dashboard muestra badge SIM en modo simulado', async ({ page, request }) => {
  const modeRes = await request.get('/api/mode', { headers: { 'x-password': 'admin' } })
  const { mode } = await modeRes.json()
  test.skip(mode !== 'sim', 'Solo aplica en modo simulado (ENABLE_BOTS=false)')

  await login(page)
  await expect(page.locator('.badge.s-sim').first()).toBeVisible()
})

test('dashboard muestra botones de simulador para teléfonos conectados', async ({ page, request }) => {
  const modeRes = await request.get('/api/mode', { headers: { 'x-password': 'admin' } })
  const { mode } = await modeRes.json()
  test.skip(mode !== 'sim', 'Solo aplica en modo simulado (ENABLE_BOTS=false)')

  await login(page)
  await expect(page.locator('button:has-text("Simulador")').first()).toBeVisible()
})

// ── Mensaje del simulador aparece en el monitor ───────────────────────────────

test('mensaje enviado en simulador aparece en el log del monitor', async ({ page, request }) => {
  const modeRes = await request.get('/api/mode', { headers: { 'x-password': 'admin' } })
  const { mode } = await modeRes.json()
  test.skip(mode !== 'sim', 'Solo aplica en modo simulado (ENABLE_BOTS=false)')

  const botsRes = await request.get('/api/bots', { headers: { 'x-password': 'admin' } })
  const bots = await botsRes.json()
  const number = bots[0].phones[0].number

  await login(page)
  await page.waitForTimeout(500)

  await request.post(`/api/sim/send/${number}`, {
    headers: { 'x-password': 'admin', 'content-type': 'application/json' },
    data: JSON.stringify({ from_name: 'PlaywrightTest', from_phone: '5411111111', text: 'test monitor e2e' }),
  })

  await page.locator('.mon-filter').fill('[sim]')
  await page.waitForTimeout(3000)

  const lines = page.locator('.mon-line')
  const count = await lines.count()
  expect(count).toBeGreaterThan(0)

  let found = false
  for (let i = 0; i < count; i++) {
    const text = await lines.nth(i).textContent()
    if (text.includes('PlaywrightTest')) { found = true; break }
  }
  expect(found).toBe(true)
})
