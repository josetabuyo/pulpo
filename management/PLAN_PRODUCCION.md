# Plan: Exposición a internet desde Mac local

## Objetivo

Hacer que clientes reales puedan acceder al sistema sin necesidad de un servidor externo.
La Mac de José es el servidor — se expone al exterior con un túnel. Cuando la facturación
lo justifique, se evalúa migrar a hosting.

---

## Estrategia: túnel permanente

En lugar de hostear en un VPS, se expone el servidor local mediante un túnel HTTPS.
El cliente accede a una URL pública que redirige al backend/frontend en la Mac.

### Opciones

| Herramienta | Costo | URL estable | Notas |
|---|---|---|---|
| **Cloudflare Tunnel** | Gratis | ✅ (subdominio fijo) | Requiere cuenta CF. La mejor opción |
| **ngrok** | Free tier limitado / $8/mes | ✅ con plan pago | URL cambia en free tier |
| **Tailscale Funnel** | Gratis | ✅ | Más orientado a dev, menos robusto |

**Opción elegida: Cloudflare Tunnel** — gratis, URL estable, HTTPS automático, sin exponer IP.

### Cómo funciona

```
Cliente → https://pulpo.midominio.com
              ↓  (Cloudflare Tunnel)
         Mac local → localhost:8000 (backend) / localhost:5173 (frontend)
```

El daemon `cloudflared` corre en la Mac como servicio (launchd), se inicia solo al arrancar.

---

## Setup

### 1. Instalar cloudflared
```bash
brew install cloudflare/cloudflare/cloudflared
cloudflared login   # abre browser, autenticar con cuenta CF
```

### 2. Crear el túnel
```bash
cloudflared tunnel create pulpo
cloudflared tunnel route dns pulpo pulpo.midominio.com
```

### 3. Config del túnel (`~/.cloudflared/config.yml`)
```yaml
tunnel: <tunnel-id>
credentials-file: ~/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: pulpo.midominio.com
    service: http://localhost:5173     # frontend
  - hostname: api.pulpo.midominio.com
    service: http://localhost:8000     # backend
  - service: http_status:404
```

### 4. Correr como servicio (inicio automático)
```bash
cloudflared service install
sudo launchctl start com.cloudflare.cloudflared
```

---

## Cambios necesarios en el sistema

- **Frontend**: la URL del backend en producción pasa a ser `https://api.pulpo.midominio.com`
  (o se sirve todo desde el mismo dominio con proxy rules en CF)
- **CORS**: agregar el dominio público a `allow_origins` en `backend/main.py`
- **Contraseña admin**: cambiar de `admin` a algo seguro antes de exponer
- **HTTPS**: Cloudflare lo gestiona automáticamente, no se necesita certificado local

---

## Limitaciones conocidas

- **WhatsApp Web**: Playwright corre localmente — si la Mac se apaga o duerme, los bots caen
  - Mitigación: deshabilitar suspensión en Preferencias del Sistema → Energía
  - La sesión WA se recupera sola al reiniciar (perfil persistido en `data/sessions/`)
- **Uptime**: depende de la Mac. Aceptable para MVP / clientes iniciales
- **Capacidad**: suficiente para decenas de empresas con tráfico moderado

---

## Camino a hosting (futuro)

Cuando la facturación lo justifique:

1. **VPS Linux** (Railway, Fly.io, Hetzner ~€5/mes) + mover `data/` y `phones.json`
2. **SQLite → PostgreSQL**: SQLAlchemy ya lo abstrae, migración limpia
3. **WA sessions en servidor**: mismo Playwright, distinto disco
4. **WhatsApp Business API** (opcional): más estable que WA Web pero requiere aprobación Meta

No hay prisa — WA Web funciona bien y el costo de mantenimiento es bajo hoy.

---

## Estado

Pendiente. Primera tarea: registrar dominio + configurar Cloudflare Tunnel.
