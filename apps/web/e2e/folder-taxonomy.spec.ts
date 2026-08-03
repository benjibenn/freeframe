import { test, expect, APIRequestContext } from '@playwright/test'
import { watchForErrors, assertHealthy, snap } from './helpers'

/**
 * Folder taxonomy end-to-end: niche → store → product → ads.
 *
 * Unlike the rest of the suite this test MUTATES data — it has to, since the
 * thing under test is the path a folder tree resolves to. Everything it creates
 * is namespaced with a run id and torn down in afterAll, and it never uploads:
 * it borrows an already-ready video from the environment and files it, so the
 * test needs no S3 or transcoder.
 *
 * Requires E2E_API_KEY (the public integration API key) on top of the usual
 * E2E_* vars — the /public/v1 endpoints are key-guarded, not JWT-guarded.
 */
const API_URL = process.env.E2E_API_URL || 'http://localhost:8000'
const API_KEY = process.env.E2E_API_KEY || ''
const EMAIL = process.env.E2E_EMAIL || 'admin@demo.com'
const PASSWORD = process.env.E2E_PASSWORD || 'password123'

// Namespacing keeps parallel/repeat runs from colliding on
// uq_folder_name_per_parent, which is unique per (project, parent, name).
const RUN = `e2e-${Date.now()}`
const NICHE = `${RUN}-niche`
const STORE = `${RUN}-store`
const PRODUCT = `${RUN}-product`
const OTHER_NICHE = `${RUN}-other`
// Fixed, not RUN-scoped: the stamped asset is written by the seed before this
// spec loads, so both sides must agree on a constant.
const STAMPED_PATH = 'E2E_STAMPED/Skincare/GlowCo/Serum'

let token = ''
let assetId = ''
let projectId = ''
let projectName = ''
let originalFolderId: string | null = null
const createdFolderIds: string[] = []

async function authed(request: APIRequestContext) {
  const res = await request.post(`${API_URL}/auth/login`, {
    data: { email: EMAIL, password: PASSWORD },
  })
  expect(res.ok(), `Login failed (${res.status()}) for ${EMAIL}`).toBeTruthy()
  return (await res.json()).access_token as string
}

/** Fetch the public video list with the integration key. */
async function listVideos(request: APIRequestContext, params: Record<string, string> = {}) {
  const res = await request.get(`${API_URL}/public/v1/videos`, {
    headers: { 'X-API-Key': API_KEY },
    params: { asset_type: 'all', per_page: '200', ...params },
  })
  expect(res.ok(), `GET /public/v1/videos failed: ${res.status()} ${await res.text()}`).toBeTruthy()
  return await res.json()
}

async function createFolder(
  request: APIRequestContext,
  projectId: string,
  name: string,
  parentId: string | null,
) {
  const res = await request.post(`${API_URL}/projects/${projectId}/folders`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name, parent_id: parentId },
  })
  expect(res.ok(), `Create folder "${name}" failed: ${res.status()} ${await res.text()}`).toBeTruthy()
  const folder = await res.json()
  createdFolderIds.push(folder.id)
  return folder.id as string
}

async function moveAsset(request: APIRequestContext, id: string, folderId: string | null) {
  const res = await request.patch(`${API_URL}/assets/${id}/move`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { folder_id: folderId },
  })
  expect(res.ok(), `Move asset failed: ${res.status()} ${await res.text()}`).toBeTruthy()
}

