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
  await expect(card.getByRole('button', { name: 'Guardar', exact: true })).toBeVisible()
})

test('editor muestra botón Guardar', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })
  await expect(page.getByRole('button', { name: 'Guardar', exact: true })).toBeVisible()
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

// ─── Back-edge: loop hacia atrás ────────────────────────────────────────────
// Nota: el routing de edges pasó de getBezierPath a getSmoothStepPath con bend
// points (ver commit 686ff00). Un back-edge ya no se identifica por tener dos
// segmentos cúbicos "C" (eso era de la implementación vieja getLoopBackPath,
// que ya no existe) — ahora se identifica porque su path baja desde el nodo
// origen (sourcePosition: Bottom) antes de subir hacia el destino, que está
// más arriba (ver FlowCanvas.jsx: isBackEdge / getSmoothStepPath).

test('back-edge se renderiza bajando antes de subir hacia el destino', async ({ page }) => {
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

  // El edge sin_direccion (validar_direccion → pedir_direccion) es un back-edge:
  // su path debe bajar (Y aumenta) antes de subir hacia el destino, que está
  // más arriba que el origen.
  const backEdgePath = page.locator('[data-testid="rf__edge-e-serv-sindir"] path.react-flow__edge-path')
  await backEdgePath.waitFor({ timeout: 8000 })
  const d = await backEdgePath.getAttribute('d')
  const coords = d.match(/-?\d+(\.\d+)?/g).map(Number)
  const ys = coords.filter((_, i) => i % 2 === 1)
  const startY = ys[0]
  const maxY = Math.max(...ys)
  expect(maxY).toBeGreaterThan(startY + 10)
})

// ─── Duplicar nodo ───────────────────────────────────────────────────────────

test('botón duplicar está deshabilitado sin nodo seleccionado', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  await expect(page.getByRole('button', { name: '⧉' })).toBeDisabled()
})

test('duplicar nodo crea una copia con la misma config', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  const nodes = page.locator('.react-flow__node')
  const countBefore = await nodes.count()
  test.skip(countBefore === 0, 'el flow no tiene nodos para duplicar')

  // Seleccionar el primer nodo (doble clic abre el panel de config)
  await nodes.first().dblclick()
  await expect(page.getByTitle('Editar nombre del nodo')).toBeVisible({ timeout: 5000 })
  const originalLabel = await page.getByTitle('Editar nombre del nodo').inputValue()
  const originalConfig = await page.locator('.cm-content').first().textContent()

  const duplicateButton = page.getByRole('button', { name: '⧉' })
  await expect(duplicateButton).toBeEnabled()
  await duplicateButton.click()

  await expect(async () => {
    expect(await nodes.count()).toBe(countBefore + 1)
  }).toPass({ timeout: 5000 })

  // El panel sigue mostrando el nodo original (la copia no se selecciona sola)
  await expect(page.getByTitle('Editar nombre del nodo')).toHaveValue(originalLabel)

  // La copia (último nodo en el DOM) tiene la misma config al abrirla
  await nodes.last().dblclick()
  const duplicateConfig = await page.locator('.cm-content').first().textContent()
  expect(duplicateConfig).toBe(originalConfig)
})

// ─── Panel de configuración colapsable ──────────────────────────────────────

test('panel de configuración se puede colapsar y expandir', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  // Colapsar: el botón "Nuevo nodo" desaparece, queda el botón para expandir
  await page.getByTitle('Colapsar panel').click()
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).not.toBeVisible()
  const expandButton = page.getByTitle('Mostrar panel de configuración')
  await expect(expandButton).toBeVisible()

  // Expandir: vuelve a verse el botón "Nuevo nodo"
  await expandButton.click()
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible()
})

test('doble click en un nodo expande el panel si estaba colapsado', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  const nodes = page.locator('.react-flow__node')
  const count = await nodes.count()
  test.skip(count === 0, 'el flow no tiene nodos para configurar')

  // Colapsar el panel
  await page.getByTitle('Colapsar panel').click()
  await expect(page.getByTitle('Mostrar panel de configuración')).toBeVisible()

  // Doble clic en un nodo → el panel se debe expandir solo, mostrando su config
  await nodes.first().dblclick()
  await expect(page.getByTitle('Mostrar panel de configuración')).not.toBeVisible()
  await expect(page.getByTitle('Editar nombre del nodo')).toBeVisible({ timeout: 5000 })
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
  // El label y el badge de tipo son spans hermanos sin separador de texto;
  // textContent() del nodo entero los concatena (ej. "Enviar mensajesend_message").
  // El diálogo de confirmación solo muestra el label, así que hay que leer
  // únicamente el primer span.
  const nodeLabel = await nodeToDelete.locator('span').first().textContent()
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

// ─── Switch activo/inactivo + Guardar como ─────────────────────────────────

test('switch del header desactiva el flow y aparece en Guardados', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  const toggle = page.getByRole('switch')
  await expect(toggle).toBeVisible()
  await expect(toggle).toHaveAttribute('aria-checked', 'true')

  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'false')

  await page.getByTitle('Volver').click()
  await expect(card.getByRole('button', { name: /Guardados/ })).toBeVisible({ timeout: 8000 })

  // Reactivar para no dejar el flow inactivo entre corridas de test
  await card.getByRole('button', { name: /Guardados/ }).click()
  await card.locator('.flow-row').last().click()
  const reopenedToggle = page.getByRole('switch')
  await expect(reopenedToggle).toHaveAttribute('aria-checked', 'false')
  await reopenedToggle.click()
  await expect(reopenedToggle).toHaveAttribute('aria-checked', 'true')
})

