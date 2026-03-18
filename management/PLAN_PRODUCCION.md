# Plan: Exposición a internet — Mac local primero, hosting después

## Filosofía

Lean. Cada paso entrega valor real. No se invierte hasta que hay ingresos que lo justifiquen.

---

## Etapa 1 — ngrok gratis (hoy, $0)

**Objetivo:** URL pública estable, primer cliente puede darse de alta hoy.

### Qué es

ngrok free tier da 1 dominio estático gratis para siempre (`algo.ngrok-free.app`).
Sin tarjeta. Sin fecha de vencimiento. La Mac sigue siendo el servidor.

### Setup

```bash
# 1. Instalar
brew install ngrok

# 2. Registrarse en ngrok.com → copiar authtoken
ngrok config add-authtoken <token>

# 3. Reclamar dominio estático en ngrok.com → Dashboard → Domains → New Domain
#    Te asigna algo como: pulpo-abc123.ngrok-free.app

# 4. Levantar el túnel apuntando al frontend
ngrok http --domain=pulpo-abc123.ngrok-free.app 5173
```

### Cambios en el sistema

- `CORS` en `backend/main.py`: agregar el dominio ngrok a `allow_origins`
- Frontend: el backend en prod apunta a `/api` (mismo origen via ngrok) o a la URL del backend si se expone por separado
- Contraseña admin: cambiar de `admin` a algo seguro

### Limitaciones aceptables en esta etapa

- Si la Mac se apaga, el servicio cae (solución: deshabilitar suspensión)
- 1 solo túnel en free tier → frontend y backend van por el mismo puerto (el frontend proxea `/api` a uvicorn)
- URL no es un dominio propio (`*.ngrok-free.app`) — suficiente para primeros clientes

### Valor entregado

Un cliente puede entrar a la URL, darse de alta como empresa, configurar su bot.
Pulpo está "en producción" sin gastar un peso.

---

## Etapa 2 — Dominio propio en Cloudflare (~$10/año, cuando haya ingresos)

**Objetivo:** URL profesional (`pulpo.io` o similar), más confianza del cliente.

### Qué cambia

- Registrar dominio en Cloudflare Registrar (~$8-10/año)
- Instalar `cloudflared` y crear túnel permanente (el servicio es gratis)
- Reemplazar ngrok por Cloudflare Tunnel — misma Mac, misma lógica
- HTTPS automático, sin exponer IP, sin límites de tráfico

### Ventajas sobre ngrok

- Dominio propio (más profesional)
- Sin restricciones de conexiones simultáneas
- Puede tener subdominios: `app.pulpo.io` para frontend, `api.pulpo.io` para backend
- El daemon `cloudflared` se instala como servicio y arranca solo con la Mac

---

## Etapa 3 — VPS Linux (cuando la Mac no alcance o se quiera uptime garantizado)

**Trigger:** más de 3-5 empresas activas con tráfico real, o el cliente pide SLA.

### Qué cambia

- VPS Linux (~€5/mes en Hetzner, Railway, Fly.io)
- Mover `data/` y `phones.json` al servidor
- Playwright corre en el servidor (headless, sin pantalla)
- Cloudflare Tunnel sigue funcionando igual pero apunta al VPS
- Backup automático de la DB

### Lo que NO cambia

- Stack: FastAPI + React + SQLite (suficiente para decenas de empresas)
- Cloudflare Tunnel para HTTPS
- `phones.json` como fuente de verdad (hasta que se necesite PostgreSQL)

---

## Etapa 4 — PostgreSQL + infraestructura seria (futuro lejano)

Solo si la escala lo exige. SQLite aguanta bien hasta cientos de empresas con tráfico moderado.
No hay prisa.

---

## Estado

- [ ] Etapa 1: ngrok — **próximo paso**
- [ ] Etapa 2: dominio + Cloudflare Tunnel
- [ ] Etapa 3: VPS
- [ ] Etapa 4: PostgreSQL
