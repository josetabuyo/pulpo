# Plan: Google Sheets como conexión + HTTP Trigger

**Estado:** borrador / pendiente de priorizar  
**Fecha:** 2026-04-30

---

## Contexto

Las conexiones actuales (WA, Telegram) son conexiones *activas*: ocupan un proceso, pollan mensajes, tienen conflicto si dos empresas comparten el recurso.

Una cuenta Google de servicio es una conexión *pasiva*: no ocupa recursos, puede ser editora de miles de hojas en simultáneo, no tiene conflicto entre empresas. Esto permite un modelo diferente:

- **Cuenta Pulpo compartida:** Pulpo presta su cuenta → la empresa solo comparte su hoja con el email de Pulpo. Sin configuración.
- **Cuenta propia por empresa:** la empresa crea su propio Service Account → pega el JSON → total autonomía.

Ambos modos conviven en la misma UI de conexiones.

---

## Fase 1 — Google Sheets como conexión (tipo `gsheet`)

### Backend

1. Nuevo tipo de conexión `gsheet` en la tabla `connections` (o en `phones.json`).
2. Al crear: recibe JSON del Service Account → extrae `client_email` → guarda credenciales cifradas.
3. Al listar conexiones de una empresa: incluye las de tipo `gsheet` con `{id, email, label, type: "gsheet"}`.
4. Seed automático: si existe `GOOGLE_SERVICE_ACCOUNT_JSON` en `.env`, registrar como conexión `id="pulpo-default"` disponible para todas las empresas.
5. Endpoint `GET /api/flow/google-accounts` → reemplazar con `GET /api/empresas/{id}/connections?type=gsheet`.

### Frontend — Conexiones UI

- En la tarjeta de empresa, pestaña **Conexiones**, botón **+ Google Sheets**.
- Modal de setup con dos opciones:
  - **Usar cuenta Pulpo:** solo muestra el email a copiar, botón "Confirmar". Sin JSON.
  - **Cuenta propia:** textarea para pegar el JSON del Service Account + validación + instrucciones paso a paso (igual que el flujo de Telegram con el token).
- Instrucciones paso a paso para crear Service Account:
  1. Ir a console.cloud.google.com → APIs → Google Sheets API → Habilitar
  2. Credenciales → Crear cuenta de servicio → Claves → JSON
  3. Pegar el JSON acá
- La conexión creada aparece en la lista con su email, sin botón de QR ni estado de conexión (es pasiva).

### Nodos

- Los campos `google_account` en `gsheet`, `search_sheet`, `fetch_sheet` se convierten en `connection_id` apuntando a una conexión de tipo `gsheet`.
- El dropdown `google_account_select` pasa a usar las conexiones del tipo `gsheet` de la empresa (incluida la cuenta Pulpo compartida).
- El recuadro "Compartir planilla con Pulpo" usa el email de la conexión seleccionada, dinámico.

---

## Fase 2 — HTTP Trigger (trigger genérico desde cualquier sistema)

**Idea central:** un nodo `http_trigger` genera una URL única por flow con un token secreto. Cualquier sistema externo (Google Sheets, formulario, botón en web) puede hacer `POST` a esa URL con datos JSON y activar el flow.

### Caso de uso principal: "botón en Google Sheets"

```
Planilla con columna "Enviar" → macro Apps Script → POST a Pulpo → flow envía WA a cada número
```

Apps Script (3 líneas):
```javascript
function enviarMensaje(fila) {
  var url = "https://pulpo.ngrok.dev/api/trigger/abc123?token=XYZ";
  UrlFetchApp.fetch(url, {method:"post", payload: JSON.stringify({row: fila})});
}
```

### Backend

1. Nuevo nodo `http_trigger` en `NODE_REGISTRY` y `NODE_TYPES`.
2. Endpoint `POST /api/trigger/{flow_id}?token={token}`:
   - Valida el token (guardado en la definición del flow o en DB).
   - Construye un `FlowState` con `vars` = body JSON recibido.
   - Ejecuta el flow en background.
   - Responde `{ok: true}` inmediatamente (no espera).
3. El token se genera al crear el nodo y se guarda en su config.

### Frontend

- El panel del nodo `http_trigger` muestra:
  - **URL del trigger** (copiable) — incluye ngrok URL si está configurada.
  - **Token** (copiable, regenerable).
  - **Snippet de Apps Script** listo para copiar.
  - Variables disponibles: documentar qué llega en `state.vars` según el body.

### Variables en el flow tras el trigger

El body JSON del POST mapea directo a `state.vars`. Ejemplo: si el body es `{"nombre": "Juan", "telefono": "549..."}`, el LLM puede usar `{{vars.nombre}}` y el nodo `send_message` puede enviar a `{{vars.telefono}}`.

---

## Fase 3 — Google Sheets como trigger (polling)

**Idea:** un nodo `gsheet_trigger` que cada N minutos lee filas de una hoja con un estado específico (ej: `estado = "pendiente"`), ejecuta el flow para cada fila, y actualiza la fila a `estado = "procesado"`.

Esto convierte Google Sheets en una **cola de trabajo** o **lista de envíos programados**.

Requiere:
- La cuenta Google debe tener permisos de escritura (para actualizar el estado).
- Un scheduler interno (similar al polling de WA/TG).
- Deduplicación para no procesar la misma fila dos veces.

---

## Orden sugerido de implementación

| Prioridad | Fase | Esfuerzo estimado |
|-----------|------|-------------------|
| 1 | Fase 1: conexiones Google en UI | ~1 sesión |
| 2 | Fase 2: HTTP trigger | ~1 sesión |
| 3 | Fase 3: gsheet_trigger (polling) | ~2 sesiones |

---

## Notas de diseño

- **Seguridad:** el JSON del Service Account es sensible. Guardar cifrado en DB, nunca en el flow definition. El flow solo guarda el `connection_id`.
- **Multiempresa:** la cuenta Pulpo compartida no expone credenciales a las empresas — solo el email de destino para compartir. Las empresas nunca ven el JSON de Pulpo.
- **HTTP trigger y ngrok:** la URL del trigger debe usar `VITE_PUBLIC_URL` (ngrok) cuando está configurada, no localhost. De lo contrario Google Sheets no puede alcanzar Pulpo.
- **Rate limiting:** el endpoint del HTTP trigger debe tener rate limiting por token para evitar abusos.
