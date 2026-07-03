import { defineConfig, devices } from '@playwright/test'

// End-to-end harness. Point it at any environment via env vars:
//   E2E_BASE_URL   web app        (default http://localhost:3000)
//   E2E_API_URL    FastAPI        (default http://localhost:8000)
//   E2E_EMAIL      login email    (default admin@demo.com — the dev seed admin)
//   E2E_PASSWORD   login password (default password123 — the dev seed password)
//   E2E_PROJECT_ID optional project to use for the project-detail test
// See e2e/README.md.
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000'

export default defineConfig({
  testDir: './e2e',
  // The suite mutates nothing, but shares one logged-in state, so keep it serial.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { outputFolder: 'e2e/report', open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    // Logs in once and saves the storage state the rest of the suite reuses.
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/state.json' },
      dependencies: ['setup'],
    },
  ],
})
