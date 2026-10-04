/**
 * The only place the frontend enforces "editors move only their own status,
 * admins move anyone's" is `canMove={canAssign || e.id === viewerId}` inside
 * `BriefRow`. Nothing else in the app checks it, so an inverted expression
 * would ship undetected: an editor could either drive a status update that
 * 404s, or lose the ability to move their own row. These tests also cover
 * the confirm-before-POST guard on assigning an editor, since that action
 * provisions a project and cannot be undone.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'

import { TaskBoardRefreshProvider } from '@/lib/task-board-refresh'
import { BriefRow } from '../brief-row'
import type { BriefEditor, BriefTaskItem, TaskStage, User } from '@/types'

const STAGES: TaskStage[] = [
  { id: 's1', name: 'In Progress', position: 1, color: null, is_default: false },
  { id: 's2', name: 'Review', position: 2, color: null, is_default: false },
]

const EDITORS: BriefEditor[] = [
  { id: 'e-self', name: 'Self Editor', email: 'self@example.com', task_stage_id: 's1' },
  { id: 'e-other', name: 'Other Editor', email: 'other@example.com', task_stage_id: 's2' },
]

function makeUser(id: string, name: string): User {
  return {
    id,
    email: `${id}@example.com`,
    name,
    avatar_url: null,
    status: 'active',
    is_superadmin: false,
    is_subadmin: false,
    uid: null,
    nickname: null,
    email_verified: true,
    preferences: {},
    created_at: '2026-09-01T00:00:00Z',
    deleted_at: null,
  }
}

const OWNERS: User[] = [makeUser('u-admin', 'Admin Owner'), makeUser('u-new', 'New Owner')]

function makeBrief(
  editors: BriefEditor[] = EDITORS,
  overrides: Partial<BriefTaskItem> = {},
): BriefTaskItem {
  return {
    id: 'brief-1',
    title: 'Test Brief',
    taxonomy_path: null,
    task_stage_id: null,
    assignee_id: null,
    assignee_name: null,
    editors,
    has_brief: false,
    has_brief_json: false,
    paid_count: 0,
    submission_count: 0,
    submit_url: null,
    created_at: '2026-09-01T00:00:00Z',
    assets: [],
    ...overrides,
  }
}

/** Renders one collapsed BriefRow. Collapsed on purpose for the brief-level
 *  assertions: an expanded row mounts the editor sub-rows, whose own pickers
 *  contribute their own comboboxes and their own "Unassigned" option. */
function renderRow(opts: {
  canAssign: boolean
  viewerId?: string
  editors?: BriefEditor[]
  brief?: Partial<BriefTaskItem>
}) {
  return render(
    <table>
      <tbody>
        <BriefRow
          brief={makeBrief(opts.editors, opts.brief)}
          stages={STAGES}
          owners={OWNERS}
          folderFilter={null}
          typeFilter="all"
          canAssign={opts.canAssign}
          viewerId={opts.viewerId}
          onDrillTo={() => {}}
        />
      </tbody>
    </table>,
  )
}

/** The row's last cell — the brief-level Status column. */
function statusCell() {
  const cells = screen.getByText('Test Brief').closest('tr')!.querySelectorAll('td')
  return within(cells[cells.length - 1] as HTMLElement)
}

/** Renders one BriefRow inside the table/tbody it expects as an ancestor, then
 *  expands it so the editor sub-rows (which only exist while expanded) mount. */
async function renderExpanded(opts: { canAssign: boolean; viewerId?: string; editors?: BriefEditor[] }) {
  const user = userEvent.setup()
  const utils = render(
    <table>
      <tbody>
        <BriefRow
          brief={makeBrief(opts.editors)}
          stages={STAGES}
          owners={OWNERS}
          folderFilter={null}
          typeFilter="all"
          canAssign={opts.canAssign}
          viewerId={opts.viewerId}
          onDrillTo={() => {}}
        />
      </tbody>
    </table>,
  )
  await user.click(screen.getByRole('button', { name: 'Expand' }))
  return { user, ...utils }
}

describe('BriefRow — who can move an editor status', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lets a non-admin move their own status but shows a co-editor’s read-only', async () => {
    // canAssign is false and viewerId matches only e-self — the case that
    // actually distinguishes the two branches of canMove.
    await renderExpanded({ canAssign: false, viewerId: 'e-self' })

    const ownRow = screen.getByText('Self Editor').closest('tr')!
    expect(within(ownRow).getByRole('combobox')).toBeInTheDocument()

    const coEditorRow = screen.getByText('Other Editor').closest('tr')!
    expect(within(coEditorRow).queryByRole('combobox')).toBeNull()
    expect(within(coEditorRow).getByText('Review')).toBeInTheDocument()
  })

  it('lets an admin move every editor’s status', async () => {
    await renderExpanded({ canAssign: true, viewerId: 'someone-not-on-the-brief' })

    const selfRow = screen.getByText('Self Editor').closest('tr')!
    const otherRow = screen.getByText('Other Editor').closest('tr')!
    expect(within(selfRow).getByRole('combobox')).toBeInTheDocument()
    expect(within(otherRow).getByRole('combobox')).toBeInTheDocument()
  })
})

