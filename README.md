# 🐙 Pulpo

**Automatizá la atención de tu negocio por WhatsApp y Telegram.**

Pulpo conecta tus canales de mensajería a un sistema de bots inteligentes: respuesta automática, historial de conversaciones y gestión desde un portal propio. Sin código, sin complicaciones.

---

## ✨ ¿Qué hace Pulpo?

- **Respuesta automática** — tu bot responde al instante cuando no estás disponible
- **Multi-canal** — WhatsApp y Telegram desde un solo lugar
- **Portal de bot** — cada cliente gestiona sus canales, ve conversaciones y responde inline
- **Panel admin** — control total: agregar bots, ver estado de bots, monitorear en tiempo real

---

## 🚀 Empezar ahora

Accedé al portal público:

**[https://unbuoyant-surgeless-micheal.ngrok-free.dev/bot](https://unbuoyant-surgeless-micheal.ngrok-free.dev/bot)**

- ¿Ya tenés una cuenta? Ingresá con tu clave de bot.
- ¿Primera vez? → **[Crear bot nueva](https://unbuoyant-surgeless-micheal.ngrok-free.dev/bot/nueva)**

---

## 📲 Conectar Telegram paso a paso

Para agregar un bot de Telegram a tu bot en Pulpo:

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

1. Entrá a tu portal: [https://unbuoyant-surgeless-micheal.ngrok-free.dev/bot](https://unbuoyant-surgeless-micheal.ngrok-free.dev/bot)
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
| WhatsApp      | vía wavi (CLI propio, poller + sesión Chrome persistente) |
| Telegram      | python-telegram-bot v21                         |
| Exposición    | ngrok (etapa 1) → Cloudflare Tunnel (etapa 2)  |

---

## ⚡ Desarrollo local

### Requisitos

- Python 3.11+ (paquete `pulpo`, instalado en modo editable — ver `CLAUDE.md`)
- Node 18+
- `connections.json` con la configuración de bots

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
# Unitarios (sin server)
uv run pytest pulpo/ -v

# Integración (requiere server en BACKEND_PORT)
uv run pytest tests/ -v

# Frontend Playwright (requiere server corriendo)
cd frontend
npx playwright test
```

---

## 🗂️ Estructura del proyecto

La estructura de `pulpo/` (paquete pip editable, 4 interfaces) y las reglas de
dónde va cada cosa están documentadas en `CLAUDE.md` — es la fuente de verdad,
se mantiene junto al código en cada cambio. Los diagramas de arquitectura
(capas, conexiones/canales) están en `docs/adr/007-diagramas-arquitectura.md`
y también se ven renderizados en vivo en el panel admin
(`/dashboard?arquitectura=1`).

---

## 🔀 Worktrees (flujo de desarrollo)

Cada feature se desarrolla en su propio worktree — un servidor independiente con DB propia, sin tocar producción.

| Worktree     | Backend | Frontend | Estado     |
|--------------|---------|----------|------------|
| `_` (master) | 8000    | 5173     | Producción |
| dev-1        | 8001    | 5174     | Libre      |
| dev-2        | 8002    | 5175     | Libre      |

Ver `docs/adr/003-worktrees-y-flujo-de-features.md` para el flujo completo de creación de worktrees, symlinks y setup.

---

## 🗺️ Roadmap

- [x] Bots de WhatsApp (vía wavi)
- [x] Bots de Telegram (python-telegram-bot)
- [x] Respuesta automática configurable por bot
- [x] Portal de bot — gestión de canales + chat inline
- [x] Alta de bot nueva (onboarding autogestionable)
- [x] Panel admin con monitoring en tiempo real
- [x] Exposición pública via ngrok
- [ ] Autenticación segura (OAuth / tokens)
- [ ] Dominio propio + Cloudflare Tunnel
- [ ] Reconexión automática de sesiones WA
