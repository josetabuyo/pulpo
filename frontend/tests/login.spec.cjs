const { test, expect } = require('@playwright/test')

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || ADMIN_PASSWORD

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
})

test('muestra pantalla de login', async ({ page }) => {
  await expect(page.getByRole('heading', { name: /Admin/ })).toBeVisible()
  await expect(page.getByPlaceholder('Contraseña')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible()
})

test('contraseña incorrecta muestra error', async ({ page }) => {
  await page.getByPlaceholder('Contraseña').fill('wrong')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByText('Contraseña incorrecta')).toBeVisible()
})

test('login con admin navega al dashboard', async ({ page }) => {
  await page.getByPlaceholder('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL('/dashboard')
  await expect(page.getByText('Pulpo — Admin')).toBeVisible()
})

test('dashboard muestra sección de empresas', async ({ page }) => {
  await page.getByPlaceholder('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL('/dashboard')
  await expect(page.getByText(/Empresas y teléfonos/i).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '+ Nueva empresa' })).toBeVisible()
})

test('proxy /api/auth no devuelve 500', async ({ request }) => {
  const res = await request.post('/api/auth', { data: { password: ADMIN_PASSWORD } })
  expect(res.status()).toBe(200)
  const body = await res.json()
  expect(body.ok).toBe(true)
  expect(body.role).toBe(ADMIN_PASSWORD)
})
