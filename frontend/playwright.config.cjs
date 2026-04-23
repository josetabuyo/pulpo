const { defineConfig } = require('@playwright/test')
const fs = require('fs')
const path = require('path')

// Lee variables del .env del worktree (un nivel arriba de /frontend).
function readEnvVar(key, fallback) {
  const envPath = path.resolve(__dirname, '../.env')
  try {
    const content = fs.readFileSync(envPath, 'utf8')
    const match = content.match(new RegExp(`^${key}=(.+)`, 'm'))
    return match ? match[1].trim() : fallback
  } catch {
    return fallback
  }
}

const PORT = process.env.FRONTEND_PORT || readEnvVar('FRONTEND_PORT', '5173')
// Exponer ADMIN_PASSWORD para los tests
process.env.ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || readEnvVar('ADMIN_PASSWORD', 'admin')
const BASE_URL = `http://localhost:${PORT}`

module.exports = defineConfig({
  testDir: './tests',
  use: {
    baseURL: BASE_URL,
  },
  webServer: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: true,
  },
})
