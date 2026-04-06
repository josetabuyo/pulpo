# NEXT_SESSION — Framework de nodos (estilo n8n casero)

## Visión
Pulpo Flow = n8n local y propio. Cada nodo es una pieza reutilizable:
cualquier empresa puede armar su flow arrastrando nodos y configurándolos.
Sin código, sin hardcodeo por cliente.

## Estado al 2026-04-05

### Hecho esta sesión
- [x] VectorSearchNode genérico con COLLECTION_REGISTRY
- [x] SendMessageNode reemplaza notify (to="" → usuario, to con valor → TG/WA)
- [x] Flow Luganense migrado en DB: search/notify → vector_search/send_message
- [x] Eliminados search.py y notify.py del registry
- [x] UI: labels descriptivos desde node ID (humanizeId)
- [x] UI: paleta de nodos actualizada con tipos reales
- [x] UI: NodeConfigPanel schema-driven — formulario completo por tipo de nodo
- [x] UI: Sumarizador muestra path + link a resúmenes
- [x] Template default de flow nuevo: solo message_trigger_1 (sin __start__/__end__)

### Nodos actuales en NODE_REGISTRY
| Nodo | Estado | Config |
|------|--------|--------|
| `message_trigger` | ✅ listo | connection_id, contact_phone, message_pattern |
| `router` | ✅ listo | prompt, routes[], fallback, model |
| `llm` | ✅ listo | prompt, model, temperature, output, json_output |
| `send_message` | ✅ listo | to (placeholder), message (placeholder), channel |
| `vector_search` | ✅ listo | collection, query_field, output_field, top_k |
| `fetch` | 🔧 en progreso | source, fb_page_id, fb_numeric_id, url, extract |
| `summarize` | ✅ listo (legacy ok) | sin config — acumula .md por contacto |

---

## PRÓXIMAS TAREAS (en orden)

### 1. FetchNode genérico — fb_page_id + fb_numeric_id 🔧 EN PROGRESO

**Objetivo:** cualquier cliente puede poner su página de Facebook sin tocar código.

Cambios necesarios:
- `backend/nodes/fetch_facebook.py`:
  - `fetch_posts(page_id, query, numeric_id=None)` — acepta numeric_id como param
  - `_search_and_scrape`: usa el `numeric_id` pasado en vez de `_PAGE_NUMERIC_IDS[page_id]`
  - `_SEED_URLS` y `_STATIC_POSTS` quedan como override opcional para Luganense
- `backend/graphs/nodes/fetch.py`:
  - Config: reemplazar `empresa_id` por `fb_page_id` (slug) + `fb_numeric_id` (opcional)
  - `_fetch_facebook`: pasa esos campos a `fetch_posts()`
- `frontend/src/components/NodeConfigPanel.jsx`:
  - Schema del nodo `fetch`: source (select), fb_page_id, fb_numeric_id, url, extract

### 2. Test end-to-end Luganense con simulador

```bash
cd backend && pytest tests/test_sim.py -v   # requiere server en :8001
```
Verificar: mensaje "busco plomero" → buscar_oficio → notificar_trabajador (TG) → responder_vecino_oficio

### 3. Nodo HTTP genérico — config_schema correcto en UI

El source="http" del FetchNode necesita mostrar/ocultar los campos `url` y `extract`
según la selección del select `source` (conditional fields en el panel).

### 4. Deprecar luganense_flow del registry

`luganense_flow` es un mega-nodo legacy que ya no tiene sentido.
Sacarlo de NODE_REGISTRY y PALETTE_TYPES. El flow está en la DB como nodos individuales.

### 5. Config schema desde el backend (futuro)

Hoy el schema de cada nodo está duplicado: Python (config_schema()) y JS (NODE_SCHEMAS).
Solución limpia: exponer GET /api/flow/node-types con el schema completo incluido,
y que el frontend lo consuma dinámicamente. Esto elimina la duplicación.

---

## Arquitectura de referencia

```
message_trigger → router → [rama A] → vector_search → send_message
                          → [rama B] → llm → send_message
                          → [rama C] → fetch → llm → send_message
```

## Skip permissions
claude --dangerously-skip-permissions
