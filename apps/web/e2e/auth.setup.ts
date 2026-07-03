import { test as setup, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const API_URL = process.env.E2E_API_URL || 'http://localhost:8000'
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000'
const EMAIL = process.env.E2E_EMAIL || 'admin@demo.com'
const PASSWORD = process.env.E2E_PASSWORD || 'password123'

const authFile = 'e2e/.auth/state.json'

// Authenticate once and persist the exact browser storage the app relies on:
//   - localStorage ff_access_token / ff_refresh_token  (source of the Bearer header)
//   - cookies      ff_access_token / ff_refresh_token  (read by Next middleware)
// Every other test reuses this via `storageState`, so login runs a single time.
setup('authenticate', async ({ page, request }) => {
  // Grab tokens straight from the API — deterministic and independent of whatever
  // login UI (magic code / SSO) is wired up. Requires an account WITH a password.
  const res = await request.post(`${API_URL}/auth/login`, {
    data: { email: EMAIL, password: PASSWORD },
  })
  expect(
    res.ok(),
    `Login failed (${res.status()}) for ${EMAIL} at ${API_URL}. Set E2E_EMAIL / ` +
      `E2E_PASSWORD to an account that has a password (see e2e/README.md).`,
  ).toBeTruthy()
  const { access_token, refresh_token } = await res.json()

  // localStorage is origin-scoped, so we must be on the app origin before writing it.
  await page.goto(`${BASE_URL}/login`)
  await page.evaluate(
    ([a, r]) => {
      localStorage.setItem('ff_access_token', a)
      localStorage.setItem('ff_refresh_token', r)
    },
    [access_token, refresh_token],
  )
  await page.context().addCookies([
    { name: 'ff_access_token', value: access_token, url: BASE_URL },
    { name: 'ff_refresh_token', value: refresh_token, url: BASE_URL },
    { name: 'ff_setup_done', value: '1', url: BASE_URL },
  ])

  // Prove the session actually works before saving it — otherwise the whole suite
  // would fail confusingly downstream on every page.
  await page.goto(`${BASE_URL}/projects`)
  await expect(page, 'auth did not stick — got bounced to /login').not.toHaveURL(/\/login/)

  fs.mkdirSync(path.dirname(authFile), { recursive: true })
  await page.context().storageState({ path: authFile })
})
