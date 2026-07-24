import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

// Leer .env desde la raíz del worktree (un nivel arriba de frontend/)
function loadRootEnv() {
  const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
  const envFile = path.join(dir, '.env')
  const vars = {}
  if (fs.existsSync(envFile)) {
    for (const line of fs.readFileSync(envFile, 'utf-8').split('\n')) {
      const m = line.match(/^\s*([^#=\s]+)\s*=\s*(.*)$/)
      if (m) vars[m[1]] = m[2].trim()
    }
  }
  return vars
}

export default defineConfig(() => {
  const env = loadRootEnv()
  // WEB_BACKEND_PORT (shell env, no el .env compartido) apunta el proxy al
  // backend Next.js de la migración a Vercel (web/) en vez del backend
  // Python (BACKEND_PORT) -- así probar un stack no pisa el puerto del
  // otro. Ver web/package.json (dev corre en :9010 por default, puerto
  // reclamado vía `las ports claim` para este worktree) y
  // management/HANDOFF_VERCEL_DEEP_MIGRATION.md.
  const backendPort = process.env.WEB_BACKEND_PORT || env.BACKEND_PORT || '8000'
  const frontendPort = parseInt(env.FRONTEND_PORT || '5173', 10)

  return {
    plugins: [react()],
    server: {
      port: frontendPort,
      allowedHosts: true,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
