# Bot Farm — Backend Python

Worktree: `arch/python-backend`
Puerto: **8000** (el Node.js sigue en 3000, no hay conflicto)

---

## Arrancar

```bash
cd /Users/josetabuyo/Development/whatsapp_bot/arch/python-backend
start_fastapi_monitor
```

En otra terminal, para seguir el log en tiempo real:
```bash
check_fastapi_monitor
```

> `start_fastapi_monitor` arranca uvicorn desde `backend/` y guarda el output en `monitor/fastapi.log`.
> `check_fastapi_monitor` hace `tail -f` sobre ese archivo desde cualquier directorio.

---

## Verificar que está funcionando

```bash
curl http://localhost:8000/health
# → { "status": "ok", "bots": 1 }
```

---

## Stack

| Componente | Tecnología |
|-----------|-----------|
| API REST | FastAPI + uvicorn |
| Bot Telegram | python-telegram-bot v21 |
| Base de datos | SQLite async (mismo `data/messages.db` que Node.js) |

---

## Estructura

```
arch/python-backend/
├── backend/
│   ├── main.py              # FastAPI app + arranque de bots
│   ├── config.py            # lee phones.json
│   ├── db.py                # SQLite async
│   ├── bots/
│   │   └── telegram_bot.py  # reemplaza telegram.js
│   ├── start.sh             # arranque directo (alternativa al alias)
│   └── requirements.txt
├── monitor/
│   └── fastapi.log          # log del servidor (gitignoreado)
└── management/
    └── PLAN_PYTHON_BACKEND.md
```

---

## Relación con otros worktrees

| Worktree | Puerto | Estado |
|----------|--------|--------|
| `_` (master) | 3000 | producción / estable |
| `fix-watchdog` | 3000 | fix WA en paralelo |
| `arch/python-backend` | **8000** | esta migración |
