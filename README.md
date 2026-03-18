# 🐙 Pulpo

**Automatizá la atención de tu negocio por WhatsApp y Telegram.**

Pulpo conecta tus canales de mensajería a un sistema de bots inteligentes: respuesta automática, historial de conversaciones y gestión desde un portal propio. Sin código, sin complicaciones.

---

## ✨ ¿Qué hace Pulpo?

- **Respuesta automática** — tu bot responde al instante cuando no estás disponible
- **Multi-canal** — WhatsApp y Telegram desde un solo lugar
- **Portal de empresa** — cada cliente gestiona sus canales, ve conversaciones y responde inline
- **Panel admin** — control total: agregar empresas, ver estado de bots, monitorear en tiempo real

---

## 🚀 Empezar ahora

Accedé al portal público:

**[https://unbuoyant-surgeless-micheal.ngrok-free.dev/empresa](https://unbuoyant-surgeless-micheal.ngrok-free.dev/empresa)**

- ¿Ya tenés una cuenta? Ingresá con tu clave de empresa.
- ¿Primera vez? → **[Crear empresa nueva](https://unbuoyant-surgeless-micheal.ngrok-free.dev/empresa/nueva)**

---

## 📲 Conectar Telegram paso a paso

Para agregar un bot de Telegram a tu empresa en Pulpo:

### 1. Crear el bot en Telegram

1. Abrí Telegram y buscá **@BotFather**
2. Enviá `/newbot`
3. Elegí un nombre para tu bot (ej: `Soporte Herrería`)
4. Elegí un username (debe terminar en `bot`, ej: `herreria_soporte_bot`)
5. BotFather te va a dar un **token** con este formato:
   ```
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```
6. Guardalo — lo vas a necesitar en el paso siguiente

### 2. Agregar el bot a Pulpo

1. Entrá a tu portal: [https://unbuoyant-surgeless-micheal.ngrok-free.dev/empresa](https://unbuoyant-surgeless-micheal.ngrok-free.dev/empresa)
2. En la sección **Telegram**, pegá el token en el campo y hacé click en **+ Agregar**
3. Listo — el bot ya está activo y respondiendo

### 3. Activar el bot

Compartí el link de tu bot (`t.me/herreria_soporte_bot`) con tus clientes. Cuando te escriban, Pulpo:
- Responde automáticamente con tu mensaje configurado
- Registra la conversación en tu portal
- Te permite responder manualmente desde el chat inline

---

## 📱 Conectar WhatsApp

1. En la sección **WhatsApp** del portal, ingresá tu número (formato internacional sin `+`, ej: `5491155612767`)
2. Click en **+ Agregar** → aparece un código QR
3. En tu WhatsApp móvil: **Dispositivos vinculados → Vincular dispositivo** → escaneá el QR
4. En 10-20 segundos el estado pasa a **Conectado**

> El bot mantiene la sesión activa. Si se desconecta, podés reconectar desde el portal sin perder el historial.

---

## 🛠️ Stack técnico

| Componente    | Tecnología                                      |
|---------------|-------------------------------------------------|
| API REST      | FastAPI + uvicorn                               |
| Frontend      | React + Vite                                    |
| Base de datos | SQLite async (`data/messages.db`)               |
| WhatsApp      | Playwright headless (perfil Chrome persistente) |
| Telegram      | python-telegram-bot v21                         |
| Exposición    | ngrok (etapa 1) → Cloudflare Tunnel (etapa 2)  |

---

## ⚡ Desarrollo local

### Requisitos

- Python 3.11+
- Node 18+
- `phones.json` con la configuración de bots

### Arrancar

```bash
./start.sh        # levanta backend (uvicorn) + frontend (vite)
```

Los puertos se leen del `.env` en la raíz:

```env
BACKEND_PORT=8000
FRONTEND_PORT=5173
ADMIN_PASSWORD=...
```

### Tests

```bash
# Backend (requiere server corriendo)
cd backend
pytest tests/ -v

# Frontend Playwright (requiere server corriendo)
cd frontend
node_modules/.bin/playwright test
```

---

## 🗂️ Estructura del proyecto

```
_/
├── backend/
│   ├── main.py              # FastAPI app, lifespan, routers
│   ├── sim.py               # Simulador (activo cuando ENABLE_BOTS=false)
│   ├── state.py             # clients dict + wa_session singleton
│   ├── config.py            # lee phones.json
│   ├── db.py                # SQLite async
│   ├── api/                 # routers: auth, bots, phones, whatsapp,
│   │                        #          telegram, messages, sim, empresa, logs
│   ├── automation/
│   │   └── whatsapp.py      # lógica WA Web con Playwright
│   ├── bots/
│   │   └── telegram_bot.py  # bot de Telegram
│   └── tests/               # pytest: auth, logs, sim
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── DashboardPage.jsx    # panel admin
│   │   │   ├── EmpresaPage.jsx      # portal de empresa (login + dashboard)
│   │   │   └── NuevaEmpresaPage.jsx # onboarding nueva empresa
│   │   └── components/
│   │       ├── ChatWidget.jsx       # chat inline reutilizable
│   │       └── MonitorPanel.jsx     # drawer de monitoring en tiempo real
│   └── tests/               # Playwright: login, monitor
├── management/              # planes, visión, arquitectura
├── phones.json              # config de bots y teléfonos (gitignoreado)
├── data/                    # DB y sesiones Chrome (gitignoreado)
└── start.sh                 # arranque unificado
```

---

## 🔀 Worktrees (flujo de desarrollo)

Cada feature se desarrolla en su propio worktree — un servidor independiente con DB propia, sin tocar producción.

| Worktree     | Backend | Frontend | Estado     |
|--------------|---------|----------|------------|
| `_` (master) | 8000    | 5173     | Producción |
| dev-1        | 8001    | 5174     | Libre      |
| dev-2        | 8002    | 5175     | Libre      |

Ver `CLAUDE.md` para el flujo completo de creación de worktrees, symlinks y setup.

---

## 🗺️ Roadmap

- [x] Bots de WhatsApp (Playwright headless)
- [x] Bots de Telegram (python-telegram-bot)
- [x] Respuesta automática configurable por empresa
- [x] Portal de empresa — gestión de canales + chat inline
- [x] Alta de empresa nueva (onboarding autogestionable)
- [x] Panel admin con monitoring en tiempo real
- [x] Exposición pública via ngrok
- [ ] Autenticación segura (OAuth / tokens)
- [ ] Dominio propio + Cloudflare Tunnel
- [ ] Reconexión automática de sesiones WA
