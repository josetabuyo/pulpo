# Plan: Conexiones multi-bot

## Problema

Una misma conexión WA/TG puede estar registrada en varias bots (`phones.json`), pero cuando llega un mensaje:

1. El **logging** solo registra el mensaje bajo el `bot_id` dueño de la sesión WA — las otras bots nunca ven el mensaje.
2. `resolve_tool` ya itera sobre todas las bots correctamente — esa parte está bien.
3. Resultado: si el número `...67` está en `gm_herreria` (sesión activa) y en `test_mxc`, los mensajes llegan a `gm_herreria` solamente.

## Casos de uso que requieren esta fix

- **Test con mi propio número** — agregar mi número a una bot de prueba sin afectar producción.
- **Operador compartido** — un número personal asignado a Bot A para un grupo de contactos y a Bot B para otro grupo.
- **Bot Telegram compartido** — un bot TG respondiendo a distintos grupos según la bot.

---

## Diagnóstico técnico

### `backend/automation/whatsapp.py` — línea 253
```python
msg_id = await log_message(bot_id, bot_phone, phone or name, name, body)
```
Solo loguea bajo `bot_id` (dueño de la sesión). Debe loguearse bajo **todas** las bots que tengan esta conexión.

### `backend/sim.py` — función `resolve_tool`
Ya llama a `get_bots_for_bot(bot_id)` y evalúa herramientas para cada bot. ✅ No necesita cambios.

### `backend/sim.py` — función `sim_receive`
```python
msg_id = await log_message(cfg["bot_id"], session_id, from_phone, from_name, text)
```
Mismo problema en el simulador. Debe loguearse para todas las bots.

---

## Solución

### Cambio 1 — `db.py`: nueva función `log_message_multi_bot`

```python
async def log_message_multi_bot(
    bot_ids: list[str], bot_phone: str, phone: str, name: str | None, body: str
) -> dict[str, int]:
    """Loguea el mismo mensaje bajo cada bot. Retorna {bot_id: msg_id}."""
```

O más simple: hacer que `log_message` existente se llame en un loop desde los puntos de entrada.

### Cambio 2 — `whatsapp.py`: dispatch multi-bot

En `_on_message`:
```python
# Antes:
msg_id = await log_message(bot_id, bot_phone, phone or name, name, body)

# Después:
from config import get_bots_for_bot
bot_ids = get_bots_for_bot(bot_id)
msg_ids = {}
for eid in bot_ids:
    mid = await log_message(eid, bot_phone, phone or name, name, body)
    msg_ids[eid] = mid
```

El `resolve_tool` ya maneja multi-bot y devuelve el tool correcto. La respuesta sigue siendo una sola (exclusividad garantizada).

### Cambio 3 — `sim.py`: mismo fix en `sim_receive`

```python
# Antes:
msg_id = await log_message(cfg["bot_id"], session_id, from_phone, from_name, text)

# Después:
from config import get_bots_for_bot
bot_ids = get_bots_for_bot(cfg["bot_id"])
for eid in bot_ids:
    await log_message(eid, session_id, from_phone, from_name, text)
```

### Cambio 4 — `whatsapp.py`: `mark_answered` multi-bot

```python
if ok:
    for mid in msg_ids.values():
        await mark_answered(mid)
```

### Cambio 5 — Telegram handler (si aplica)
Revisar si el bot TG tiene el mismo patrón y aplicar el mismo fix.

---

## Lo que NO cambia

- El modelo de DB (messages, contacts, tools) — sin migraciones
- La UI — sin cambios en frontend
- La sesión WA — sigue siendo un proceso por número, un Chrome, una sesión
- La validación de exclusividad — ya opera cross-bot
- `resolve_tool` — ya está bien

---

## Invariante de exclusividad

Un par `(conexión, contacto)` solo puede tener UNA herramienta exclusiva activa en toda la DB (cross-bot). Esto garantiza que el dispatch multi-bot no genere respuestas duplicadas: a lo sumo una bot tiene una herramienta activa para ese par.

---

## Tests

### Backend
- `test_sim.py`: agregar caso donde misma conexión está en dos bots → ambas reciben el mensaje en DB
- `test_tools.py`: verificar que exclusividad cross-bot bloquea herramientas en conflicto

### Manual
1. Número `...67` en `gm_herreria` y `test_mxc`
2. Ivancho escribe → mensaje aparece en DB bajo ambas bots
3. Herramienta de `test_mxc` para Ivancho responde "hola ivancho mensaje para ivancho"
4. Herramienta de `gm_herreria` para Ivancho (si existe y es exclusiva) entra en conflicto → validación lo bloquea

---

## Estado

- [x] Fase 1 — Fix `whatsapp.py`: log multi-bot — **completado 2026-03-18**, mergeado a master (commit 1692c94)
- [x] Fase 2 — Fix `sim.py`: log multi-bot en simulador — **completado 2026-03-18**, mergeado a master (commit 1692c94)
- [x] Fase 3 — Fix Telegram handler — revisado, mismo patrón aplicado
- [ ] Fase 4 — Tests actualizados (test_sim.py: caso 2 bots, test_tools.py: exclusividad cross-bot)
- [ ] Fase 5 — Test manual con `test_mxc` + `gm_herreria` compartiendo `...67`

> **Test manual (Fase 5) confirmado funcionando por el usuario en 2026-03-18.** El dispatch multi-bot funciona perfecto en producción.
