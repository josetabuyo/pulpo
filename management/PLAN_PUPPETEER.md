# Plan: Automatización de Browser con Puppeteer/Playwright

## Estado actual

`whatsapp-web.js` usa Puppeteer internamente para controlar Chrome y mantener la sesión de WhatsApp Web. Nosotros no tocamos Puppeteer directamente — lo hace la librería por nosotros. Eso nos da WhatsApp gratis, pero nos deja ciegos y sin control sobre el browser.

---

## Por qué tomar control directo

Hoy usamos el browser solo para conectar WhatsApp (escanear QR al setup). Pero el mismo browser que ya tenemos corriendo puede hacer mucho más:

- **Web scraping** como feature para los clientes
- **Automatizaciones web** programables: llenar formularios, consultar portales, extraer datos
- **Integración con flujos del bot**: el bot recibe un mensaje → dispara una acción en un sitio web → responde con el resultado

Esto convierte al bot en un agente con capacidad de actuar en la web, no solo de responder mensajes.

---

## Decisión de arquitectura tomada ✅

**Opción B — Control del browser en Python con Playwright.**

- Playwright (Python) en lugar de Puppeteer (Node.js)
- El backend Python orquesta automatizaciones web y agentes de IA
- `BrowserAutomation` como clase base genérica; `WhatsAppSession` como subclase

---

## Lo que se implementó en este worktree ✅

### Sesión persistente con `launch_persistent_context`
- Reemplazamos `browser.new_context()` + `storage_state()` (solo guardaba cookies/localStorage) por `playwright.chromium.launch_persistent_context(user_data_dir)`.
- El perfil Chrome completo (cookies, localStorage, IndexedDB, Service Workers) se preserva en `data/sessions/{session_id}/profile/`.
- **Resultado**: al reiniciar el backend, la sesión se restaura sin pedir QR.

### Detección de mensajes nuevos
- El bot no usa webhooks de WA — detecta cambios en el sidebar de WA Web.
- `_poll_open_chat`: tarea asyncio que cada 3s evalúa JS en la página WA y lee los previews de todos los chats visibles (`role="grid"` → `role="row"` → `span[title]`).
- Deduplicación con `seen_pairs: set[(name, body)]` — cada par (nombre, texto) se procesa una sola vez.
- Loop prevention en `_on_message`: si el body es idéntico al auto-reply, se ignora.
- Soporte para "Message yourself": el self-chat no tiene badge de no leídos pero sí preview en sidebar — funciona correctamente.

### Envío de respuestas automáticas (sin nueva pestaña)
- El approach original (`context.new_page()` con URL `?phone=...`) abría una segunda tab que WA detectaba y mostraba "Usar aquí" — lo cual rompía la sesión.
- **Solución**: click real de Playwright en el span del sidebar (`page.locator(f"span[title='{phone}']").click()`) para abrir el chat, luego `keyboard.type()` + Enter en el compose box.
- No navega fuera de la página principal, no abre pestañas nuevas.

### Desconexión limpia desde la UI
- Endpoints `POST /disconnect/{session_id}` y `POST /disconnect-all` (require admin).
- Botón "Desconectar" en el dashboard — cierra el contexto Chromium del bot sin tocar el browser del MCP ni borrar el perfil en disco.

### Deduplicación entre detectores
- Tanto el JS listener (`pollSidebar`) como el Python `_poll_open_chat` pueden detectar el mismo mensaje.
- `recent_msgs: set[(name, body)]` en `_on_message` con TTL de 60s — el mensaje se procesa una sola vez.

---

## Casos de uso como features para clientes

| Feature | Descripción |
|---------|-------------|
| **Consulta de estado** | El bot consulta un portal web (ej: estado de un pedido, turno médico) y responde al cliente |
| **Scraping de precios** | El bot extrae precios o disponibilidad de un sitio y los informa |
| **Formulario automatizado** | El bot completa un formulario online en nombre del cliente |
| **Notificación por cambio** | Monitoreo de una página: si cambia algo, el bot avisa al cliente |

---

## Pendientes / próximos pasos

### Auto-conexión al arrancar el backend
Hoy el browser Playwright se lanza al inicio del backend, pero las sesiones de WA solo se conectan cuando el admin hace click en "Vincular QR" desde la UI.

**Comportamiento deseado**: si ya existe un perfil guardado en `data/sessions/{id}/profile/`, el backend debería intentar restaurar la sesión automáticamente al arrancar, sin esperar intervención humana. Si la sesión está vigente, el bot queda operativo de inmediato. Solo si la sesión expiró (WA Web pide QR de nuevo) se notifica al admin para que escanee.

**Beneficio**: operación sin fricción en producción — reiniciar el servidor no requiere ninguna acción manual.

### Fase de prueba (no borrar docs hasta completarla)
La documentación actual se mantiene hasta terminar la validación en producción con clientes reales.

---

*Documento vivo. Se actualiza a medida que avanza la implementación.*
