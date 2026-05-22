# NEXT_SESSION — feat-gsheet-connections

**Worktree:** `/Users/josetabuyo/Development/pulpo/feat-gsheet-connections`
**Branch:** `feat-gsheet-connections`
**Backend:** http://localhost:8001
**Frontend:** http://localhost:5174
**Modo:** simulado (ENABLE_BOTS=false)

---

## Objetivo

Convertir las cuentas Google de servicio en conexiones de primera clase en Pulpo,
igual que WhatsApp y Telegram. Plan completo en `management/PLAN_GSHEET_CONNECTIONS.md`.

---

## Arrancar

```bash
cd /Users/josetabuyo/Development/pulpo/feat-gsheet-connections
./start.sh
cd backend && pytest tests/ -v
```

---

## Contexto (lo que ya existe en master)

- Nodos `gsheet`, `search_sheet`, `fetch_sheet` funcionan en producción.
- Campo `google_account_select` en NodeConfigPanel lee de `GET /api/flow/google-accounts`.
- Ese endpoint lee solo de `GOOGLE_SERVICE_ACCOUNT_JSON` en `.env` — es lo que hay que reemplazar.
- La cuenta configurada es `pulpo-sheets@booming-monitor-459317-d3.iam.gserviceaccount.com`.
- El `.env` ya tiene `GOOGLE_SERVICE_ACCOUNT_JSON` con el JSON completo.

---

## Fase 1 — Backend: conexiones tipo `gsheet`

### 1a. Modelo en DB

En `backend/db.py`, la tabla `connections` (o donde vivan las conexiones) necesita soporte para `type="gsheet"`.
Revisar primero cómo están modeladas las conexiones WA/TG para seguir el mismo patrón.

Una conexión `gsheet` guarda:
- `type = "gsheet"`
- `empresa_id` — null si es la cuenta compartida de Pulpo
- `credentials_json` — el JSON del Service Account (texto plano por ahora, cifrar en el futuro)
- `email` — extraído de `client_email` del JSON (para mostrar en UI sin exponer las credenciales)
- `label` — nombre amigable (ej: "Cuenta principal Pulpo")

### 1b. Seed automático al arrancar

En `backend/main.py` (lifespan), si `GOOGLE_SERVICE_ACCOUNT_JSON` está en `.env`:
- Si no existe una conexión con `id="pulpo-default"`, crearla.
- Esto hace que la cuenta de Pulpo esté disponible para todas las empresas sin configurar nada.

### 1c. Listar conexiones Google de una empresa

Modificar el endpoint que lista conexiones para incluir las de tipo `gsheet`:
- Las conexiones propias de la empresa (con su `empresa_id`).
- La conexión `pulpo-default` (compartida, sin empresa_id).

### 1d. Reemplazar `/api/flow/google-accounts`

Reemplazar (o hacer que internamente use) las conexiones de tipo `gsheet` de la empresa.
El campo `google_account_select` en los nodos pasa a listar estas conexiones.

---

## Fase 2 — Frontend: UI en EmpresaCard

### 2a. Botón "+ Google Sheets" en la pestaña Conexiones

En `frontend/src/components/EmpresaCard.jsx`, agregar botón junto a "+ WhatsApp" y "+ Telegram".

### 2b. Modal de setup

Dos opciones dentro del modal:

**Opción A — Usar cuenta Pulpo (recomendado):**
- Muestra el email `pulpo-sheets@booming-monitor-459317-d3.iam.gserviceaccount.com` con botón Copiar.
- Instrucción: "Compartí tu Google Sheet con este email como Editor."
- Botón "Confirmar" — no requiere pegar nada.

**Opción B — Cuenta propia:**
- Textarea para pegar el JSON del Service Account.
- Validación: intentar `JSON.parse()` y verificar que tiene `client_email` y `private_key`.
- Instrucciones paso a paso:
  1. Ir a console.cloud.google.com → Biblioteca → "Google Sheets API" → Habilitar
  2. Credenciales → + Crear credenciales → Cuenta de servicio → nombre cualquiera → Crear
  3. Clic en la cuenta → pestaña Claves → Agregar clave → JSON → se descarga el archivo
  4. Pegar el contenido del archivo acá
- Al guardar: `POST /api/empresas/{id}/connections` con `{type: "gsheet", credentials_json: "..."}`.

### 2c. Tarjeta de conexión Google

En la lista de conexiones, la conexión Google aparece como:
- Ícono de Google Sheets (verde).
- Email de la cuenta.
- Label (ej: "Cuenta Pulpo" o el nombre que puso el usuario).
- Sin botón QR ni estado de conexión (es pasiva).
- Botón eliminar (solo para cuentas propias; la de Pulpo no se puede borrar).

---

## Fase 3 — Conectar nodos a conexiones

Los campos `google_account` en `gsheet.py`, `search_sheet.py`, `fetch_sheet.py` ya son de tipo
`google_account_select`. Solo hay que hacer que el selector use las conexiones del backend
en lugar del endpoint separado `/api/flow/google-accounts`.

En `NodeConfigPanel.jsx`, el `useEffect` que carga `googleAccounts` pasa a llamar
a las conexiones de tipo `gsheet` de la empresa.

---

## Archivos clave

- `management/PLAN_GSHEET_CONNECTIONS.md` — plan completo incluyendo Fases futuras (HTTP trigger, polling)
- `backend/db.py` — esquema de conexiones
- `backend/api/connections.py` — CRUD de conexiones (si existe; buscar dónde están)
- `backend/api/flows.py` — endpoint `GET /api/flow/google-accounts` (a reemplazar)
- `frontend/src/components/EmpresaCard.jsx` — UI de conexiones
- `frontend/src/components/NodeConfigPanel.jsx` — campo `google_account_select` ya implementado

---

## No hacer en este worktree

- No tocar la lógica de ejecución de los nodos (ya funciona en prod).
- No implementar HTTP trigger ni gsheet_trigger (están en el plan pero son fases futuras).
- El merge a master lo hace siempre la sesión de `_`.
