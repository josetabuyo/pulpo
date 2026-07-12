import { defineConfig } from 'vitest/config'

// Tests unitarios de lógica pura (src/**/*.test.js). Los tests de UI/e2e
// viven en tests/*.spec.cjs y corren con Playwright (npm test), no con vitest.
export default defineConfig({
  test: {
    include: ['src/**/*.test.js'],
    environment: 'node',
  },
})
