/**
 * architecture.spec.cjs — tests de la sección Arquitectura del dashboard.
 *
 * Requiere back + front corriendo (mismo setup que el resto de la suite).
 */
const { test, expect } = require('@playwright/test')

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

async function login(page) {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
  await page.getByPlaceholder('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL(/\/dashboard/)
}

test('la sección Arquitectura existe y aparece antes que Config', async ({ page }) => {
  await login(page)
  const titles = page.locator('.section-block-title')
  await expect(titles.filter({ hasText: 'Arquitectura' })).toBeVisible()
  // Orden en el DOM: Arquitectura primero, Config después
  const all = await titles.allInnerTexts()
  const archIdx = all.findIndex(t => t.includes('Arquitectura'))
  const configIdx = all.findIndex(t => t.includes('Config'))
  expect(archIdx).toBeGreaterThanOrEqual(0)
  expect(configIdx).toBeGreaterThan(archIdx)
})

test('sin query param la sección arranca colapsada', async ({ page }) => {
  await login(page)
  await page.goto('/dashboard')
  await expect(page.locator('.arch-panel')).toHaveCount(0)
})

test('deep link ?arquitectura=1 expande la sección con datos vivos', async ({ page }) => {
  await login(page)
  await page.goto('/dashboard?arquitectura=1')
  const panel = page.locator('.arch-panel')
  await expect(panel).toBeVisible({ timeout: 8000 })
  // Hero con el nombre del sistema
  await expect(panel.getByText('— arquitectura')).toBeVisible()
  // Catálogo dinámico de nodos: al menos un nodo conocido del registry
  await expect(panel.getByText('Sumarizador')).toBeVisible()
  await expect(panel.locator('.arch-node-trigger').first()).toBeVisible()
  // Sección de tests presente (con reporte o estado vacío)
  await expect(panel.getByText('Backend — pytest')).toBeVisible()
  await expect(panel.getByText('Frontend — Playwright')).toBeVisible()
})

test('expandir la sección actualiza la URL con ?arquitectura=1', async ({ page }) => {
  await login(page)
  await page.locator('.section-block-header', { hasText: 'Arquitectura' }).click()
  await expect(page).toHaveURL(/arquitectura=1/)
})

test('la ruta /dashboard/arquitectura redirige al deep link', async ({ page }) => {
  await login(page)
  await page.goto('/dashboard/arquitectura')
  await expect(page).toHaveURL(/\/dashboard\?arquitectura=1/)
  await expect(page.locator('.arch-panel')).toBeVisible({ timeout: 8000 })
})
