// Bug real 2026-09-01: este archivo probaba un login por password
// (`.getByPlaceholder('Contraseña')`) que ya no existe -- LoginPage.jsx es
// Google-only desde hace tiempo, ADMIN_PASSWORD quedó vestigial. Todos los
// tests de esta suite (y de flows/bot_safety/architecture/summary_bubble,
// que comparten el mismo helper) hacían timeout esperando ese campo.
// Reescrito para probar la UI real (botón de Google) + el flujo de sesión
// vía el bypass "test-login" (web/auth.ts, ver tests/helpers.cjs) para todo
// lo que necesita estar logueado -- Playwright no puede completar un OAuth
// real contra Google.
const { test, expect } = require('@playwright/test')
const { loginAsAdmin } = require('./helpers.cjs')

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
})

test('muestra pantalla de login con botón de Google', async ({ page }) => {
  await expect(page.getByRole('heading', { name: /Admin/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Continuar con Google/ })).toBeVisible()
})

test('email no autorizado no genera sesión (AccessDenied)', async ({ page }) => {
  const { csrfToken } = await page.request.get('/api/auth/csrf').then(r => r.json())
  await page.request.post('/api/auth/callback/test-login', {
    form: { email: 'nadie@ejemplo.com', csrfToken, json: 'true' },
  })
  const session = await page.request.get('/api/auth/session').then(r => r.json())
  expect(session).toBeNull()
})

test('login con admin navega al dashboard', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/dashboard')
  await expect(page).toHaveURL('/dashboard')
  await expect(page.getByText('Pulpo — Admin')).toBeVisible()
})

test('dashboard muestra sección de empresas', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/dashboard')
  await expect(page.getByText('🏢 Bots')).toBeVisible()
  await expect(page.getByRole('button', { name: '+ Nueva bot' })).toBeVisible()
})

test('expandir Monitor actualiza la URL con ?monitor=1', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/dashboard')

  await page.locator('.section-block-header').filter({ hasText: 'Monitor' }).click()
  await expect(page).toHaveURL(/monitor=1/)
})

test('navegar a /dashboard?monitor=1 muestra Monitor expandido', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/dashboard?monitor=1')
  await expect(page.locator('.mon-inline')).toBeVisible({ timeout: 5000 })
})
