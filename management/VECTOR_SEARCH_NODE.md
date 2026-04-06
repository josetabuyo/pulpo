# Vector Search Node

Nodo genérico parametrizado para búsquedas en colecciones registradas.

## Propósito

Reemplaza la lógica hardcodeada del nodo `search` anterior. Permite:
- Buscar en diferentes colecciones (oficios, auspiciantes, etc.)
- Parametrizar qué campo usar como query
- Escribir resultados en campos diferentes
- Registrar nuevas colecciones sin modificar el nodo

## Configuración

| Campo | Tipo | Default | Descripción |
|-------|------|---------|------------|
| `collection` | string | "luganense_oficios" | Nombre de la colección registrada |
| `query_field` | select | "message" | Dónde leer el query: "message" \| "query" \| "context" |
| `output_field` | select | "context" | Dónde escribir el resultado: "context" \| "query" |
| `top_k` | float | 3 | Cantidad máxima de resultados |

## Colecciones disponibles

### `luganense_oficios`

Busca trabajadores por oficio. Handler: `handler_luganense_oficios`

**Input:**
- Query: mensaje del usuario buscando un servicio

**Output (state.vars):**
- `oficio` (str): oficio identificado (ej: "electricista", "otro")
- `worker` (dict | None): datos del trabajador encontrado
- `nombre` (str): nombre del trabajador (vacío si no hay)
- `telefono` (str): teléfono del trabajador (vacío si no hay)
- `text` (str): JSON serializado con oficio y worker

**Output (state.context):**
Igual a `text` si `output_field` es "context"

### `luganense_auspiciantes`

Busca auspiciantes relevantes por tags.

**Input:**
- Query: mensaje del usuario

**Output (state.vars):**
- `nombre` (str): nombre del auspiciante encontrado (vacío si no hay)
- `mensaje` (str): mensaje del auspiciante (vacío si no hay)
- `text` (str): igual a mensaje

**Output (state.context):**
Igual a `text` si `output_field` es "context"

## Ejemplos de uso en flows

### Ejemplo 1: Buscar trabajador por oficio

```json
{
  "id": "search_worker",
  "type": "vector_search",
  "config": {
    "collection": "luganense_oficios",
    "query_field": "message",
    "output_field": "context",
    "top_k": 3
  }
}
```

El nodo:
1. Lee el mensaje del usuario (`state.message`)
2. Interpola placeholders si existen
3. Llama al handler `luganense_oficios(query, 3, empresa_id)`
4. Escribe en `state.vars`: `oficio`, `worker`, `nombre`, `telefono`, `text`
5. Escribe en `state.context` el JSON serializado

### Ejemplo 2: Buscar auspiciante después de router

```json
{
  "id": "search_sponsor",
  "type": "vector_search",
  "config": {
    "collection": "luganense_auspiciantes",
    "query_field": "message",
    "output_field": "context"
  }
}
```

Nodos posteriores pueden acceder a `{{nombre}}` y `{{mensaje}}` en placeholders.

### Ejemplo 3: Query expandida

```json
{
  "id": "search_worker",
  "type": "vector_search",
  "config": {
    "collection": "luganense_oficios",
    "query_field": "query",
    "output_field": "context"
  }
}
```

Útil después de un nodo LLM que expande la query:
```
message: "necesito ayuda"
         ↓ [LLM]
query:   "Estoy buscando un electricista para reparar un tomacorriente"
         ↓ [VectorSearchNode]
context: JSON con oficio="electricista", worker={...}
```

## Arquitectura: Registry de colecciones

### Registrar una nueva colección

```python
# En graphs/collections/tu_modulo.py
from . import register_collection

@register_collection("tu_coleccion")
async def handler_tu_coleccion(query: str, top_k: int, empresa_id: str) -> dict:
    """
    Busca en tu colección.

    Returns:
        dict con las keys que desees: nombre, mensaje, score, etc.
        Una de ellas será "text" (el texto principal a mostrar).
    """
    # Tu lógica de búsqueda
    resultado = buscar(query, empresa_id)
    return {
        "nombre": resultado.nombre,
        "score": resultado.score,
        "text": f"{resultado.nombre} (score: {resultado.score})",
    }

# En graphs/collections/__init__.py
from .tu_modulo import register_handlers_tu_coleccion
register_handlers_tu_coleccion()
```

### Cómo funciona

1. El nodo `vector_search` recibe configuración con `collection: "tu_coleccion"`
2. Llama a `get_handler("tu_coleccion")` que busca en `COLLECTION_REGISTRY`
3. Si existe, la llama con `(query, top_k, empresa_id)`
4. El handler retorna un `dict`
5. El nodo escribe todas las keys en `state.vars`
6. El nodo escribe `dict.get("text")` o serializa el dict en `state.context` o `state.query`

## Comportamiento ante errores

- **Sin collection:** loguea warning, retorna state sin modificar
- **Handler no existe:** loguea warning, retorna state sin modificar
- **Handler falla:** loguea error, retorna state sin modificar (no rompe el flow)
- **Query vacío:** loguea warning, retorna state sin modificar

## Placeholders disponibles

El nodo interpola placeholders en el query usando `interpolate()`:

```
{{message}}       — mensaje original del usuario
{{query}}         — query expandida (de nodo LLM anterior)
{{context}}       — contexto acumulado (de fetch/search anterior)
{{contact_name}}  — nombre del contacto
{{contact_phone}} — teléfono del contacto
{{bot_name}}      — nombre del bot
{{empresa_id}}    — ID de la empresa
{{canal}}         — "whatsapp" | "telegram"
```

Ejemplo:
```json
{
  "config": {
    "collection": "luganense_oficios",
    "query_field": "message"
  }
}
```

Si el usuario envía "Necesito un {{canal}} reparador" → busca "Necesito un whatsapp reparador"

## Compatibility

- Mantiene compatibilidad con el nodo `search` anterior (mismo tipo, misma lógica)
- Handlers de Luganense wrappean la lógica existente sin modificarla
- No hay breaking changes para flows existentes

## Testing

Tests unitarios en `backend/tests/test_vector_search.py`:
- Config schema válido
- Manejo de colecciones faltantes
- Interpolación de placeholders
- Escritura en `state.vars` y `state.context`
- Handlers registrados y callable