test.describe('folder taxonomy → public API folder_path', () => {
  test.skip(!API_KEY, 'Set E2E_API_KEY to run the folder taxonomy suite.')

  test.beforeAll(async ({ request }) => {
    token = await authed(request)

    // Borrow a video that is already ready. /public/v1/videos only ever returns
    // assets with a ready version, so anything it lists is safe to file.
    const { items } = await listVideos(request)
    expect(
      items.length,
      'No ready videos in this environment — seed one before running this suite.',
    ).toBeGreaterThan(0)

    assetId = items[0].id
    projectName = items[0].project_name
    originalFolderId = items[0].folder_id ?? null

    projectId = items[0].project_id
    const nicheId = await createFolder(request, projectId, NICHE, null)
    const storeId = await createFolder(request, projectId, STORE, nicheId)
    const productId = await createFolder(request, projectId, PRODUCT, storeId)
    await createFolder(request, projectId, OTHER_NICHE, null)

    await moveAsset(request, assetId, productId)
  })

  test.afterAll(async ({ request }) => {
    if (!assetId) return
    // Put the borrowed asset back before removing the tree, so a failed run
    // never strands it in a soft-deleted folder.
    await moveAsset(request, assetId, originalFolderId).catch(() => {})
    for (const id of [...createdFolderIds].reverse()) {
      await request
        .delete(`${API_URL}/folders/${id}`, { headers: { Authorization: `Bearer ${token}` } })
        .catch(() => {})
    }
  })

  test('resolves the full ancestor path, rooted at the project name', async ({ request }) => {
    const { items } = await listVideos(request)
    const video = items.find((v: any) => v.id === assetId)

    expect(video, 'filed asset vanished from the public list').toBeTruthy()
    // The whole point: three levels of nesting collapse into one readable path,
    // and the project name leads so the path is unambiguous across projects.
    expect(video.folder_path).toBe(`${projectName}/${NICHE}/${STORE}/${PRODUCT}`)
  })

  test('filtering by a niche returns everything beneath it', async ({ request }) => {
    // Prefix match is what makes drill-down work: picking a niche must surface
    // ads filed three levels down, not just ads sitting directly in the niche.
    const niche = await listVideos(request, { folder_path: `${projectName}/${NICHE}` })
    expect(niche.items.map((v: any) => v.id)).toContain(assetId)

    const store = await listVideos(request, { folder_path: `${projectName}/${NICHE}/${STORE}` })
    expect(store.items.map((v: any) => v.id)).toContain(assetId)

    const exact = await listVideos(request, {
      folder_path: `${projectName}/${NICHE}/${STORE}/${PRODUCT}`,
    })
    expect(exact.items.map((v: any) => v.id)).toContain(assetId)
  })

  test('a sibling niche does not leak ads from another branch', async ({ request }) => {
    // Guards the prefix match against matching on substrings or on any ancestor
    // segment — the failure mode that would quietly mix two clients' ads.
    const other = await listVideos(request, { folder_path: `${projectName}/${OTHER_NICHE}` })
    expect(other.items.map((v: any) => v.id)).not.toContain(assetId)
  })

  test('submitted work carries the taxonomy even with no folder', async ({ request }) => {
    // Submitted assets are born in a per-submitter project with folder_id NULL,
    // so without the stamped path they would sit outside the tree entirely and a
    // niche filter would quietly omit every piece of work editors sent in.
    const { items } = await listVideos(request)
    const stamped = items.find((v: any) => v.name === 'E2E_TAXONOMY_MARK_STAMPED')

    expect(stamped, 'stamped asset missing from the public list').toBeTruthy()
    expect(stamped.folder_id, 'stamped asset should have no folder').toBeNull()
    expect(stamped.folder_path).toBe(STAMPED_PATH)

    // The filter must reach it — matching only real folders would miss it.
    const byNiche = await listVideos(request, { folder_path: 'E2E_STAMPED' })
    expect(byNiche.items.map((v: any) => v.id)).toContain(stamped.id)
  })

  test('an unknown path returns nothing rather than everything', async ({ request }) => {
    // A filter that silently falls back to "no filter" is worse than an error:
    // the picker would look like it worked and show the wrong library.
    const nothing = await listVideos(request, { folder_path: `${RUN}-does-not-exist` })
    expect(nothing.items).toHaveLength(0)
    expect(nothing.total).toBe(0)
  })

  test('the folder tree renders in the web UI', async ({ page }, testInfo) => {
    const watch = watchForErrors(page)
    await page.goto(`/projects/${projectId}`)
    await expect(page.getByText(NICHE).first()).toBeVisible({ timeout: 15_000 })
    await snap(page, testInfo, 'folder-taxonomy-tree')
    assertHealthy(watch, testInfo)
  })
})
