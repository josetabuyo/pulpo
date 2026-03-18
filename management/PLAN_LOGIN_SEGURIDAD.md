# Plan: Login y Seguridad

## Situación actual

El sistema tiene dos tipos de acceso, ambos con autenticación básica por contraseña plana:

| Acceso | Endpoint | Mecanismo actual | Problema |
|--------|----------|-----------------|----------|
| Admin  | `POST /api/auth/login` | contraseña en `.env` | Sin rate limiting, sin expiración |
| Empresa | `POST /api/empresa/auth` | contraseña en `phones.json` | Igual, + se envía en cada request vía header |

La contraseña de empresa viaja en cada request como `x-empresa-pwd`. No hay tokens, no hay sesiones del lado del servidor, no hay expiración.

---

## Análisis de opciones

### Opción A — JWT propio con refresh tokens ⭐ Recomendado Fase 1

**Qué es**: al hacer login, el backend emite un JWT de corta vida (15-30 min) + un refresh token de larga vida (7-30 días). El frontend usa el access token en cada request. Cuando expira, usa el refresh token para pedir uno nuevo silenciosamente.

**Pros**:
- $0, sin dependencia de terceros
- Control total
- Simple de implementar en FastAPI (`python-jose` o `PyJWT`)
- El frontend ya maneja tokens (solo cambia `sessionStorage` por tokens bien manejados)
- No requiere dominio propio ni email

**Contras**:
- Hay que implementar la lógica de refresh
- Hay que almacenar refresh tokens (SQLite, tabla simple)
- No hay "olvídé mi contraseña" (pero para B2B con pocas empresas no es crítico)

**Complejidad**: baja-media. 1-2 días.

**Lo que cambia**:
- `POST /api/empresa/auth` devuelve `{ access_token, refresh_token }` en vez de solo `ok`
- Cada request lleva `Authorization: Bearer <token>` en vez de `x-empresa-pwd`
- Nuevo endpoint `POST /api/empresa/refresh`
- Rate limiting en el endpoint de auth (max 5 intentos / 15 min por IP)

---

### Opción B — Google OAuth (Sign in with Google)

**Qué es**: el usuario hace click en "Iniciar sesión con Google", se autentica en Google, y Google devuelve un token que el backend valifica. No hay contraseña que gestionar.

**Pros**:
- El estándar más reconocido en B2B (todos los clientes tienen Google Workspace)
- Sin gestión de contraseñas (sin "olvidé mi contraseña")
- Muy confiable: Google gestiona MFA, detección de intrusos, etc.
- Clerk y Auth0 lo dan con 3 líneas de código en React

**Contras**:
- Requiere que el email del cliente esté pre-registrado en `phones.json`
- El flujo OAuth requiere redirect URI pública (ngrok o dominio propio) → ya lo tenemos
- Hay que crear proyecto en Google Cloud Console (15 min de setup)
- Si el cliente no usa Google, queda afuera

**Complejidad**: media. 2-3 días con Clerk, 3-5 días sin.

**Costo**: $0 con Google Cloud gratuito. Clerk es gratis hasta 10.000 MAU activos.

---

### Opción C — Clerk (servicio de auth)

**Qué es**: servicio drop-in que maneja toda la auth: Google OAuth, email/password, magic links, MFA, etc. Componentes React listos.

**Pros**:
- Implementación rapidísima (horas, no días)
- Incluye Google OAuth, magic links, MFA de gratis
- Panel de usuarios en la nube
- SDK React + Python oficiales

**Contras**:
- Dependencia de tercero → si Clerk cae, la auth cae
- Los emails de los usuarios quedan en su sistema
- Requiere dominio verificado para producción (ok, lo tenemos en Etapa 2)
- Free tier: gratis hasta 10.000 MAU (más que suficiente para años)

**Complejidad**: muy baja. 1 día.

---

### Opción D — Magic links por email

**Qué es**: el usuario ingresa su email, recibe un link con token de un solo uso, hace click y está dentro. Sin contraseña.

**Pros**:
- UX moderna, sin contraseñas que recordar
- Muy seguro si el email está bajo control del cliente

**Contras**:
- Requiere servidor de email (Resend, SendGrid — gratis en free tier)
- Latencia: el usuario espera el email
- Para empresas B2B con pocas cuentas, agrega fricción sin mucho beneficio extra sobre JWT bien hecho

---

## Recomendación: dos fases

### Fase 1 — JWT propio (esta semana, $0)

**Por qué primero esto y no Google**: el sistema ya tiene contraseñas definidas en `phones.json`. Agregar JWT es un cambio puro de backend sin tocar el flujo de onboarding. Es rápido, seguro y no requiere que el cliente configure nada nuevo.

**Qué implementar**:
1. `python-jose[cryptography]` en el backend
2. Tabla `sessions` en SQLite: `(id, bot_id, refresh_token_hash, expires_at, created_at)`
3. `POST /api/empresa/auth` → devuelve `access_token` (JWT, 30 min) + `refresh_token` (opaco, 30 días)
4. `POST /api/empresa/refresh` → valida refresh token, devuelve nuevo access token
5. `POST /api/empresa/logout` → invalida el refresh token
6. Middleware que valida `Authorization: Bearer` en todos los endpoints `/empresa/{bot_id}/*`
7. Rate limiting: `slowapi` (3 líneas) — max 10 intentos / hora por IP en endpoints de auth
8. Frontend: guardar tokens en `localStorage` (access) + cookie HttpOnly vía backend (refresh)

**Lo que NO cambia**: el flujo de onboarding, las contraseñas en `phones.json`, la UX del portal.

### Fase 2 — Google OAuth (cuando haya dominio propio, Etapa 2 del plan de producción)

Una vez que tengamos `pulpo.io` o similar:
1. Agregar "Iniciar sesión con Google" como opción adicional en el portal de empresa
2. Mapear el email de Google al `bot_id` correspondiente en `phones.json`
3. El cliente deja de necesitar recordar la contraseña — entra con su cuenta de Google de trabajo

**Por qué esperar al dominio**: Google OAuth necesita redirect URI válida. Ngrok funciona pero el dominio cambia si se pierde el static domain. Con Cloudflare Tunnel + dominio propio es permanente.

---

## Seguridad adicional (barata, alta palanca)

Estas cosas van independientemente del sistema de auth elegido:

| Medida | Esfuerzo | Impacto |
|--------|----------|---------|
| HTTPS | ✅ ya tenemos (ngrok) | Alto |
| Rate limiting en auth | 1h (`slowapi`) | Alto |
| CORS estricto (solo el dominio propio) | 30 min | Medio |
| Passwords hasheadas (`bcrypt`) en vez de planas en `phones.json` | 2h | Alto |
| Headers de seguridad (`X-Frame-Options`, `CSP`) | 30 min | Medio |
| Logs de intentos fallidos de login | 1h | Medio |

---

## Estado

- [x] Fase 1: JWT + refresh tokens + rate limiting — **completado 2026-03-18**, mergeado a master
  - Tabla `sessions` en SQLite
  - `POST /api/empresa/login` → JWT 30min + refresh cookie HttpOnly 30d
  - `POST /api/empresa/refresh` + `POST /api/empresa/logout`
  - Middleware Bearer en `/empresa/{bot_id}/*`
  - Rate limiting 10 intentos/hora por IP (`slowapi`)
  - Frontend: `authFetch` wrapper con auto-refresh en 401
- [ ] Fase 2: Google OAuth (post-dominio propio)
- [ ] Hash de contraseñas en phones.json
