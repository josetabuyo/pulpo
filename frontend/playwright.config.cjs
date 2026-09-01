const { defineConfig } = require('@playwright/test')
const fs = require('fs')
const path = require('path')

// Bug real 2026-09-01 (encontrado corriendo `npm test` después de tocar el
// chat en web/): esto apuntaba a FRONTEND_PORT=5173 leído de `_/.env` --
// resto de un esquema viejo por-worktree (ver ese archivo, "master (estable):
// BACKEND_PORT=8000 FRONTEND_PORT=5173") de antes de la migración "un solo
// deploy" a Next.js (2026-07-24). Ese puerto no corre nada hace rato --
// :9010 es el ÚNICO puerto local del dashboard/API (ver CLAUDE.md y el
// `.agent.json` de Pulpo, que ya ni lista 5173 entre sus puertos). Los 56
// specs comparten un helper `login()`; con el server real inalcanzable,
// TODOS fallaban con el mismo timeout esperando el campo "Contraseña" --
// no era un bug de los tests en sí. Ahora lee de `web/.env.local` (el env
// real del server que sirve :9010), con WEB_BACKEND_PORT como single source
// of truth del puerto (mismo default que usa `web/package.json`'s `dev`).
function readEnvVar(key, fallback) {
  const envPath = path.resolve(__dirname, '../web/.env.local')
  try {
    const content = fs.readFileSync(envPath, 'utf8')
    const match = content.match(new RegExp(`^${key}=(.+)`, 'm'))
    return match ? match[1].trim().replace(/^"(.*)"$/, '$1') : fallback
  } catch {
    return fallback
  }
}

const PORT = process.env.WEB_BACKEND_PORT || readEnvVar('WEB_BACKEND_PORT', '9010')
// Exponer ADMIN_PASSWORD para los tests
process.env.ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || readEnvVar('ADMIN_PASSWORD', 'admin')
const BASE_URL = `http://localhost:${PORT}`

module.exports = defineConfig({
  testDir: './tests',
  // El JSON alimenta GET /api/architecture (sección Arquitectura del dashboard)
  reporter: [
    ['list'],
    ['json', { outputFile: '../monitor/test_report_frontend.json' }],
  ],
  use: {
    baseURL: BASE_URL,
  },
  webServer: {
    // El server real vive en web/ (Next.js, :9010) -- no en frontend/ (SPA
    // fuente, sin server propio salvo el Vite dev deprecado). reuseExistingServer
    // hace que esto casi nunca se ejecute en la práctica (el flujo normal ya
    // deja `next dev` corriendo, ver CLAUDE.md), pero si Playwright tiene que
    // levantarlo de cero, tiene que ser el server correcto.
    command: 'npm run dev',
    cwd: path.resolve(__dirname, '../web'),
    url: BASE_URL,
    reuseExistingServer: true,
  },
})
