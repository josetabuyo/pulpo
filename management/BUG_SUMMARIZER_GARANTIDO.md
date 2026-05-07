# BUG: Sumarizador no funciona para Garantido (ni para contactos bootstrapeados)

**Fecha:** 2026-05-07  
**Estado:** ❌ Sin resolver  
**Síntoma:** "✓ 0 contactos sincronizados" al hacer sync-all desde el nodo summarize

---

## Por qué `sync-all` devuelve 0

`sync-all` en `api/summarizer.py:459` hace:
```sql
SELECT DISTINCT phone FROM messages WHERE connection_id = :eid AND outbound = 0
```
donde `:eid` es el `empresa_id` (e.g. `"garantido"`).

Esto es correcto — el handler WA guarda mensajes con `connection_id = empresa_id`  
(ver `automation/whatsapp.py:288`: `log_message(eid, bot_phone, ...)`).

**Pero:** si Andrés Buxareo nunca mandó un mensaje DESPUÉS de que el sistema fuera activado,
la tabla `messages` literalmente no tiene ninguna fila para `connection_id = "garantido"`.
El sistema solo guarda mensajes que pasan `_passes_any_flow_filter` (filtro de seguridad).
El caso de Garantido: el usuario activó el sistema DESPUÉS de que Andrés escribió → 0 mensajes en DB.

---

## La solución: bootstrap por nombre (ya implementada pero sin probar)

Se agregó en esta sesión:

### Backend: `POST /whatsapp/bootstrap-contact`
Archivo: `backend/api/whatsapp.py` línea ~670

Llama a `wa_session.scrape_full_history_v2(session_id, contact_name)` que:
1. Busca el contacto en WA Web sidebar por nombre
2. Raspa mensajes históricos
3. Guarda con `log_message_historic(eid, session_id, contact_name, contact_name, ...)`

**PROBLEMA CONOCIDO:** `phone` se guarda como el nombre del contacto (`"Andrés Buxareo"`) 
en vez de un número real. Esto es inevitable sin conocer el teléfono, pero necesita 
verificarse que `sync-all` y el sumarizador lo manejan bien.

### Frontend: botón `↓ historial`
Aparece en `ContactFilterEditor` para contactos "huérfanos" — los que están en `included[]`
del filtro pero NO están en la tabla `contacts` de DB.

**El botón solo aparece si:**
- El contacto está en la lista CON ESTADO (incluido/excluido)
- No está en la tabla `contacts` de DB (es decir, nunca mandó un mensaje real)
- La conexión tiene un `connection_id` configurado en el nodo trigger

---

## Flujo completo esperado (para que el sumarizador funcione con Andrés)

```
1. En el nodo whatsapp_trigger de Garantido → FILTRO DE CONTACTOS
   → "Andrés Buxareo" aparece en CON ESTADO con botón "↓ historial"
   → Click → llama POST /whatsapp/bootstrap-contact
   → El backend raspa WA Web por nombre y guarda mensajes en DB

2. En el nodo summarize → SYNC HISTÓRICO
   → Click "↓ Sincronizar desde fecha"
   → Llama POST /summarizer/garantido/sync-all
   → Debería encontrar mensajes de "Andrés Buxareo" en DB
   → Crea el .md con el historial
```

---

## Cosas a verificar en la próxima sesión

### 1. ¿El bootstrap corre?
Revisar logs tras hacer click en "↓ historial":
```bash
log_back | grep bootstrap
```
Buscar: `[bootstrap] Iniciando para 'Andrés Buxareo'` y `[bootstrap] 'Andrés Buxareo': N mensajes importados`

Si hay error: `[bootstrap] Error para 'Andrés Buxareo': ...`

### 2. ¿Los mensajes quedan en DB tras el bootstrap?
```bash
qdb "SELECT phone, body, timestamp FROM messages WHERE connection_id='garantido' LIMIT 10"
```
Si vacío → el bootstrap no guardó nada (falló la scrapeada o `log_message_historic` falló)

### 3. ¿`scrape_full_history_v2` encuentra el contacto?
El scraper busca en el sidebar de WA Web por `contact_name`.  
Si el nombre en WA no coincide exactamente con "Andrés Buxareo", no lo encuentra.  
Ver `automation/whatsapp.py` → función `scrape_full_history_v2`.

### 4. ¿`sync-all` los recoge tras el bootstrap?
Tras confirmar que hay mensajes en DB, hacer sync-all y verificar que los cuenta.
Si devuelve 0 con mensajes en DB → hay un bug en la query de sync-all.

---

## Arquitectura del sumarizador (estado actual, mayo 2026)

- Mensajes → `data/summaries/{empresa_id}/{contact_slug}/chat.md`
- `contact_slug` = nombre slugificado (e.g. `andres-buxareo`) o phone como fallback
- `sync-all` reconstruye el .md desde DB (fuente de verdad: tabla `messages`)
- `sync_contact` hace delta sync de un contacto individual
- La UI (tab Sumarizador en EmpresaCard/FlowEditor) lee el `.md` vía API

## Archivos clave
- `backend/api/summarizer.py` — endpoints de consulta y sync
- `backend/graphs/nodes/summarize.py` — lógica de acumulación y lectura de .md
- `backend/api/whatsapp.py:670` — endpoint bootstrap-contact
- `frontend/src/components/ContactFilterEditor.jsx` — botón "↓ historial"
- `frontend/src/components/NodeConfigPanel.jsx` — sección SYNC HISTÓRICO en nodo summarize

## Plan de largo plazo: PLAN_SUMMARIZER_V2.md
Ver ese doc para la arquitectura de carpeta-por-contacto y delta sync periódico.
El V2 aún no está implementado — lo que existe es el flujo básico de sync desde DB.
