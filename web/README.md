# Pulpo — `web/` (Next.js)

Backend real de Pulpo, pensado para correr en Vercel. Sirve `/api/**` (todo
el motor de flows/triggers/chats/runs) y, en el build de producción, también
la SPA de `../frontend` (Vite) — ver "Un solo deploy" más abajo. `pulpo/`
(Python, en la raíz del repo) queda solo para lo que necesita correr en una
máquina local de verdad (CLI, WhatsApp/Wavi con browser) — no es el backend
real de nada de lo que vive acá.

## ⚠️ Local y producción usan bases de datos DISTINTAS — no se mezclan

Esto se confunde seguido, léelo antes de tocar `db:push` o cualquier migración:

| | Variable en `.env.local` | Dónde vive |
|---|---|---|
| **Local (dev)** | `DATABASE_URL` | Postgres local, `localhost:9011` (docker/local, no Neon) |
| **Producción (Vercel)** | `POSTGRES_URL` / `DATABASE_URL_UNPOOLED` (mismo host que las demás `PG*`/`POSTGRES_*`) | Neon, host `ep-ancient-credit-...neon.tech` |

`.env.local` tiene AMBAS cosas a la vez porque se generó una vez con
`vercel env pull` (trae todas las `POSTGRES_*`/`PG*` de Neon) y después se le
pisó a mano solo `DATABASE_URL` para apuntar al Postgres local — el resto de
las variables de Neon quedaron ahí de referencia, **no se usan en dev**.

Consecuencia práctica: `npm run db:push` (que hace `dotenv -e .env.local --
drizzle-kit push`) **solo migra la base local**, nunca producción, porque
`drizzle.config.ts` lee `process.env.DATABASE_URL` y ese es el override
local. Si cambiás `lib/db/schema.ts`, tenés que aplicar el `db:push` DOS
VECES: una tal cual (local) y otra apuntando explícitamente a la URL de
Neon/producción (por ejemplo `DATABASE_URL="$POSTGRES_URL" npx drizzle-kit
push`, con el valor real de `POSTGRES_URL` de `.env.local` o de `vercel env
ls`/dashboard — nunca hardcodeado en un commit).

Vercel (el deploy real) usa las env vars configuradas en el proyecto
(`vercel env ls` / dashboard → Settings → Environment Variables) para
Production/Preview/Development — **no lee `.env.local`**, ese archivo es
solo para tu `next dev` local.

## Local dev

```bash
npm run dev              # next dev -p ${WEB_BACKEND_PORT:-9010}, contra la DB local (:9011)
```

Login con Google no anda en local (`AUTH_GOOGLE_ID`/`SECRET` vacíos en
`.env.local` a propósito). Para probar sin login, seteá
`PULPO_LOCAL_NO_AUTH=1` en `.env.local` (ver `lib/auth/local-bypass.ts`) y
usá el CLI:

```bash
npm run pulpo -- bots list
npm run pulpo -- flows trigger <flowId> <nodeId> --message "hola"
```

El CLI (`cli/main.ts`) habla por HTTP contra `http://localhost:9010`, nunca
importa `lib/business/*` directo — ejercita el mismo camino que producción
(proxy → route → business → DB).

`frontend/` (la SPA, Vite) se sirve aparte en dev: `./start.sh front` desde
la raíz del repo, con su propio proxy de `/api` hacia este backend (ver
`WEB_BACKEND_PORT` en `frontend/vite.config.js`).

## Un solo deploy en Vercel (`npm run build`)

`scripts/build-spa.mjs` compila `../frontend` (Vite) y copia el resultado a
`public/assets` + `lib/generated/spa-index.ts` (inlineado, no se lee del
filesystem en runtime). `app/[[...slug]]/route.ts` sirve ese HTML para
cualquier path que no sea `/api/**` — una sola URL, sin CORS.

Vercel solo sube el árbol de este directorio (`web/`), sin `frontend/` al
lado — por eso `scripts/build-spa.mjs` detecta si `../frontend` no existe y
en ese caso usa lo que ya esté generado en `public/assets`/`lib/generated`
(generado localmente ANTES de deployar). `.vercelignore` existe
específicamente para que esos archivos generados (gitignoreados) SÍ viajen
en el upload del CLI.

```bash
node scripts/build-spa.mjs   # regenera public/assets + lib/generated desde frontend/
vercel deploy                # preview
vercel deploy --prod         # producción
```
