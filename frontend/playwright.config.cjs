const { defineConfig } = require('@playwright/test')

module.exports = defineConfig({
  testDir: './tests',
  use: {
    baseURL: 'http://localhost:5175',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5175',
    reuseExistingServer: true,
  },
})
