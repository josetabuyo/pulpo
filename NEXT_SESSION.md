# NEXT_SESSION.md — seguridad-jwt

## Instrucciones para el Claude que abra este worktree

Cuando el usuario diga **"dale!"** (o cualquier variante de arrancar), ejecuta **inmediatamente**:

```bash
say -v "Paulina" "dale, arrancando seguridad JWT"
```

Luego trabaja en orden sin pedir permiso. Después de cada fase completada, da un update de audio corto con `say -v "Paulina" "..."`. Trabaja de forma autónoma — solo interrumpe si encuentras algo bloqueante que el usuario deba decidir.

---

## Contexto del proyecto

- **Stack**: FastAPI + uvicorn (backend), React + Vite (frontend), SQLite
- **Este worktree**: ambiente de desarrollo. `ENABLE_BOTS=false` → simulador activo, no hay bots reales
- **Puertos**: backend :8001, frontend :5174
- **Arrancar servidor**: `./start.sh` desde la raíz del worktree
- **Tests backend**: `cd backend && pytest tests/ -v` (requiere servidor corriendo en :8001)
- **Tests frontend**: `cd frontend && node_modules/.bin/playwright test`

Archivos clave:
- `backend/main.py` — lifespan, routers, CORS
- `backend/state.py` — `clients` dict
- `backend/api/` — routers existentes
- `backend/sim.py` — motor del simulador
- `frontend/src/pages/` — páginas React
- `phones.json` — configuración de bots/empresas (gitignoreado, symlink a producción)

---

## Scope de esta sesión — Fase 1: JWT completo

### Objetivo
Reemplazar el acceso sin autenticación al portal de empresa por un sistema JWT real con refresh tokens, rate limiting, y contraseñas hasheadas.

### Paso 0 — Verificar estado inicial
```bash
cd /Users/josetabuyo/Development/pulpo/seguridad-jwt
./start.sh &
sleep 5
cd backend && pytest tests/ -v
```
Lee el output. Los tests deben pasar antes de tocar código.

---

### Paso 1 — Instalar dependencias
```bash
cd /Users/josetabuyo/Development/pulpo/seguridad-jwt
.venv/bin/pip install "python-jose[cryptography]" passlib[bcrypt] slowapi
```

Audio: `say -v "Paulina" "dependencias instaladas, creando tablas"`

---

### Paso 2 — DB: tabla sessions + hash de contraseñas

En `backend/db.py`, agregar después de las tablas existentes:

```sql
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    refresh_token TEXT NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(refresh_token);
CREATE INDEX IF NOT EXISTS idx_sessions_bot_id ON sessions(bot_id);
```

También agregar funciones en db.py:
- `create_session(bot_id, refresh_token, expires_at) -> int`
- `get_session(refresh_token) -> dict | None` (solo si no revocado y no expirado)
- `revoke_session(refresh_token) -> bool`
- `revoke_all_sessions(bot_id) -> int` (para logout-all futuro)

Audio: `say -v "Paulina" "tablas creadas, implementando JWT"`

---

### Paso 3 — Módulo JWT: `backend/auth_jwt.py`

Crear `backend/auth_jwt.py`:

```python
import os
import secrets
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def create_access_token(bot_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": bot_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)

def decode_access_token(token: str) -> str | None:
    """Returns bot_id or None if invalid/expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
```

**Nota sobre contraseñas:** Las contraseñas en `phones.json` son texto plano hoy. Para no romper compatibilidad, al hacer login:
1. Leer contraseña de phones.json
2. Si empieza con `$2b$` → es bcrypt, usar `verify_password`
3. Si no → comparar texto plano (backward compat), pero no bloquear el login

---

### Paso 4 — Router de auth empresa: `backend/api/auth_empresa.py`

Crear `backend/api/auth_empresa.py` con los siguientes endpoints:

**POST `/api/empresa/login`**
```json
Request:  { "bot_id": "...", "password": "..." }
Response: { "access_token": "...", "token_type": "bearer", "bot_id": "..." }
          + Set-Cookie: refresh_token=...; HttpOnly; SameSite=Strict; Max-Age=2592000
```
- Buscar empresa en phones.json por `bot_id`
- Verificar contraseña (bcrypt o texto plano)
- Si inválida: `401 Incorrect password`
- Si válida: crear access token + refresh token, guardar refresh en DB sessions
- Rate limiting: 10 intentos/hora por IP (usar `slowapi`)

