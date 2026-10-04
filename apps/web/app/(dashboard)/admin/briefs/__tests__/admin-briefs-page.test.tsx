/**
 * Mirrors tasks-page.test.tsx's paging contract tests for the other infinite
 * list on the branch: a remount with a warm SWR cache must still refetch (the
 * review's "cross-page staleness after /review decisions" finding applies to
 * this page too, see final-review.md Important #1), and "Loading more…" must
 * key off "a page beyond those loaded is being fetched", not fire on every
 * background refetch nor show next to the initial load.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SWRConfig } from 'swr'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'

const authState = { isSuperAdmin: true, isLoading: false }
vi.mock('@/stores/auth-store', () => ({ useAuthStore: () => authState }))

import AdminBriefsPage from '../page'
import { stubIntersectionObserver } from '@/test/intersection-observer'
import type { BriefOverviewRow } from '@/components/admin/brief-overview-table'

function row(id: string, title: string): BriefOverviewRow {
  return {
    id, token: `tok-${id}`, title, instructions: null, is_enabled: true, expires_at: null,
    created_at: '2026-09-01T00:00:00Z', home_project_id: null, home_folder_id: null,
    home_path: null, persona_label: null, angle_label: null, problem: null,
    has_brief: false, has_brief_json: false, reference_image_count: 0,
    reference_video_count: 0, submission_count: 0, asset_count: 0, submissions: [],
  }
}

const overviewCalls = () =>
  vi.mocked(api.get).mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith('/brief-overview'))

function renderPage(cache: Map<string, unknown> = new Map()) {
  return render(
    <SWRConfig value={{ provider: () => cache, dedupingInterval: 0 }}>
      <AdminBriefsPage />
    </SWRConfig>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  stubIntersectionObserver()
  authState.isSuperAdmin = true
  authState.isLoading = false
  vi.mocked(api.get).mockImplementation(((url: string) => {
    if (url === '/users/assignable') return Promise.resolve([])
    return Promise.resolve({ items: [row('b1', 'First Brief')], total: 1 })
  }) as never)
})

describe('AdminBriefsPage — paged overview', () => {
  it('remounting with a warm cache refetches the first page', async () => {
    const cache = new Map<string, unknown>()
    const { unmount } = renderPage(cache)
    expect(await screen.findAllByText('First Brief')).not.toHaveLength(0)
    unmount()

    vi.mocked(api.get).mockClear()
    renderPage(cache)
    expect(await screen.findAllByText('First Brief')).not.toHaveLength(0)
    await waitFor(() => expect(overviewCalls().length).toBeGreaterThan(0))
  })

  it('does not show "Loading more…" next to the initial load', async () => {
    vi.mocked(api.get).mockImplementation(
      ((url: string) => (url === '/users/assignable' ? Promise.resolve([]) : new Promise(() => {}))) as never,
    )
    renderPage()
    expect(screen.queryByText('Loading more…')).toBeNull()
  })
})
