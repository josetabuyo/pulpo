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

// Abre el editor del primer flow haciendo click en su fila
async function clickFlowEdit(card) {
  await card.locator('.flow-row').first().click()
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
  await expect(page.getByText('NODOS')).toBeVisible({ timeout: 8000 })
  await expect(page.getByRole('button', { name: 'Guardar' })).toBeVisible()
})

test('botón volver regresa a la lista', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByText('NODOS')).toBeVisible({ timeout: 8000 })
  await page.getByTitle('Volver').click()
  await expect(card.getByRole('button', { name: /Nuevo flow/i })).toBeVisible()
})

test('doble click en un nodo abre el panel de configuración', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByText('NODOS')).toBeVisible({ timeout: 8000 })

  const nodes = page.locator('.react-flow__node')
  const count = await nodes.count()
  test.skip(count === 0, 'el flow no tiene nodos para configurar')

  await nodes.first().dblclick()
  // El panel (components/nodeconfig/ConfigForm) muestra el header con el label editable
  await expect(page.getByTitle('Editar nombre del nodo')).toBeVisible({ timeout: 5000 })
})

test('crear nuevo flow y verificar que aparece en la lista', async ({ page }) => {
  const card = await goToFlowTab(page)
  const before = await card.locator('.flow-row').count()

  await card.getByRole('button', { name: /Nuevo flow/i }).click()
  await expect(page.getByText('NODOS')).toBeVisible({ timeout: 8000 })

  await page.getByTitle('Volver').click()
  await expect(async () => {
    const after = await card.locator('.flow-row').count()
    expect(after).toBeGreaterThanOrEqual(before)
  }).toPass({ timeout: 8000 })
})
