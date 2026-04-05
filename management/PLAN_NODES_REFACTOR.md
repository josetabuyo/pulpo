# Plan: refactor de nodos — primitivos genéricos

## Problema actual

Tres nodos tienen cohesión rota — hacen más de una cosa o tienen lógica de dominio hardcodeada:

| Nodo | Problema |
|------|----------|
| `search` | Switch interno `"worker" \| "auspiciante"` — dos búsquedas distintas, acopladas a Luganense |
| `notify` | 4 responsabilidades: parsear contexto, enviar al worker, registrar job en DB, generar reply |
| `reply`  | Solo envía texto al usuario — debería ser un caso particular de `send_message` |

---

## Nodos nuevos / refactorizados

### 1. `vector_search` — reemplaza `search`

**Una responsabilidad:** busca en una colección vectorial y escribe los resultados en un campo del state.

```
Config:
  collection:   str  — nombre de la colección ("luganense_oficios", "luganense_auspiciantes", ...)
  query_field:  str  — de dónde tomar el query: "message" | "query" | "context"  (default: "message")
  output_field: str  — dónde escribir el resultado:  "context" | "query"          (default: "context")
  top_k:        int  — cantidad de resultados (default: 3)
```

El mismo nodo, dos usos en Luganense:
- `collection: "luganense_auspiciantes"` → busca el auspiciante relevante
- `collection: "luganense_oficios"` → busca el trabajador disponible

**Migración de `search`:** el nodo actual queda como alias en el registry hasta que todos los flows estén migrados.

---

### 2. `send_message` — reemplaza `reply` y absorbe el envío de `notify`

**Una responsabilidad:** envía un mensaje a un destinatario vía WA o Telegram.

```
Config:
  to:      str  — destinatario. Vacío = usuario de la conversación.
                  Soporta placeholders: "{{worker_telegram_id}}", "{{contact_phone}}", etc.
  message: str  — texto con placeholders: "Hola {{contact_name}}, ..."
  channel: str  — "auto" | "telegram" | "whatsapp"  (default: "auto")
```

**Dos usos, un solo nodo:**
- `to: ""` + `message: "{{context}}"` → responde al usuario (equivalente al `reply` actual)
- `to: "{{worker_telegram_id}}"` + `message: "Nuevo pedido: {{message}}"` → notifica al worker

**Migración de `reply`:** `reply` queda en el registry como alias de `send_message` con `to: ""`.

---

### 3. `notify` → deprecar

Una vez migrado el flow de Luganense, `notify` desaparece.
El job en DB (`create_job`) queda pendiente para un nodo `db_write` futuro.

---

## Cómo queda el flow Luganense

### Rama `auspiciante` (hoy)
```
search (auspiciante) → llm (responder_auspiciante)
```

### Rama `auspiciante` (después)
```
vector_search (collection: luganense_auspiciantes) → llm (responder_auspiciante)
```

---

### Rama `oficio` (hoy)
```
search (worker) → notify
```

### Rama `oficio` (después)
```
vector_search (collection: luganense_oficios)
  → send_message (to: {{worker_telegram_id}}, message: "🔔 Nuevo pedido: {{message}}")
  → send_message (to: "", message: "¡Encontramos a *{{worker_nombre}}*! Te va a contactar pronto.")
```

---

## Estado de FlowState — campos a agregar

Para que `send_message` pueda resolver `{{worker_telegram_id}}` y `{{worker_nombre}}`, el nodo `vector_search` tiene que escribir esos valores en el state cuando los encuentra.

Opciones:
- **a)** `vector_search` escribe JSON en `state.context` y los placeholders se resuelven parseando ese JSON
- **b)** `FlowState` tiene un dict `state.vars: dict[str, str]` para valores arbitrarios que los nodos producen y los placeholders resuelven

La opción **b** es más limpia a largo plazo: `{{worker_nombre}}` resuelve `state.vars["worker_nombre"]`, independiente del formato del context.

---

## Orden de implementación

1. `send_message` node — es el que desbloquea enviar al worker y deprecar `reply`
2. `vector_search` node — requiere decidir el vector store a usar (ChromaDB, SQLite-vec, etc.)
3. Migrar flow Luganense en DB para usar los nuevos nodos
4. Deprecar `notify`, `search`, `reply` del registry (mantener aliases)
5. `db_write` node — para cuando se retome el registro de jobs

---

## Lo que NO toca este plan

- Interfaz gráfica de configuración de nodos (NodeConfigPanel — Fase 2 del editor)
- Autenticación / permisos de flows
- Multi-turno / historial de conversación
