const { defineConfig } = require('@playwright/test')
const fs = require('fs')
const path = require('path')

// Lee FRONTEND_PORT del .env del worktree (un nivel arriba de /frontend).
// Fallback: 5173 (puerto por defecto de Vite).
function readFrontendPort() {
  const envPath = path.resolve(__dirname, '../.env')
  try {
    const content = fs.readFileSync(envPath, 'utf8')
    const match = content.match(/^FRONTEND_PORT=(\d+)/m)
    return match ? match[1] : '5173'
  } catch {
    return '5173'
  }
}

const PORT = process.env.FRONTEND_PORT || readFrontendPort()
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