test('Guardar como duplica el flow inactivo con nuevo nombre', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })

  const newName = `Copia de prueba ${Date.now()}`
  page.once('dialog', dialog => dialog.accept(newName))
  await page.getByRole('button', { name: 'Guardar como' }).click()

  // El editor se re-monta mostrando el nuevo flow duplicado
  await expect(page.locator('input[placeholder="Nombre del flow"]')).toHaveValue(newName, { timeout: 8000 })
  const toggle = page.getByRole('switch')
  await expect(toggle).toHaveAttribute('aria-checked', 'false')

  await page.getByTitle('Volver').click()
  await expect(card.getByRole('button', { name: /Guardados/ })).toBeVisible({ timeout: 8000 })
  await card.getByRole('button', { name: /Guardados/ }).click()
  await expect(card.getByText(newName)).toBeVisible()
})

// ─── Panel de Ayuda (JsonNodeEditor): campos, opciones y copiar al portapapeles ─

// Agrega un nodo LLM nuevo (siempre tiene campos con "options", como model/output)
// y lo deja seleccionado, con el panel de config abierto.
// Devuelve el contenedor del panel de Ayuda para escopar los selectores y no
// pisarse con el texto del editor JSON de arriba (que puede repetir "model", etc).
async function addAndSelectLlmNode(page) {
  await page.getByRole('button', { name: '+ Nuevo nodo' }).click()
  const picker = page.getByTestId('node-picker')
  await picker.getByPlaceholder('Buscar nodo...').fill('llm')
  await picker.getByText('llm', { exact: true }).click()
  await expect(picker).not.toBeVisible()

  // addNode() no selecciona el nodo solo: hay que abrirlo con doble clic, como en el resto de los tests
  await page.locator('.react-flow__node').last().dblclick()
  await expect(page.getByTitle('Editar nombre del nodo')).toBeVisible({ timeout: 5000 })

  const ayudaHeader = page.getByText('AYUDA', { exact: true })
  await expect(ayudaHeader).toBeVisible()
  return ayudaHeader.locator('..')
}

test('panel de ayuda muestra header AYUDA con campos y opciones', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })
  const ayuda = await addAndSelectLlmNode(page)

  await expect(ayuda.getByText('model', { exact: true })).toBeVisible()
  // Opciones del campo "model" (best:<categoria>|<estrategia>)
  await expect(ayuda.getByText('best:instruction — local', { exact: true })).toBeVisible()
})

test('clic en una opción de Ayuda la copia al portapapeles', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })
  const ayuda = await addAndSelectLlmNode(page)

  await ayuda.getByText('best:instruction — local', { exact: true }).click()
  const clipboard = await page.evaluate(() => navigator.clipboard.readText())
  expect(clipboard).toBe('best:instruction|local')
})

test('clic en el nombre de un campo de Ayuda lo copia al portapapeles', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })
  const ayuda = await addAndSelectLlmNode(page)

  await ayuda.getByText('model', { exact: true }).click()
  await expect(ayuda.getByText('✓ copiado')).toBeVisible()
  const clipboard = await page.evaluate(() => navigator.clipboard.readText())
  expect(clipboard).toBe('model')
})

test('el divisor entre editor y ayuda es arrastrable y ambos llenan el panel', async ({ page }) => {
  const card = await goToFlowTab(page)
  await clickFlowEdit(card)
  await expect(page.getByRole('button', { name: '+ Nuevo nodo' })).toBeVisible({ timeout: 8000 })
  const ayuda = await addAndSelectLlmNode(page)

  const ayudaBoxBefore = await ayuda.boundingBox()
  // El panel de config también tiene un handle de resize horizontal con el mismo title;
  // el de Ayuda (vertical, dentro del editor JSON) es el segundo en el DOM.
  const handle = page.getByTitle('Arrastrar para redimensionar').last()
  const handleBox = await handle.boundingBox()

  await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y - 100)
  await page.mouse.up()

  await expect(async () => {
    const ayudaBoxAfter = await ayuda.boundingBox()
    expect(ayudaBoxAfter.height).toBeGreaterThan(ayudaBoxBefore.height + 50)
  }).toPass({ timeout: 5000 })
})
