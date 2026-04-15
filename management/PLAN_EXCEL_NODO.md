# Plan: Nodo de Planilla Excel / Google Sheets

## Objetivo

Permitir que un flow use datos de una planilla (Excel o Google Sheets) como fuente de información en lugar de listas hardcodeadas en la config del nodo. Útil para catálogos de productos, listas de precios, FAQs, contactos de referencia, etc.

---

## Casos de uso concretos

- Un router que decide la ruta basándose en si el producto mencionado está en el catálogo
- Un nodo LLM que recibe el catálogo de precios como contexto para responder consultas
- Un nodo de búsqueda que filtra contra una lista de clientes VIP
- Reemplazar listas hardcodeadas en `contact_filter` por una planilla dinámica que el cliente edita sin tocar el flow

---

## Diseño del nodo

### `fetch_sheet`

Descarga o lee una planilla y vuelca su contenido en `state.context` (para que el LLM lo use) o en `state.vars["sheet_data"]` (para que otros nodos lo inspeccionen).

```json
{
  "source": "google_sheets",
  "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
  "range": "A1:D50",
  "output": "context",
  "format": "markdown_table"
}
```

#### Parámetros

| Campo | Tipo | Descripción |
|---|---|---|
| `source` | select | `google_sheets`, `excel_url`, `csv_url` |
| `sheet_id` | string | ID de la hoja (Google) o URL del archivo |
| `range` | string | Rango A1:D50 (Google) o nombre de hoja (Excel) |
| `output` | select | `context` (para LLM), `vars.sheet_data` (para lógica) |
| `format` | select | `markdown_table`, `json`, `plain_text` |
| `cache_minutes` | number | Tiempo de caché en memoria. 0 = sin caché |

---

## Fuentes soportadas

### Google Sheets (Fase 1)
- Leer con Google Sheets API v4 o con URL pública exportada como CSV:
  ```
  https://docs.google.com/spreadsheets/d/{ID}/export?format=csv&range={RANGE}
  ```
- No requiere auth si la hoja es pública ("cualquiera con el enlace puede ver")
- Auth de servicio para hojas privadas (Fase 2)

### Excel / CSV por URL (Fase 1)
- `httpx.get(url)` → parsear con `openpyxl` o `pandas`
- Soporta `.xlsx`, `.csv`

### Archivo local (Fase 2)
- Subida desde el panel de empresa → guardado en `data/sheets/{empresa_id}/{nombre}.xlsx`
- El nodo referencia el archivo por nombre

---

## Caché

Las planillas no cambian con cada mensaje. El nodo cachea el contenido en memoria:

```python
_sheet_cache: dict[str, tuple[str, float]] = {}  # key → (content, timestamp)
```

Si `cache_minutes > 0` y el contenido en caché tiene menos de `cache_minutes` minutos → usar caché.
Si no → descargar de nuevo.

Esto evita llamadas HTTP en cada mensaje con planillas que cambian poco.

---

## Integración con otros nodos

### Patrón típico: fetch_sheet → llm

```
Trigger → fetch_sheet (catálogo → context) → LLM ("Usá el catálogo: {context}")
```

### Patrón: fetch_sheet → check_contact mejorado

En el futuro, `check_contact` podría comparar el contacto contra la lista de la planilla en lugar de solo la DB interna.

---

## Fases de implementación

### Fase 1 — Google Sheets y CSV públicos (MVP)
- Nodo `fetch_sheet` con fuente `google_sheets` (URL pública como CSV) y `csv_url`
- Output a `state.context` o `state.vars["sheet_data"]`
- Caché en memoria configurable
- Registro en NODE_REGISTRY + paleta frontend

### Fase 2 — Excel upload + hojas privadas
- Endpoint de subida de archivos Excel por empresa
- Panel en EmpresaCard para gestionar planillas subidas
- Auth Google (Service Account) para hojas privadas

### Fase 3 — Nodo de búsqueda en planilla
- `search_sheet`: busca una fila por valor en columna X, devuelve la fila como vars
- Útil para: "dado el número de cliente, traer su nombre y descuento"

---

## Archivos a crear/modificar

```
backend/graphs/nodes/fetch_sheet.py   — nuevo nodo
backend/graphs/node_types.py          — agregar tipo fetch_sheet
backend/graphs/nodes/__init__.py      — registrar
frontend/src/store/flowStore.js       — paleta + default config
```

---

## Estado

- [ ] Fase 1 — fetch_sheet con Google Sheets público y CSV
- [ ] Fase 2 — Excel upload + hojas privadas
- [ ] Fase 3 — search_sheet
