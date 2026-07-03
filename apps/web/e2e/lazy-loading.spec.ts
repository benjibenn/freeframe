import { test, expect } from '@playwright/test'
import { watchForErrors, assertHealthy, countAfterScroll } from './helpers'

// A narrow, short viewport forces the grid into fewer columns, so a single page of
// cards is taller than the viewport + the observer's 800px preload margin. That keeps
// the sentinel off-screen on load — proving that scrolling (not eager preloading) is
// what fetches the next page, which is the whole point of the feature.
test.use({ viewport: { width: 520, height: 720 } })

// Verifies the lazy-loading behaviour added to the asset/project surfaces: the list
// starts with one page of items and scrolling loads more. Each test skips (rather
// than fails) when the account simply doesn't have enough data to trigger a second
// page — you can't prove infinite scroll with 5 items. Point E2E_* at an account /
// project with plenty of assets to actually exercise it.

const ASSETS_PAGE_SIZE = 24 // matches ASSETS_PAGE_SIZE / PER_PAGE in the app
const PROJECTS_REVEAL_STEP = 18 // matches PROJECTS_REVEAL_STEP on the projects list

test('library: infinite scroll loads more assets', async ({ page }, testInfo) => {
  const w = watchForErrors(page)
  await page.goto('/library')
  await page.locator('[data-lib-index]').first().waitFor({ state: 'visible' }).catch(() => {})
  const initial = await page.locator('[data-lib-index]').count()
  test.skip(initial < ASSETS_PAGE_SIZE, `only ${initial} library assets; need > ${ASSETS_PAGE_SIZE}`)

  const { after } = await countAfterScroll(page, '[data-lib-index]')
  testInfo.annotations.push({ type: 'counts', description: `${initial} → ${after}` })
  expect(after, 'scrolling did not load additional assets').toBeGreaterThan(initial)
  assertHealthy(w, testInfo)
})

test('my assets: infinite scroll loads more assets', async ({ page }, testInfo) => {
  const w = watchForErrors(page)
  await page.goto('/assets')
  await page.locator('[data-testid="asset-card"]').first().waitFor({ state: 'visible' }).catch(() => {})
  const initial = await page.locator('[data-testid="asset-card"]').count()
  test.skip(initial < ASSETS_PAGE_SIZE, `only ${initial} assets; need > ${ASSETS_PAGE_SIZE}`)

  const { after } = await countAfterScroll(page, '[data-testid="asset-card"]')
  testInfo.annotations.push({ type: 'counts', description: `${initial} → ${after}` })
  expect(after, 'scrolling did not load additional assets').toBeGreaterThan(initial)
  assertHealthy(w, testInfo)
})

test('project detail: infinite scroll loads more assets', async ({ page }, testInfo) => {
  const w = watchForErrors(page)

  let target = process.env.E2E_PROJECT_ID ? `/projects/${process.env.E2E_PROJECT_ID}` : ''
  if (!target) {
    await page.goto('/projects')
    const firstCard = page.locator('[data-testid="project-card"] a[href^="/projects/"]').first()
    await expect(firstCard, 'no projects exist to open').toBeVisible()
    target = (await firstCard.getAttribute('href')) || ''
  }
  await page.goto(target)
  await page.locator('[data-testid="asset-card"]').first().waitFor({ state: 'visible' }).catch(() => {})
  const initial = await page.locator('[data-testid="asset-card"]').count()
  test.skip(
    initial < ASSETS_PAGE_SIZE,
    `project has ${initial} root-level assets; need > ${ASSETS_PAGE_SIZE} (set E2E_PROJECT_ID to a large one)`,
  )

  const { after } = await countAfterScroll(page, '[data-testid="asset-card"]')
  testInfo.annotations.push({ type: 'counts', description: `${initial} → ${after}` })
  expect(after, 'scrolling did not load additional assets').toBeGreaterThan(initial)
  assertHealthy(w, testInfo)
})

test('projects list: reveals more cards on scroll', async ({ page }, testInfo) => {
  const w = watchForErrors(page)
  await page.goto('/projects')
  await page.locator('[data-testid="project-card"]').first().waitFor({ state: 'visible' }).catch(() => {})
  const initial = await page.locator('[data-testid="project-card"]').count()
  test.skip(initial < PROJECTS_REVEAL_STEP, `only ${initial} project cards; need > ${PROJECTS_REVEAL_STEP}`)

  const { after } = await countAfterScroll(page, '[data-testid="project-card"]')
  testInfo.annotations.push({ type: 'counts', description: `${initial} → ${after}` })
  expect(after, 'scrolling did not reveal more project cards').toBeGreaterThan(initial)
  assertHealthy(w, testInfo)
})
