const { test, expect } = require('@playwright/test')

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

async function login(page) {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
  await page.getByPlaceholder('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL('/dashboard')
}

async function expandMonitor(page) {
  await page.locator('.section-block-header').filter({ hasText: 'Monitor' }).click()
  await expect(page.locator('.mon-inline')).toBeVisible({ timeout: 5000 })
}

// ── Sección Monitor inline ────────────────────────────────────────────────────

test('sección Monitor visible en el dashboard', async ({ page }) => {
  await login(page)
  await expandMonitor(page)
  await expect(page.locator('.mon-inline')).toBeVisible()
})

test('monitor tiene tabs de fuente backend y frontend', async ({ page }) => {
  await login(page)
  await expandMonitor(page)
  await expect(page.getByRole('button', { name: 'backend' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'frontend' })).toBeVisible()
})

test('monitor tiene selector de ventana de tiempo', async ({ page }) => {
  await login(page)
  await expandMonitor(page)
  for (const label of ['15m', '30m', '1h', '3h']) {
    await expect(page.getByRole('button', { name: label })).toBeVisible()
  }
})

test('monitor tiene botón Pausar', async ({ page }) => {
  await login(page)
  await expandMonitor(page)
  await expect(page.locator('.mon-inline').getByRole('button', { name: /Pausar/ })).toBeVisible()
})

test('monitor muestra cuatro stat cards', async ({ page }) => {
  await login(page)
  const cards = page.locator('.mon-stat')
  await expect(cards).toHaveCount(4)
})

// ── Log en tiempo real ────────────────────────────────────────────────────────

test('el log muestra líneas del backend', async ({ page }) => {
  await login(page)
  await expandMonitor(page)
  await expect(page.locator('.mon-line').first()).toBeVisible({ timeout: 5000 })
  const count = await page.locator('.mon-line').count()
  expect(count).toBeGreaterThan(0)
})

test('el contador de líneas muestra un número mayor a 0', async ({ page }) => {
  await login(page)
  await expandMonitor(page)
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
  await expandMonitor(page)
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
  await expandMonitor(page)
  await page.locator('.mon-filter').fill('xXxNOEXISTExXx')
  await page.waitForTimeout(300)
  await expect(page.locator('.mon-empty')).toBeVisible()
})

// ── Pausar ────────────────────────────────────────────────────────────────────

test('pausar cambia el botón a Reanudar y muestra badge PAUSADO', async ({ page }) => {
  await login(page)
  await expandMonitor(page)
  await page.locator('.mon-inline').getByRole('button', { name: /Pausar/ }).click()
  await expect(page.locator('.mon-inline').getByRole('button', { name: /Reanudar/ })).toBeVisible()
  await expect(page.locator('.mon-paused-badge')).toBeVisible()
})

// ── Colapsar sección ──────────────────────────────────────────────────────────

test('colapsar y expandir la sección Monitor', async ({ page }) => {
  await login(page)
  await expandMonitor(page)
  await expect(page.locator('.mon-inline')).toBeVisible()

  // Colapsar
  await page.locator('.section-block-header').filter({ hasText: 'Monitor' }).getByRole('button', { name: /Colapsar/ }).click()
  await expect(page.locator('.mon-inline')).not.toBeVisible()

  // Expandir
  await page.locator('.section-block-header').filter({ hasText: 'Monitor' }).getByRole('button', { name: /Expandir/ }).click()
  await expect(page.locator('.mon-inline')).toBeVisible()
})