describe('BriefRow — assigning an editor', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers the assign-editor control only to admins', async () => {
    const admin = await renderExpanded({ canAssign: true })
    expect(screen.getByText('Assign an editor…')).toBeInTheDocument()
    admin.unmount()

    await renderExpanded({ canAssign: false, viewerId: 'e-self' })
    expect(screen.queryByText('Assign an editor…')).toBeNull()
  })

  it('assigns nothing when the confirm dialog is declined', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { user } = await renderExpanded({ canAssign: true })

    const select = screen.getByText('Assign an editor…').closest('select') as HTMLSelectElement
    await user.selectOptions(select, 'u-new')

    expect(window.confirm).toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()
  })
})


describe('BriefRow — the owner column', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows a neutral placeholder, not “Unassigned”, when the owner is withheld', () => {
    // The server blanks assignee_id/assignee_name for an editor who is not the
    // owner, so this is what a non-admin actually receives for a brief that DOES
    // have an owner. "Unassigned" would tell them nobody is on the hook for it,
    // and on an admin board the same brief reads with a name — one of the two
    // would be wrong.
    renderRow({ canAssign: false, viewerId: 'e-self', editors: [EDITORS[0]] })

    const ownerCell = screen.getByText('Test Brief').closest('tr')!.querySelectorAll('td')[2]
    expect(ownerCell.textContent).toBe('\u2014')
    expect(screen.queryByText('Unassigned')).toBeNull()
  })

  it('still names the owner to the owner', () => {
    renderRow({
      canAssign: false,
      viewerId: 'u-owner',
      editors: [EDITORS[0]],
      brief: { assignee_id: 'u-owner', assignee_name: 'Owner Themself' },
    })

    expect(screen.getByText('Owner Themself')).toBeInTheDocument()
  })
})

describe('BriefRow — who can move the brief’s own status', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows a non-owner text, not a picker, because the PATCH would 404', () => {
    // PATCH /submission-links/{id}/task-stage admits admins and the brief's owner
    // only. Before the board widened to editors, every row on a non-admin's board
    // was one they owned, so the picker always worked; now it would reject every
    // change and snap back. The text itself is 'In Progress' — e-self's OWN stage,
    // not the brief's 's2' ('Review') — because the chips above this row count and
    // filter by the same reading; a row showing the brief's stage here would
    // disagree with the chip that selected it.
    renderRow({
      canAssign: false,
      viewerId: 'e-self',
      editors: [EDITORS[0]],
      brief: { task_stage_id: 's2' },
    })

    expect(statusCell().queryByRole('combobox')).toBeNull()
    expect(statusCell().getByText('In Progress')).toBeInTheDocument()
  })

  it('reads the read-only Status cell from the editor\'s own stage, not the brief\'s', () => {
    // The tasks-list chips above this table now count and filter by stageOf (an
    // editor's own status), built in lib/brief-stage.ts. This cell used to render
    // brief.task_stage_id directly instead of going through stageOf — a second,
    // drifted copy of that decision — so a non-admin could click a "Review 1" chip
    // and land on the one row it selected while that row's own Status column read
    // "In Progress". The two stages are given different names on purpose: if this
    // cell read either source, a same-named fixture would pass either way and
    // catch nothing.
    renderRow({
      canAssign: false,
      viewerId: 'e-self',
      editors: [EDITORS[0]],
      brief: { task_stage_id: 's2' },
    })

    expect(statusCell().getByText('In Progress')).toBeInTheDocument()
    expect(statusCell().queryByText('Review')).toBeNull()
  })

  it('keeps the picker live for a non-admin who owns the brief', () => {
    // The half that fails if the condition is inverted or dropped: an owner is the
    // one non-admin the endpoint accepts, and this is the only control they have
    // over the brief's own status.
    renderRow({
      canAssign: false,
      viewerId: 'u-owner',
      editors: [EDITORS[0]],
      brief: { assignee_id: 'u-owner', assignee_name: 'Owner Themself', task_stage_id: 's2' },
    })

    expect(statusCell().getByRole('combobox')).toBeInTheDocument()
  })

  it('keeps the picker live for an admin', () => {
    renderRow({ canAssign: true, brief: { task_stage_id: 's2' } })
    expect(statusCell().getByRole('combobox')).toBeInTheDocument()
  })
})

describe('BriefRow — reloading the board after a change', () => {
  beforeEach(() => vi.clearAllMocks())

  it('asks the tasks page to reload after the brief status moves', async () => {
    // The board is a paged list now, which a global mutate('/task-board') no
    // longer reaches. A change that does not reload it leaves a stale row.
    vi.mocked(api.patch).mockResolvedValue({} as never)
    const refresh = vi.fn()
    const user = userEvent.setup()
    render(
      <TaskBoardRefreshProvider value={refresh}>
        <table>
          <tbody>
            <BriefRow
              brief={makeBrief([])}
              stages={STAGES}
              owners={OWNERS}
              folderFilter={null}
              typeFilter="all"
              canAssign
              viewerId="u-admin"
              onDrillTo={() => {}}
            />
          </tbody>
        </table>
      </TaskBoardRefreshProvider>,
    )
    await user.selectOptions(statusCell().getByRole('combobox'), 'Review')
    await waitFor(() => expect(refresh).toHaveBeenCalled())
  })
})
