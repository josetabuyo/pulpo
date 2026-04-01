# Plan: Recuperar mensajes perdidos al reconectar WA Web

## Problema

Cuando la red cae (Mac en suspensión, cambio de WiFi, etc.), el WebSocket de WhatsApp Web se desconecta. Los mensajes que llegan durante esa ventana **no disparan el observer JS** porque la página estaba sin conexión. Al reconectar, WA Web los muestra en el chat pero el bot nunca los procesa.

Hoy esto es invisible — el monitor solo muestra el WARNING de "WebSocket desconectado" pero no hay forma de saber si se perdió algo. El usuario lo descubrió porque esperaba respuesta y no llegó.

---

## Solución propuesta: scan de no leídos al reconectar

### Idea central

Cuando el WebSocket reconecta (la página vuelve a estar online), hacer un barrido de los chats con badge de no leídos y procesar los mensajes que el observer se haya perdido.

WA Web muestra los badges de no leídos en el sidebar (círculos con número). Ya tenemos infraestructura para leer eso — el `_poll_open_chat` lo hace parcialmente.

### Flujo propuesto

```
WebSocket cae → WARNING en el log
        ↓
WebSocket reconecta (página vuelve online)
        ↓
INFO en el log: "Reconectado — escaneando mensajes perdidos..."
        ↓
Scan de badges en sidebar: encontrar todos los chats con no leídos
        ↓
Para cada chat con no leídos:
  - ¿Es un contacto en allowedContacts?
    - No → ignorar (debug log)
    - Sí → leer los mensajes no leídos, procesarlos
        ↓
Continuar con el observer normal
```

### Detección de reconexión

WA Web expone el estado de la conexión en el DOM. Hay dos formas:

**Opción A — Evento `online` del browser:**
```js
window.addEventListener('online', () => { __waOnReconnect() });
```
El browser dispara `online` cuando la red vuelve. Simple y confiable.

**Opción B — Observer del indicador de conexión de WA Web:**
WA Web muestra un banner "Conectando..." con `data-testid="connection-indicator"`. Observar cuando desaparece.

Recomendada: **Opción A** (más simple, no depende de selectores de WA que pueden cambiar).

### Scan de no leídos

Ya existe lógica similar en `_poll_open_chat`. La diferencia es que este scan es on-demand (solo al reconectar) y más exhaustivo:

```python
async def scan_unread_on_reconnect(self, session_id, bot_id, bot_phone, allowed_contacts, auto_reply):
    """
    Al reconectar, busca chats con no leídos en allowedContacts y los procesa.
    Se llama una sola vez por reconexión.
    """
    page = self.get_page(session_id)
    # 1. Obtener todos los chats con badge de no leídos
    # 2. Filtrar los que están en allowedContacts
    # 3. Para cada uno: abrir → leer mensajes nuevos → procesar → cerrar
```

---

## Qué se loguea (lo importante para el monitor)

| Evento | Nivel | Mensaje |
|---|---|---|
| WebSocket cae | WARNING | `⚠️ WebSocket desconectado — posibles mensajes perdidos` |
| Red vuelve | INFO | `🔄 Red reconectada — escaneando mensajes pendientes...` |
| Mensajes encontrados | INFO | `📨 [contacto] Mensaje pendiente procesado: {body[:40]}` |
| Sin pendientes | INFO | `✅ Sin mensajes perdidos tras reconexión` |
| Error en scan | WARNING | `⚠️ Error al escanear pendientes: {e}` |

---

## Lo que NO se hace

- No se procesan mensajes de contactos fuera de `allowedContacts` (mismo criterio que el observer normal)
- No se re-procesa el historial completo — solo los no leídos al momento de reconectar
- No se usa ninguna API externa de WhatsApp — todo es DOM scraping de WA Web

---

## Orden de implementación

1. Registrar callback `window.online` en `start_listening()` que llama a `__waOnReconnect`
2. Exponer `__waOnReconnect` como función Python via `expose_function`
3. Implementar `scan_unread_on_reconnect()` en `WhatsAppSession`
4. Loguear cada paso según la tabla de arriba
5. Validar con simulación: apagar WiFi → mandar mensaje → prender WiFi → ver que el bot responde

---

## Estado
- [x] Cubierto — `_poll_sidebar_for_delta` (cada 10s) detecta cambios de preview al reconectar + `_startup_delta_sync` captura mensajes perdidos al reiniciar. El evento `window.online` explícito no se implementó pero el resultado es equivalente.
