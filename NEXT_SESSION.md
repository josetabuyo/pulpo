# NEXT_SESSION — Refactor de nodos (continuación)

## Estado actual (2026-04-05)

Refactor de arquitectura de nodos completado y pusheado a master.

### Nodos actuales en NODE_REGISTRY
- `message_trigger` — trigger de entrada
- `llm` — llamada LLM (Groq), prompt con {{placeholders}}, output: reply|context|query
- `send_message` — único nodo que envía (to="" → usuario, to con valor → tercero vía TG/WA)
- `vector_search` — búsqueda en colecciones registradas vía COLLECTION_REGISTRY
- `fetch` — fetch externo
- `router`, `search`, `notify` — pendientes deprecar
- `summarize`, `llm_respond` — legacy

### state.vars
FlowState tiene `vars: dict` — nodos escriben valores, interpolate() los resuelve como {{key}}.

### Colecciones registradas
- `luganense_oficios` → state.vars: worker_nombre, worker_telegram_id, worker_whatsapp, oficio
- `luganense_auspiciantes` → state.vars: nombre, text

---

## PRÓXIMAS TAREAS

### 1. Migrar flow Luganense en DB (data/messages.db, tabla flows, name='Luganense')

Rama oficio:
- buscar_oficio: type search → vector_search, config: {"collection": "luganense_oficios"}
- notificar_oficio (notify) → reemplazar por dos nodos:
  - notificar_trabajador: send_message, to: "{{worker_telegram_id}}", message: "🔔 *Nuevo pedido de {{oficio}}*\n\nUn vecino necesita ayuda:\n\n_{{message}}_\n\n¿Podés tomar este trabajo?"
  - responder_vecino_oficio: send_message, to: "", message: "¡Encontramos a alguien! *{{worker_nombre}}* puede ayudarte con tu pedido de {{oficio}} 🙌\nTe va a contactar pronto."
- Edges: buscar_oficio → notificar_trabajador → responder_vecino_oficio

Rama auspiciante:
- buscar_auspiciante: type search → vector_search, config: {"collection": "luganense_auspiciantes"}

### 2. Limpiar registry

- Sacar notify y search del NODE_REGISTRY
- Eliminar backend/graphs/nodes/notify.py y search.py

### 3. Tests + commit + push

backend/.venv/bin/python -m pytest backend/tests/ -q
git add -A && git commit && git push origin master

---

## Skip permissions
claude --dangerously-skip-permissions
