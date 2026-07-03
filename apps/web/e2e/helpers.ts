import { Page, TestInfo, expect } from '@playwright/test'
import fs from 'node:fs'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000'
const API_URL = process.env.E2E_API_URL || 'http://localhost:8000'

export interface ErrorWatch {
  crashes: string[] // uncaught JS exceptions — a real crash
  serverErrors: string[] // 5xx from our app / API
  consoleErrors: string[] // console.error — reported, not fatal (often third-party noise)
}

/** Start collecting page health signals. Call before navigating. */
export function watchForErrors(page: Page): ErrorWatch {
  const w: ErrorWatch = { crashes: [], serverErrors: [], consoleErrors: [] }
  page.on('pageerror', (err) => w.crashes.push(String(err)))
  page.on('console', (msg) => {
    if (msg.type() === 'error') w.consoleErrors.push(msg.text())
  })
  page.on('response', (res) => {
    const url = res.url()
    const ours = url.startsWith(BASE_URL) || url.startsWith(API_URL)
    if (ours && res.status() >= 500) w.serverErrors.push(`${res.status()} ${url}`)
  })
  return w
}

/**
 * Fail on real problems (uncaught exceptions, 5xx from our own services) and
 * surface console errors as annotations without failing — those are frequently
 * third-party/hydration noise and would make the harness flaky as a hard gate.
 */
export function assertHealthy(w: ErrorWatch, testInfo: TestInfo) {
  if (w.consoleErrors.length) {
    testInfo.annotations.push({
      type: 'console-error',
      description: w.consoleErrors.slice(0, 15).join('\n'),
    })
  }
  expect(w.crashes, `Uncaught page errors:\n${w.crashes.join('\n')}`).toHaveLength(0)
  expect(w.serverErrors, `Server (5xx) responses:\n${w.serverErrors.join('\n')}`).toHaveLength(0)
}

/** Screenshot the current page into e2e/screenshots and attach it to the report. */
export async function snap(page: Page, testInfo: TestInfo, name: string) {
  fs.mkdirSync('e2e/screenshots', { recursive: true })
  const file = `e2e/screenshots/${name}.png`
  await page.screenshot({ path: file, fullPage: true })
  await testInfo.attach(name, { path: file, contentType: 'image/png' })
}

/**
 * Count items matching `selector`, then scroll the last one into view a few times
 * to trigger infinite scroll / reveal-on-scroll, and count again. Works regardless
 * of which inner container actually scrolls (scrollIntoViewIfNeeded finds it).
 */
export async function countAfterScroll(page: Page, selector: string) {
  const loc = page.locator(selector)
  const initial = await loc.count()
  for (let i = 0; i < 8; i++) {
    const before = await loc.count()
    await loc.last().scrollIntoViewIfNeeded().catch(() => {})
    await page.waitForTimeout(700)
    const now = await loc.count()
    if (now > before && now >= initial + 1 && i >= 1) break
  }
  return { initial, after: await loc.count() }
}
