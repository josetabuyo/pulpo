/**
 * bot_safety.spec.cjs — tests UI de las nuevas protecciones anti-spam.
 *
 * Cubre:
 *  - Botón ⏸ Pausar visible en EmpresaCard header
 *  - Click Pausar → botón cambia a ▶ Reanudar
 *  - Click Reanudar → vuelve a ⏸ Pausar
 *
 * Requiere server corriendo (backend + frontend).
 * Correr: cd frontend && node_modules/.bin/playwright test tests/bot_safety.spec.cjs
 */
const { test, expect } = require('@playwright/test')

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

async function loginAndGetCard(page) {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
  await page.getByPlaceholder('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL('/dashboard')
  const card = page.locator('.ec-card').first()
  await card.waitFor({ state: 'visible' })
  return card
}

/**
 * Normaliza la card a estado NO pausado, sin importar el estado actual.
 * Hace click en "Reanudar" si está visible, o no hace nada si ya está "Pausar".
 */
async function ensureResumed(card) {
  const resumeBtn = card.getByRole('button', { name: /Reanudar/i })
  const isResumeVisible = await resumeBtn.isVisible()
  if (isResumeVisible) {
    await resumeBtn.click()
    await card.getByRole('button', { name: /Pausar/i }).waitFor({ state: 'visible', timeout: 5000 })
  }
}

test('botón Pausar o Reanudar es visible en el header de la empresa card', async ({ page }) => {
  const card = await loginAndGetCard(page)
  // Acepta cualquier estado inicial — puede haber quedado pausado de una corrida anterior
  const pauseOrResume = card.getByRole('button', { name: /Pausar|Reanudar/i })
  await expect(pauseOrResume).toBeVisible()
})

test('click Pausar cambia el botón a Reanudar', async ({ page }) => {
  const card = await loginAndGetCard(page)
  await ensureResumed(card)
  await card.getByRole('button', { name: /Pausar/i }).click()
  await expect(card.getByRole('button', { name: /Reanudar/i })).toBeVisible({ timeout: 5000 })
})

test('click Reanudar vuelve a Pausar', async ({ page }) => {
  const card = await loginAndGetCard(page)
  await ensureResumed(card)

  // Pausar primero
  await card.getByRole('button', { name: /Pausar/i }).click()
  await expect(card.getByRole('button', { name: /Reanudar/i })).toBeVisible({ timeout: 5000 })

  // Reanudar
  await card.getByRole('button', { name: /Reanudar/i }).click()
  await expect(card.getByRole('button', { name: /Pausar/i })).toBeVisible({ timeout: 5000 })
})
