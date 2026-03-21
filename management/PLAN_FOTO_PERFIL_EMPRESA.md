# Plan: Foto de perfil por empresa

## Objetivo
Permitir que cada empresa suba una foto de perfil (logo) que se muestre en su portal y en el dashboard de admin.

## Alcance

### Backend
- Nuevo campo `logo_url` (o `logo_path`) en la tabla `empresas` de SQLite.
- Endpoint `POST /api/empresa/logo` — recibe multipart/form-data con la imagen, la guarda en `data/logos/{empresa_id}.{ext}` y actualiza el campo en DB.
- Endpoint `GET /api/empresa/logo/{empresa_id}` — sirve el archivo estático (o redirigir a `/data/logos/...` si ya están expuestos como static).
- Validación: solo imágenes (MIME jpg/png/webp), tamaño máximo ~2 MB.

### Frontend — EmpresaPage (portal del cliente)
- En la sección de perfil/header de EmpresaPage: mostrar la foto si existe, placeholder genérico si no.
- Botón "Cambiar foto" → input file oculto → preview inline → confirmar → POST al endpoint.

### Frontend — DashboardPage (admin)
- En la card de cada empresa/bot: mostrar el logo en miniatura (32–48px) junto al nombre.
- Sin edición desde el dashboard — solo visualización.

## Flujo de datos
```
EmpresaPage
  └─ input[type=file] (click en avatar)
       └─ POST /api/empresa/logo  (multipart, auth Bearer)
            └─ guarda en data/logos/
            └─ UPDATE empresas SET logo_path=... WHERE id=...
  └─ GET /api/empresa/me  →  incluir logo_url en la respuesta
```

## Consideraciones
- `data/logos/` debe estar en `.gitignore` (igual que `data/sessions/`).
- En worktrees de desarrollo, la carpeta se crea sola al subir la primera imagen (igual que `data/messages.db`).
- Si la empresa no tiene logo, mostrar un avatar placeholder con las iniciales del nombre.
- No es necesario CDN ni S3 por ahora — el servidor sirve los archivos directamente.

## Foto desde WhatsApp / Telegram (opción automática)
Cada empresa ya tiene bots de WA o Telegram activos con foto de perfil. Se puede ofrecer esa imagen como opción de carga rápida:

- **WhatsApp**: la foto del número de WA se puede obtener via `page.evaluate` o la API interna de WA Web (`window.WWebJS` o scraping del DOM del chat propio). Guardarla igual que una subida manual.
- **Telegram**: `bot.get_user_profile_photos(bot.id)` devuelve las fotos del perfil del bot; descargar la más reciente con `bot.get_file(file_id)`.
- En EmpresaPage, si la empresa tiene al menos un bot conectado (WA o TG), mostrar un botón secundario: **"Usar foto de WhatsApp"** / **"Usar foto de Telegram"** además del upload manual.
- El backend ejecuta la descarga y la procesa igual que una imagen subida: la guarda en `data/logos/` y actualiza `logo_path`.
- Esto es opcional — si el bot no está conectado o no tiene foto, simplemente no aparece el botón.

## Notas de UI
- El avatar es clickeable solo desde EmpresaPage (el cliente lo gestiona).
- Tamaño de display sugerido: 80px circular en el header del portal, 32px en la card del dashboard.
- El placeholder con iniciales debe coincidir con el color de acento actual del portal.

## Estado
Pendiente — no iniciado.
