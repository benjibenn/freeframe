/**
 * The list view is the default view, and its stage chips both count and filter.
 * They must answer the same question the pipeline columns answer — an editor's own
 * status, an admin's the brief's — or one screen contradicts itself: the chip says
 * a brief is in Review, the pipeline puts it in In Progress, and the editor cannot
 * tell which one they are being measured on.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SWRConfig } from 'swr'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'

const authState = { user: null as { id: string; is_superadmin: boolean; is_subadmin: boolean } | null }
vi.mock('@/stores/auth-store', () => ({ useAuthStore: () => authState }))

import TasksPage from '../page'
import type { BriefTaskItem, TaskStage } from '@/types'

const STAGES: TaskStage[] = [
  { id: 's1', name: 'In Progress', position: 1, color: null, is_default: false },
  { id: 's2', name: 'Review', position: 2, color: null, is_default: false },
]

/** The brief's own status and the viewer's own status deliberately differ — with
 *  both at the same stage the test would pass whichever one the page reads. */
const BRIEF: BriefTaskItem = {
  id: 'brief-1',
  title: 'Test Brief',
  taxonomy_path: null,
  task_stage_id: 's1',
  assignee_id: null,
  assignee_name: null,
  editors: [{ id: 'viewer-1', name: 'Viewer', email: 'viewer@example.com', task_stage_id: 's2' }],
  has_brief: false,
  has_brief_json: false,
  paid_count: 0,
  submission_count: 0,
  submit_url: null,
  created_at: '2026-09-01T00:00:00Z',
  assets: [],
}

function renderTasks() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <TasksPage />
    </SWRConfig>,
  )
}

/** A stage chip is a button whose text is the label followed by its count. */
function chipCount(label: string): string {
  const chip = screen
    .getAllByRole('button')
    .find((b) => b.textContent?.startsWith(label) && b.textContent !== label)
  if (!chip) throw new Error(`no stage chip labelled ${label}`)
  return chip.textContent!.slice(label.length)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockImplementation(((url: string) => {
    if (url === '/task-stages') return Promise.resolve(STAGES)
    // Only the admin run reaches this one — the owner dropdown's source.
    if (url === '/users/assignable') return Promise.resolve([])
    return Promise.resolve({ briefs: [BRIEF], unbriefed: [] })
  }) as never)
})

describe('TasksPage — which status the stage chips count', () => {
  it("counts a non-admin's brief under their own status, not the brief's", async () => {
    authState.user = { id: 'viewer-1', is_superadmin: false, is_subadmin: false }
    renderTasks()

    expect(await screen.findByText('Test Brief')).toBeInTheDocument()
    expect(chipCount('Review')).toBe('1')
    expect(chipCount('In Progress')).toBe('0')
  })

  it("counts an admin's brief under the brief's own status", async () => {
    authState.user = { id: 'admin-1', is_superadmin: true, is_subadmin: false }
    renderTasks()

    expect(await screen.findByText('Test Brief')).toBeInTheDocument()
    expect(chipCount('In Progress')).toBe('1')
    expect(chipCount('Review')).toBe('0')
  })

  it('filters a non-admin by their own status too, so the chip and the rows agree', async () => {
    authState.user = { id: 'viewer-1', is_superadmin: false, is_subadmin: false }
    const user = userEvent.setup()
    renderTasks()
    expect(await screen.findByText('Test Brief')).toBeInTheDocument()

    // A chip showing 1 that then empties the table on click is the contradiction
    // this guards: the count and the predicate have to read the same status.
    await user.click(screen.getAllByRole('button').find((b) => b.textContent === 'Review1')!)
    expect(screen.getByText('Test Brief')).toBeInTheDocument()

    await user.click(screen.getAllByRole('button').find((b) => b.textContent === 'In Progress0')!)
    expect(screen.queryByText('Test Brief')).toBeNull()
  })
})
