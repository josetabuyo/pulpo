const { test, expect } = require('@playwright/test')

async function login(page) {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
  await page.getByPlaceholder('Contraseña').fill('admin')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL('/dashboard')
}

// ── Botón Monitor ─────────────────────────────────────────────────────────────

test('botón Monitor visible en el header del dashboard', async ({ page }) => {
  await login(page)
  await expect(page.getByRole('button', { name: /Monitor/ })).toBeVisible()
})

test('botón Monitor abre el drawer lateral', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
  await expect(page.locator('.mon-drawer')).toBeVisible()
})

test('drawer tiene tabs backend y frontend', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
  await expect(page.getByRole('button', { name: 'backend' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'frontend' })).toBeVisible()
})

test('drawer tiene botón Pausar y cerrar', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
  await expect(page.getByRole('button', { name: /Pausar/ })).toBeVisible()
  await expect(page.getByRole('button', { name: '✕' })).toBeVisible()
})

test('botón cerrar cierra el drawer', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
  await expect(page.locator('.mon-drawer')).toBeVisible()
  await page.getByRole('button', { name: '✕' }).click()
  await expect(page.locator('.mon-drawer')).not.toBeVisible()
})

// ── Log en tiempo real ────────────────────────────────────────────────────────

test('el log muestra líneas del backend', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
  // Esperar hasta que aparezca al menos una línea INFO
  await expect(page.locator('.mon-line').first()).toBeVisible({ timeout: 5000 })
  const count = await page.locator('.mon-line').count()
  expect(count).toBeGreaterThan(0)
})

test('el contador de líneas muestra un número mayor a 0', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
  await page.waitForTimeout(2500) // esperar un ciclo de polling
  const counter = page.locator('.mon-count')
  await expect(counter).toBeVisible()
  const text = await counter.textContent()
  const n = parseInt(text)
  expect(n).toBeGreaterThan(0)
})

// ── Filtro ────────────────────────────────────────────────────────────────────

test('filtro reduce las líneas mostradas', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
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
  await page.getByRole('button', { name: /Monitor/ }).click()
  await page.locator('.mon-filter').fill('xXxNOEXISTExXx')
  await page.waitForTimeout(300)
  await expect(page.locator('.mon-empty')).toBeVisible()
})

// ── Pausar ────────────────────────────────────────────────────────────────────

test('pausar cambia el botón a Reanudar y muestra badge PAUSADO', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
  await page.getByRole('button', { name: /Pausar/ }).click()
  await expect(page.getByRole('button', { name: /Reanudar/ })).toBeVisible()
  await expect(page.locator('.mon-paused-badge')).toBeVisible()
})

// ── Simulador visible en dashboard ────────────────────────────────────────────

test('dashboard muestra badge SIM en modo simulado', async ({ page }) => {
  await login(page)
  await expect(page.locator('.badge.s-sim').first()).toBeVisible()
})

test('dashboard muestra botones de simulador para teléfonos conectados', async ({ page }) => {
  await login(page)
  await expect(page.locator('button:has-text("Simulador")').first()).toBeVisible()
})

// ── Mensaje del simulador aparece en el monitor ───────────────────────────────

test('mensaje enviado en simulador aparece en el log del monitor', async ({ page, request }) => {
  // 1. Obtener un número via API
  const botsRes = await request.get('/api/bots', { headers: { 'x-password': 'admin' } })
  const bots = await botsRes.json()
  const number = bots[0].phones[0].number

  // 2. Abrir monitor
  await login(page)
  await page.getByRole('button', { name: /Monitor/ }).click()
  await page.waitForTimeout(500)

  // 3. Enviar mensaje via API
  await request.post(`/api/sim/send/${number}`, {
    headers: { 'x-password': 'admin', 'content-type': 'application/json' },
    data: JSON.stringify({ from_name: 'PlaywrightTest', from_phone: '5411111111', text: 'test monitor e2e' }),
  })

  // 4. Filtrar por [sim] y verificar
  await page.locator('.mon-filter').fill('[sim]')
  await page.waitForTimeout(3000) // esperar polling

  const lines = page.locator('.mon-line')
  const count = await lines.count()
  expect(count).toBeGreaterThan(0)

  // Verificar que alguna línea contiene el mensaje
  let found = false
  for (let i = 0; i < count; i++) {
    const text = await lines.nth(i).textContent()
    if (text.includes('PlaywrightTest')) { found = true; break }
  }
  expect(found).toBe(true)
})
