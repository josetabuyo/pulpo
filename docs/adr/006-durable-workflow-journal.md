# ADR-006: Flow executions como durable workflows con journal en DB

**Estado:** Decidido — implementación pendiente

## Contexto

Hoy `run_flows()` ejecuta un flow de punta a punta en memoria. No queda registro
de qué camino tomó un nodo router, qué estado tenía al entrar a cada nodo, ni si
hubo errores. Cuando salta un bug, el debug es ciego.

Además, la arquitectura actual no puede pausar un flow a mitad de camino para esperar
un evento externo (un mensaje de aprobación por Telegram, una respuesta por email).
Eso requeriría persistir el estado entre eventos.

## Decisión

Cada ejecución de flow tiene un `run_id`. Cada nodo loguea su ejecución en SQLite.
El estado del flow (FlowState) se serializa como JSON al entrar y salir de cada nodo.

### Schema

```sql
-- Una fila por ejecución de flow
CREATE TABLE flow_runs (
  run_id        TEXT PRIMARY KEY,   -- UUID generado al iniciar
  flow_id       TEXT NOT NULL,
  bot_id        TEXT NOT NULL,
  connection_id TEXT,
  started_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  ended_at      DATETIME,
  status        TEXT DEFAULT 'running',  -- running | completed | waiting_gate | error
  trigger_data  TEXT                     -- FlowState inicial serializado como JSON
);

-- Una fila por nodo ejecutado dentro de una run
CREATE TABLE flow_run_steps (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        TEXT NOT NULL REFERENCES flow_runs(run_id),
  node_id       TEXT NOT NULL,
  node_type     TEXT NOT NULL,   -- router, llm, reply, fetch, gate, ...
  started_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  ended_at      DATETIME,
  input_state   TEXT,            -- FlowState al entrar al nodo (JSON)
  output_state  TEXT,            -- FlowState al salir del nodo (JSON)
  branch_taken  TEXT,            -- para nodos router: qué rama eligió
  status        TEXT DEFAULT 'ok'  -- ok | skipped | error | waiting
);
```

### Qué habilita

1. **Debug visual**: dado un `run_id`, reconstruir el grafo de ejecución con nodos
   coloreados por status (ok/error/waiting) y el JSON de entrada/salida de cada nodo.
   El frontend ya tiene React Flow — es reutilizar el canvas existente.

2. **Gates bloqueantes** (flows multi-canal, multi-paso):
   ```
   [WA trigger] → [LLM presupuesto] → [gate: esperar aprobación TG]
                                              ↓ (cuando llega "apruebo" por TG)
                                      → [send_email PDF] → [reply WA]
   ```
   El gate serializa el FlowState a DB con `status=waiting`. Cuando llega el
   evento externo, el trigger correspondiente busca si hay una run esperando
   esa señal y la reanuda desde ese step con el mismo `run_id`.

3. **Auditoría completa**: qué rama tomó el router, qué respondió el LLM, qué
   buscó el fetch, qué envió el reply. Todo legible sin tocar logs.

### Flujo de un gate

```python
# Al llegar a un nodo gate
await db.upsert_flow_step(run_id, node_id, status="waiting", input_state=state)
await db.update_flow_run(run_id, status="waiting_gate")
return  # el flow "se duerme" — la coroutine termina

# Cuando llega el evento externo (otro canal)
step = await db.find_waiting_gate(gate_type="telegram_approval", flow_id=flow_id)
if step:
    state = FlowState.from_json(step.input_state)
    # continuar el flow desde el nodo siguiente al gate
    await run_flows_from(state, run_id=step.run_id, resume_from=step.node_id)
```

## Implementación actual del nodo gate (in-memory, 2026-07-01)

El nodo `gate` implementado usa un dict global en módulo (`_GATE_STORE`) para
acumular mensajes entre ejecuciones BFS. **Este modelo es consciente y temporal:**

### Comportamiento actual
- `_GATE_STORE` persiste en proceso mientras el backend esté corriendo.
- Clave: `(node_id, contact_phone)` — independiente por contacto y por gate.
- Cuando el gate bloquea: `flow_run.status = "waiting_gate"`, el step se loguea como `"blocked"`.
- Cuando el gate abre: `state.data["gate_messages"] = [msg1, msg2, ...]`.

### Restricciones conocidas (a anotar antes de usar en producción compleja)

1. **Se pierde en reinicio**: launchd puede reiniciar el backend. Un gate a medio
   llenar pierde su contador silenciosamente. Para el caso de uso actual (2 triggers
   simultáneos → gate) esto es tolerable; para esperas de horas, no.

2. **Nodos previos al gate re-ejecutan**: el segundo trigger arranca un BFS completo
   desde su entry point. Si hay nodos entre el trigger y el gate, esos nodos se
   ejecutan dos veces (una por cada trigger). **Diseño recomendado:** los nodos que
   producen efectos de lado (LLM, send_message, fetch) deben estar DESPUÉS del gate,
   no antes. Los triggers apuntan directamente al gate.

3. **Memory leak**: gates que nunca completan (contact que envía un mensaje y no manda
   el segundo) quedan en `_GATE_STORE` para siempre. Pendiente: job de GC con TTL.

4. **Sin multi-proceso**: si el backend escala a múltiples workers, el store no se
   comparte. El modelo durable (DB) del ADR resuelve esto.

### Migración al modelo durable (cuando se necesite)
El modelo durable del ADR (serializar FlowState a DB con `status=waiting` y reanudar
desde el step siguiente al gate) reemplaza `_GATE_STORE` sin cambiar la interfaz del
nodo — el compilador absorbería el cambio. El nodo gate en sí no cambia.

## Lo que NO resuelve este ADR (pendiente futuro)

- **Identidad unificada entre canales**: si WA tiene `+549...` y TG tiene `@username`,
  vincular que son la misma persona. No es necesario para la primera implementación
  de gates — el gate puede esperar "cualquier aprobación" del flow, no de una persona
  específica.

- **Timeout y garbage collection**: flows con gates abiertos que nunca se resuelven.
  Requiere un job de limpieza periódico.

## Consecuencias para la arquitectura actual

- `run_flows()` en `pulpo/graphs/compiler.py` recibe opcionalmente un `run_id`.
  Si no se pasa, genera uno nuevo. Loguea cada step antes y después de ejecutar cada nodo.
- Los nodos no cambian su interfaz — el logging lo hace el compilador, no el nodo.
- `core/state.py` (dict global de sesiones en memoria) se reemplaza progresivamente
  por `flow_runs` en DB — el estado sobrevive reinicios.
- El dashboard puede mostrar una vista "Ejecuciones" que lista `flow_runs` y permite
  abrir cualquiera y ver el grafo de esa ejecución.
