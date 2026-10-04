/**
 * The board is paged on the server, so the page no longer counts or filters.
 * These pin the page's half of the contract: chip counts come from the server's
 * stage_counts (which apply the editor-own-status rule; see test_board_paging.py),
 * a chip click becomes a stage_id query, and reaching the end asks for the next
 * page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SWRConfig } from 'swr'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'

const authState = { user: null as { id: string; is_superadmin: boolean; is_subadmin: boolean } | null }
vi.mock('@/stores/auth-store', () => ({ useAuthStore: () => authState }))

import TasksPage from '../page'
import { stubIntersectionObserver } from '@/test/intersection-observer'
import type { BriefTaskItem, TaskBoardPage, TaskStage } from '@/types'

const STAGES: TaskStage[] = [
  { id: 's1', name: 'In Progress', position: 1, color: null, is_default: false },
  { id: 's2', name: 'Review', position: 2, color: null, is_default: false },
]

function brief(id: string, title: string): BriefTaskItem {
  return {
    id, title, taxonomy_path: null, task_stage_id: 's1', assignee_id: null, assignee_name: null,
    editors: [], has_brief: false, has_brief_json: false, paid_count: 0, submission_count: 0,
    submit_url: null, created_at: '2026-09-01T00:00:00Z', assets: [],
  }
}

function renderTasks() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <TasksPage />
    </SWRConfig>,
  )
}

/** Same cache across mounts, so the second render sees a warm SWR cache
 *  instead of a fresh one — the only way to exercise "remount with cached
 *  pages" in a test. */
function renderTasksWithCache(cache: Map<string, unknown>) {
  return render(
    <SWRConfig value={{ provider: () => cache, dedupingInterval: 0 }}>
      <TasksPage />
    </SWRConfig>,
  )
}

/** A stage chip is a button whose text is the label followed by its count. */
function chipCount(label: string): string {
  const chip = screen
    .getAllByRole('button')
    .find((b) => b.textContent?.startsWith(label) && /\d+$/.test(b.textContent.slice(label.length)))
  if (!chip) throw new Error(`no stage chip labelled ${label}`)
  return chip.textContent!.slice(label.length)
}

const boardCalls = () =>
  vi.mocked(api.get).mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith('/task-board'))

let boardPages: Record<number, TaskBoardPage>
let io: ReturnType<typeof stubIntersectionObserver>

beforeEach(() => {
  vi.clearAllMocks()
  io = stubIntersectionObserver()
  authState.user = { id: 'admin-1', is_superadmin: true, is_subadmin: false }
  boardPages = { 0: { items: [brief('b1', 'First Brief')], total: 1, stage_counts: { s1: 1 } } }
  vi.mocked(api.get).mockImplementation(((url: string) => {
    if (url === '/task-stages') return Promise.resolve(STAGES)
    if (url === '/users/assignable') return Promise.resolve([])
    const offset = Number(new URL(url, 'http://x').searchParams.get('offset') ?? 0)
    return Promise.resolve(boardPages[offset] ?? { items: [], total: 0, stage_counts: {} })
  }) as never)
})

describe('TasksPage — paged board', () => {
  it('asks for the first 25 briefs, not the whole board', async () => {
    renderTasks()
    expect(await screen.findByText('First Brief')).toBeInTheDocument()
    expect(boardCalls()[0]).toBe('/task-board?limit=25&offset=0')
  })

  it("shows the server's per-stage counts on the chips", async () => {
    boardPages[0] = { items: [brief('b1', 'First Brief')], total: 3, stage_counts: { s1: 1, s2: 2 } }
    renderTasks()
    await screen.findByText('First Brief')
    expect(chipCount('All')).toBe('3')
    expect(chipCount('In Progress')).toBe('1')
    expect(chipCount('Review')).toBe('2')
    expect(chipCount('Unassigned')).toBe('0')
  })

  it('sends the chosen stage to the server instead of filtering what is loaded', async () => {
    const user = userEvent.setup()
    renderTasks()
    await screen.findByText('First Brief')
    await user.click(screen.getAllByRole('button').find((b) => b.textContent?.startsWith('Review'))!)
    await waitFor(() => expect(boardCalls()).toContain('/task-board?stage_id=s2&limit=25&offset=0'))
  })

  it('loads the next page when the end of the list scrolls into view', async () => {
    boardPages = {
      0: {
        items: Array.from({ length: 25 }, (_, i) => brief(`b${i}`, `Brief ${i}`)),
        total: 26,
        stage_counts: { s1: 26 },
      },
      25: { items: [brief('b25', 'Last Brief')], total: 26, stage_counts: { s1: 26 } },
    }
    renderTasks()
    await screen.findByText('Brief 0')
    act(() => io.reveal())
    expect(await screen.findByText('Last Brief')).toBeInTheDocument()
    expect(boardCalls()).toContain('/task-board?limit=25&offset=25')
  })

  it('remounting with a warm cache refetches the first page (stale after /review decisions otherwise)', async () => {
    const cache = new Map<string, unknown>()
    const { unmount } = renderTasksWithCache(cache)
    expect(await screen.findByText('First Brief')).toBeInTheDocument()
    unmount()

    vi.mocked(api.get).mockClear()
    renderTasksWithCache(cache)
    // The cached page renders immediately...
    expect(await screen.findByText('First Brief')).toBeInTheDocument()
    // ...but a fresh fetch must still have been made, not served from cache only.
    await waitFor(() => expect(boardCalls().length).toBeGreaterThan(0))
  })

  it('does not show "Loading more…" next to the initial skeleton on first load', async () => {
    // A page that never resolves keeps isLoading/isValidating true without
    // ever producing data, so the skeleton branch stays on screen — exactly
    // the moment "Loading more…" must NOT also render.
    vi.mocked(api.get).mockImplementation(
      ((url: string) => (url === '/task-stages' ? Promise.resolve(STAGES) : new Promise(() => {}))) as never,
    )
    renderTasks()
    expect(screen.queryByText('Loading more…')).toBeNull()
  })
})
