# NEXT SESSION — multi-empresa connection dispatch

## Contexto

Estás en el worktree `multi-empresa` (puerto backend: 8001, frontend: 5174).
`ENABLE_BOTS=false` — usás el simulador, no hay bots reales.

El usuario dirá solo "dale!" para que arranques. Trabajá de forma **completamente autónoma**.
Usá `say -v "Paulina" "..."` para anunciar cada avance importante en voz alta (frases cortas).

---

## Problema a resolver

Cuando llega un mensaje a una conexión WA/TG, el sistema solo loguea el mensaje bajo el
`bot_id` dueño de la sesión. Si esa misma conexión está registrada en otras empresas, ellas
nunca ven el mensaje ni evalúan sus herramientas.

**Archivo del plan:** `management/PLAN_CONEXIONES_MULTI_EMPRESA.md` — leelo primero.

---

## Archivos clave a modificar

### `backend/automation/whatsapp.py` — función `_on_message` (línea ~253)
```python
# HOY — solo loguea bajo el dueño de la sesión:
msg_id = await log_message(bot_id, bot_phone, phone or name, name, body)

# FIX — loguar bajo todas las empresas con esta conexión:
from config import get_empresas_for_bot
empresa_ids = get_empresas_for_bot(bot_id)
msg_ids = {}
for eid in empresa_ids:
    mid = await log_message(eid, bot_phone, phone or name, name, body)
    msg_ids[eid] = mid
# Y más abajo, mark_answered para todos:
# for mid in msg_ids.values(): await mark_answered(mid)
```

### `backend/sim.py` — función `sim_receive` (línea ~112)
```python
# HOY:
msg_id = await log_message(cfg["bot_id"], session_id, from_phone, from_name, text)

# FIX — mismo patrón multi-empresa
```

### Telegram handler
Buscar en `backend/automation/telegram.py` o similar si tiene el mismo patrón y aplicar el fix.

---

## Orden de trabajo

1. **Correr tests existentes** — `cd backend && pytest tests/ -v` — ver qué pasa
2. **Leer** `backend/sim.py` completo y `backend/automation/whatsapp.py` función `_on_message`
3. **Implementar** Fase 1 (`whatsapp.py`) + Fase 2 (`sim.py`) + Fase 3 (Telegram si aplica)
4. **Agregar test** en `tests/test_sim.py`: misma conexión en dos empresas → ambas reciben el mensaje
5. **Correr tests** de nuevo — todo verde
6. Anunciar con Paulina: "listo para mergear"

---

## Invariante crítica

`resolve_tool` ya evalúa multi-empresa y devuelve un solo tool (exclusividad garantizada).
No tocar `resolve_tool`. Solo arreglar el logging.

## Merge

El merge a master lo hace la sesión de `_` (producción), no este worktree.
Cuando terminés, anunciá con Paulina y esperá instrucciones.