**POST `/api/empresa/refresh`**
```json
Request:  Cookie refresh_token=...
Response: { "access_token": "...", "token_type": "bearer" }
```
- Leer refresh token de cookie HttpOnly
- Buscar en DB: debe existir, no revocado, no expirado
- Generar nuevo access token

**POST `/api/empresa/logout`**
```json
Request:  Cookie refresh_token=... (o header Authorization)
Response: { "ok": true }
          + Set-Cookie: refresh_token=; Max-Age=0 (borrar cookie)
```
- Revocar refresh token en DB

**GET `/api/empresa/me`** (requiere Bearer token)
```json
Response: { "bot_id": "...", "nombre": "..." }
```
- Validar access token
- Devolver datos básicos de la empresa

Audio: `say -v "Paulina" "endpoints de auth listos, agregando middleware"`

---

### Paso 5 — Middleware de autenticación

Crear `backend/middleware_auth.py`:

```python
from fastapi import HTTPException, Header, Depends
from auth_jwt import decode_access_token

async def require_empresa_auth(authorization: str = Header(None)) -> str:
    """Dependency que extrae y valida Bearer token. Retorna bot_id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    token = authorization.removeprefix("Bearer ")
    bot_id = decode_access_token(token)
    if not bot_id:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return bot_id
```

Aplicar `Depends(require_empresa_auth)` a los endpoints del portal de empresa:
- `backend/api/client.py` — todos los endpoints `/empresa/{bot_id}/...`
- Validar además que el `bot_id` del token coincida con el `bot_id` del path

---

### Paso 6 — Registrar router en main.py

En `backend/main.py`:
```python
from api.auth_empresa import router as auth_empresa_router
app.include_router(auth_empresa_router)
```

Agregar `.env` variable `JWT_SECRET_KEY` en el `.env` de este worktree (ya está, pero recordar para producción se debe setear una clave fija).

---

### Paso 7 — Frontend: flujo de login con tokens

Actualizar `frontend/src/pages/EmpresaLoginPage.jsx` (o equivalente):

1. Al hacer login: `POST /api/empresa/login` con `{ bot_id, password }`
2. Guardar `access_token` en `localStorage` (key: `empresa_access_token`)
3. La cookie `refresh_token` la maneja el browser automáticamente (HttpOnly)
4. Antes de cada request autenticado: incluir header `Authorization: Bearer <token>`
5. Si request devuelve 401: intentar `POST /api/empresa/refresh` automáticamente
   - Si refresh OK → guardar nuevo access_token y reintentar request original
   - Si refresh falla → redirigir a login

Crear `frontend/src/lib/auth.js` (o similar) con funciones:
- `getAccessToken()` → lee de localStorage
- `setAccessToken(token)` → guarda en localStorage
- `clearAccessToken()` → borra de localStorage
- `authFetch(url, options)` → wrapper de fetch que agrega Bearer y maneja 401→refresh

Actualizar todos los `fetch` del portal empresa para usar `authFetch`.

Audio: `say -v "Paulina" "frontend actualizado, corriendo tests"`

---

### Paso 8 — Tests

**Tests backend** — agregar `backend/tests/test_auth_jwt.py`:

```python
# Test login exitoso → devuelve access_token
# Test login contraseña incorrecta → 401
# Test acceso sin token → 401
# Test acceso con token válido → 200
# Test refresh → nuevo access_token
# Test logout → refresh revocado
# Test rate limiting → después de 10 intentos fallidos → 429
```

Correr: `cd backend && pytest tests/ -v`

**Tests frontend** — actualizar `frontend/tests/login.spec.cjs`:
- El flujo de login ahora devuelve token → verificar que queda en localStorage
- Verificar que con token inválido redirige a login

Correr: `cd frontend && node_modules/.bin/playwright test`

Audio: `say -v "Paulina" "tests pasando, JWT completo y listo para mergear"`

---

### Paso 9 — Verificación final

Checklist antes de dar por terminado:
- [ ] `pytest tests/ -v` → todos en verde
- [ ] `playwright test` → todos en verde
- [ ] Login desde el browser funciona y persiste entre recargas
- [ ] Logout limpia correctamente
- [ ] Refresh automático funciona (simular token expirado)
- [ ] Endpoints protegidos devuelven 401 sin token

Cuando todo pase: `say -v "Paulina" "sesión JWT terminada, listo para que master mergee"`

---

## Reglas de este worktree

- `ENABLE_BOTS=false` — no hay bots reales, usar simulador
- No mergear a master desde aquí — el merge lo hace la sesión de `_` (master)
- No tocar `data/sessions/` ni hacer `pkill -9`
- Commits frecuentes con mensajes descriptivos
