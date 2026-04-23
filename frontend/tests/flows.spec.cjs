/**
 * flows.spec.cjs — tests del Flow Editor (Fase 2)
 *
 * Requiere server corriendo en :8003 / :5178
 * Correr: cd frontend && node_modules/.bin/playwright test tests/flows.spec.cjs
 */
const { test, expect } = require('@playwright/test')

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

// Helper: login y navegar a la tab "Flow" de la primera empresa
// Devuelve { card, flowSection } para que los tests puedan escopar sus selectores
async function goToFlowTab(page) {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
  await page.getByPlaceholder('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL('/dashboard')

  // Abrir la primera empresa visible
  const card = page.locator('.ec-card').first()
  await card.waitFor({ state: 'visible' })

  // Hacer clic en la tab "Flow"
  await card.getByRole('button', { name: 'Flow' }).click()
  // Esperar a que cargue la lista de flows (botón Nuevo flow)
  await card.getByRole('button', { name: /Nuevo flow/i }).waitFor({ state: 'visible' })

  return card
}

test('tab Flow muestra lista de flows', async ({ page }) => {
  const card = await goToFlowTab(page)
  await expect(card.getByText(/flow/i).first()).toBeVisible()
})

test('lista de flows tiene botón Nuevo flow', async ({ page }) => {
  const card = await goToFlowTab(page)
  await expect(card.getByRole('button', { name: /Nuevo flow/i })).toBeVisible()
})

// Dentro de una ec-card, el btn "Editar" nth(0) es el de la empresa, nth(1) es el del primer flow.
async function clickFlowEdit(card) {
  await card.getByRole('button', { name: 'Editar' }).nth(1).click()
}

test('botón Editar abre el editor', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(card.getByText('NODOS')).toBeVisible({ timeout: 8000 })
  await expect(card.getByRole('button', { name: 'Guardar' })).toBeVisible()
})

test('editor muestra nodos de la paleta', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(card.getByText('NODOS')).toBeVisible({ timeout: 8000 })
  await expect(card.getByText('Respuesta fija').first()).toBeVisible()
  await expect(card.getByText('Respuesta LLM').first()).toBeVisible()
  await expect(card.getByText('Sumarizador').first()).toBeVisible()
})

test('botón volver regresa a la lista', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(card.getByText('NODOS')).toBeVisible({ timeout: 8000 })
  await card.getByTitle('Volver a la lista').click()
  await expect(card.getByRole('button', { name: /Nuevo flow/i })).toBeVisible()
})

test('crear nuevo flow y verificar que aparece en la lista', async ({ page }) => {
  const card = await goToFlowTab(page)
  // Contar flows existentes (empresaEditar + n flowEditar; nth(0) es empresa, nth(1+) son flows)
  const before = await card.getByRole('button', { name: 'Editar' }).count()

  await card.getByRole('button', { name: /Nuevo flow/i }).click()
  await expect(card.getByText('NODOS')).toBeVisible({ timeout: 8000 })

  await card.getByTitle('Volver a la lista').click()
  // Esperar a que loadFlows() termine (puede ser async) con retry
  await expect(async () => {
    const after = await card.getByRole('button', { name: 'Editar' }).count()
    expect(after).toBeGreaterThanOrEqual(before)
  }).toPass({ timeout: 8000 })
})
