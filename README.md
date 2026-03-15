# Bot Farm

Plataforma multi-bot para empresas. Gestiona bots de WhatsApp y Telegram con auto-reply, panel admin y portal de cliente.

## Stack

| Componente  | Tecnología |
|-------------|------------|
| API REST    | FastAPI + uvicorn |
| Frontend    | React + Vite |
| Base de datos | SQLite async (`data/messages.db`) |
| WhatsApp    | Playwright headless (perfil Chrome persistente) |
| Telegram    | python-telegram-bot v21 |

## Arrancar

```bash
./start.sh        # levanta backend + frontend
```

Los puertos se leen del `.env` local de cada worktree. El worktree `_` (master) usa 8000/5173.

## Tests

### Backend
```bash
cd backend
pytest tests/ -v
# requiere: .venv/bin/pip install pytest pytest-asyncio httpx
# requiere: server corriendo
```

### Frontend (Playwright)
```bash
cd frontend
node_modules/.bin/playwright test
```

## Estructura

```
_/
├── backend/
│   ├── main.py              # FastAPI app, lifespan, routers
│   ├── sim.py               # Simulador (activo cuando ENABLE_BOTS=false)
│   ├── state.py             # clients dict + wa_session singleton
│   ├── config.py            # lee phones.json
│   ├── db.py                # SQLite async
│   ├── api/                 # routers: auth, bots, phones, whatsapp,
│   │   │                    #          telegram, messages, sim, client, logs
│   │   └── logs.py          # GET /api/logs/latest y /api/logs/stream
│   ├── automation/
│   │   └── whatsapp.py      # lógica WA Web con Playwright
│   ├── bots/
│   │   └── telegram_bot.py  # bot de Telegram
│   └── tests/               # pytest: auth, logs, sim
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── DashboardPage.jsx   # panel admin
│   │   │   └── ConnectPage.jsx     # portal cliente
│   │   └── components/
│   │       └── MonitorPanel.jsx    # drawer de monitoring en tiempo real
│   └── tests/               # Playwright: login, monitor
├── monitoring.json          # config del panel de monitoring
├── phones.json              # config de bots y teléfonos (gitignoreado)
├── data/                    # DB y sesiones Chrome (gitignoreado)
└── start.sh                 # arranque unificado
```

## Worktrees

Cada feature se desarrolla en su propio worktree (ambiente simulado independiente).
Ver `CLAUDE.md` para el flujo completo.

| Worktree     | Backend | Frontend | Estado     |
|--------------|---------|----------|------------|
| `_` (master) | 8000    | 5173     | Producción |
| dev-1        | 8001    | 5174     | Libre      |
| dev-2        | 8002    | 5175     | Libre      |
