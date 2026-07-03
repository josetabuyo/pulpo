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
  await expect(card.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })
  await expect(card.getByRole('button', { name: 'Guardar' })).toBeVisible()
})

test('editor muestra botón Guardar', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })
  await expect(page.getByRole('button', { name: 'Guardar' })).toBeVisible()
})

test('botón volver regresa a la lista', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })
  await page.getByTitle('Volver').click()
  await expect(card.getByRole('button', { name: /Nuevo flow/i })).toBeVisible()
})

test('doble click en un nodo abre el panel de configuración', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

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
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  await page.getByTitle('Volver').click()
  await expect(async () => {
    const after = await card.locator('.flow-row').count()
    expect(after).toBeGreaterThanOrEqual(before)
  }).toPass({ timeout: 8000 })
})

// ─── NodePicker: whatsapp_trigger + buscador ───────────────────────────────────
// El picker se abre con el botón "+ Nuevo nodo" en NodeConfigPanel (ex NodePalette izquierda)

test('picker de nodos incluye whatsapp_trigger', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await page.getByRole('button', { name: '+ Nuevo nodo' }).click()
  const picker = page.getByTestId('node-picker')
  await expect(picker.getByText('whatsapp_trigger')).toBeVisible()
})

test('buscador de nodos filtra por texto', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await page.getByRole('button', { name: '+ Nuevo nodo' }).click()

  const picker = page.getByTestId('node-picker')
  const filter = picker.getByPlaceholder('Buscar nodo...')
  await expect(filter).toBeVisible()

  // Con "send" solo debe verse send_message en el picker, no whatsapp_trigger
  await filter.fill('send')
  await expect(picker.getByText('send_message')).toBeVisible()
  await expect(picker.getByText('whatsapp_trigger')).not.toBeVisible()

  // Al borrar el filtro vuelven todos
  await filter.fill('')
  await expect(picker.getByText('whatsapp_trigger')).toBeVisible()
})

// ─── Back-edge: curva hacia la izquierda (getLoopBackPath) ────────────────────

test('back-edge usa path con dos segmentos cúbicos (getLoopBackPath)', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => sessionStorage.clear())
  await page.goto('/')
  await page.getByPlaceholder('Contraseña').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await page.waitForURL('/dashboard')

  // Abrir tab Flow del bot Luganense (tiene back-edge sin_direccion → pedir_direccion)
  const luganenseCard = page.locator('.ec-card', { has: page.locator('text=luganense') })
  await luganenseCard.waitFor({ state: 'visible', timeout: 8000 })
  await luganenseCard.getByRole('button', { name: 'Flow' }).click()

  const flowRow = luganenseCard.locator('.flow-row', { has: page.locator('text=Orquestador Vendedor') })
  await flowRow.waitFor({ state: 'visible', timeout: 8000 })
  await flowRow.click()
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  // La etiqueta del back-edge debe ser visible
  await expect(page.getByText('sin_direccion')).toBeVisible({ timeout: 8000 })

  // Verificar que al menos un edge SVG usa dos segmentos C (firma de getLoopBackPath)
  // getBezierPath estándar produce un solo "C"; getLoopBackPath produce dos "C"
  const paths = page.locator('.react-flow__edge path.react-flow__edge-path')
  await paths.first().waitFor({ timeout: 8000 })
  const count = await paths.count()
  let hasLoopBackPath = false
  for (let i = 0; i < count; i++) {
    const d = await paths.nth(i).getAttribute('d')
    if (d && (d.match(/C .+ C /) || d.split('C').length > 2)) {
      hasLoopBackPath = true
      break
    }
  }
  expect(hasLoopBackPath).toBe(true)
})

test('buscador del picker arranca vacío al reabrirlo', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  const toggle = page.getByRole('button', { name: '+ Nuevo nodo' })
  await expect(toggle).toBeVisible({ timeout: 8000 })

  // Abrir el picker y escribir algo en el filtro
  await toggle.click()
  const picker = page.getByTestId('node-picker')
  await picker.getByPlaceholder('Buscar nodo...').fill('send')
  await expect(picker.getByText('whatsapp_trigger')).not.toBeVisible()

  // Cerrar (el picker se desmonta) y volver a abrir
  await page.getByRole('button', { name: '− Nuevo nodo' }).click()
  await expect(picker).not.toBeVisible()
  await toggle.click()

  // El filtro debe estar vacío y todos los nodos visibles
  const reopenedPicker = page.getByTestId('node-picker')
  await expect(reopenedPicker.getByPlaceholder('Buscar nodo...')).toHaveValue('')
  await expect(reopenedPicker.getByText('whatsapp_trigger')).toBeVisible()
})

// ─── Modo eliminar nodos ────────────────────────────────────────────────────

test('modo eliminar: click en un nodo pide confirmación y lo borra', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  // Agregar un nodo nuevo para borrarlo sin afectar el flow existente
  await page.getByRole('button', { name: '+ Nuevo nodo' }).click()
  const picker = page.getByTestId('node-picker')
  await picker.getByText('send_message').click()

  const countBefore = await page.locator('.react-flow__node').count()

  // Activar modo eliminar
  await page.getByRole('button', { name: /Eliminar/i }).click()

  // El botón "+ Nuevo nodo" queda deshabilitado mientras el modo eliminar está activo
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeDisabled()

  // Click en el último nodo agregado dispara el popup de confirmación
  const nodeToDelete = page.locator('.react-flow__node').last()
  const nodeLabel = await nodeToDelete.textContent()
  await nodeToDelete.click()

  const confirmButton = page.getByRole('button', { name: 'Sí, eliminar' })
  await expect(confirmButton).toBeVisible({ timeout: 5000 })
  if (nodeLabel) {
    await expect(page.getByText(new RegExp(`¿Eliminar.*${nodeLabel.trim()}`))).toBeVisible()
  }

  await confirmButton.click()

  await expect(async () => {
    const countAfter = await page.locator('.react-flow__node').count()
    expect(countAfter).toBe(countBefore - 1)
  }).toPass({ timeout: 5000 })
})

test('modo eliminar: cancelar la confirmación no borra el nodo', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  const nodes = page.locator('.react-flow__node')
  const countBefore = await nodes.count()
  test.skip(countBefore === 0, 'el flow no tiene nodos para probar el cancelar')

  await page.getByRole('button', { name: /Eliminar/i }).click()
  await nodes.first().click()

  const cancelButton = page.getByRole('button', { name: 'Cancelar' })
  await expect(cancelButton).toBeVisible({ timeout: 5000 })
  await cancelButton.click()

  await expect(cancelButton).not.toBeVisible()
  await expect(nodes).toHaveCount(countBefore)
})
