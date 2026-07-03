import { test, expect } from '@playwright/test'
import { watchForErrors, assertHealthy, snap } from './helpers'

// The "does every page render at all" gate: navigate, confirm we weren't bounced
// to /login, confirm the page's key landmark is visible, screenshot it, and assert
// no crashes or 5xx. This alone catches blank pages, auth regressions, and API
// blowups across the whole app — run it after any feature change.
const PAGES = [
  { name: 'dashboard-home', path: '/', ready: 'main' },
  { name: 'projects', path: '/projects', ready: 'h1:has-text("Projects")' },
  { name: 'library', path: '/library', ready: 'h1:has-text("Library")' },
  { name: 'assets', path: '/assets', ready: 'h1' },
]

for (const p of PAGES) {
  test(`renders: ${p.name}`, async ({ page }, testInfo) => {
    const w = watchForErrors(page)
    await page.goto(p.path, { waitUntil: 'domcontentloaded' })
    await expect(page, 'bounced to /login — auth/session problem').not.toHaveURL(/\/login/)
    await expect(page.locator(p.ready).first()).toBeVisible()
    await page.waitForLoadState('networkidle').catch(() => {})
    await snap(page, testInfo, p.name)
    assertHealthy(w, testInfo)
  })
}

// The project detail page needs a real project id. Prefer E2E_PROJECT_ID, else pick
// the first project card on /projects — proving that navigation path end-to-end too.
test('renders: project-detail', async ({ page }, testInfo) => {
  const w = watchForErrors(page)
  let target = process.env.E2E_PROJECT_ID ? `/projects/${process.env.E2E_PROJECT_ID}` : ''
  if (!target) {
    await page.goto('/projects')
    const firstCard = page.locator('[data-testid="project-card"] a[href^="/projects/"]').first()
    await expect(firstCard, 'no projects exist to open').toBeVisible()
    target = (await firstCard.getAttribute('href')) || ''
  }
  expect(target, 'could not resolve a project to open').toBeTruthy()
  await page.goto(target, { waitUntil: 'domcontentloaded' })
  await expect(page).not.toHaveURL(/\/login/)
  await page.waitForLoadState('networkidle').catch(() => {})
  await snap(page, testInfo, 'project-detail')
  assertHealthy(w, testInfo)
})
