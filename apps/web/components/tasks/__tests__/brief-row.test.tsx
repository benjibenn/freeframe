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
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
import { api } from '@/lib/api'

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

function makeBrief(editors: BriefEditor[] = EDITORS): BriefTaskItem {
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
  }
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
