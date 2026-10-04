/**
 * `stageOf` is what decides which column a card sits in and which endpoint a
 * drag writes, and it means two different things for the two audiences: an
 * admin's roll-up status vs. an editor's own status. These tests render the
 * board (no drag simulation needed — grouping is observable from a plain
 * render) and check which column each card lands in.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))

import { PipelineBoard } from '../pipeline-board'
import type { BriefEditor, BriefTaskItem, TaskStage } from '@/types'

const STAGES: TaskStage[] = [
  { id: 's1', name: 'In Progress', position: 1, color: null, is_default: false },
  { id: 's2', name: 'Review', position: 2, color: null, is_default: false },
]

function makeBrief(overrides: Partial<BriefTaskItem> & { editors?: BriefEditor[] } = {}): BriefTaskItem {
  return {
    id: 'brief-1',
    title: 'Test Brief',
    taxonomy_path: null,
    task_stage_id: null,
    assignee_id: null,
    assignee_name: null,
    editors: [],
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

function columnItems(name: string) {
  const heading = screen.getByText(name)
  const column = heading.closest('div')!.parentElement!
  return within(column)
}

describe('PipelineBoard — whose status a card is grouped by', () => {
  it("groups an admin's card by the brief's own status", () => {
    const brief = makeBrief({
      task_stage_id: 's1',
      editors: [{ id: 'e1', name: 'Editor One', email: 'e1@example.com', task_stage_id: 's2' }],
    })
    render(
      <PipelineBoard
        briefs={[brief]}
        stages={STAGES}
        folderFilter={null}
        canManage
        viewerId="admin-1"
        stageCounts={{}}
      />,
    )

    expect(columnItems('In Progress').getByText('Test Brief')).toBeInTheDocument()
    expect(columnItems('Review').queryByText('Test Brief')).toBeNull()
  })

  it("groups a non-admin's card by their own editor status, not the brief's", () => {
    const brief = makeBrief({
      task_stage_id: 's1',
      editors: [{ id: 'viewer-1', name: 'Viewer', email: 'viewer@example.com', task_stage_id: 's2' }],
    })
    render(
      <PipelineBoard
        briefs={[brief]}
        stages={STAGES}
        folderFilter={null}
        canManage={false}
        viewerId="viewer-1"
        stageCounts={{}}
      />,
    )

    expect(columnItems('Review').getByText('Test Brief')).toBeInTheDocument()
    expect(columnItems('In Progress').queryByText('Test Brief')).toBeNull()
  })

  it('falls back to the brief status for a non-admin owner with no editor row of their own', () => {
    const brief = makeBrief({
      task_stage_id: 's1',
      assignee_id: 'owner-1',
      editors: [{ id: 'someone-else', name: 'Other', email: 'other@example.com', task_stage_id: 's2' }],
    })
    render(
      <PipelineBoard
        briefs={[brief]}
        stages={STAGES}
        folderFilter={null}
        canManage={false}
        viewerId="owner-1"
        stageCounts={{}}
      />,
    )

    expect(columnItems('In Progress').getByText('Test Brief')).toBeInTheDocument()
    expect(columnItems('Review').queryByText('Test Brief')).toBeNull()
  })
})

describe('PipelineBoard — the owner pill on a card with no visible owner', () => {
  // assignee_name: null means two different things depending on who is looking:
  // for an admin it is true — the brief really has no owner, and that is theirs
  // to fix. For a non-admin it is the server withholding an owner they are not
  // allowed to see, not a brief that has none. The `(brief.assignee_name ||
  // canManage)` gate on the pill is what keeps those apart; nothing today asserts
  // it survives, so restoring an unconditional pill — which would tell a non-admin
  // "Unassigned" about a brief someone else already owns — would break nothing in
  // CI. This locks in both halves of the gate at once.
  it('hides the pill from a non-admin but shows it to an admin, for the same null owner', () => {
    // Scoped to the card itself: the "Unassigned" column header renders
    // unconditionally regardless of the pill, so a bare screen.getByText('Unassigned')
    // would pass whether or not the card grew its own pill back.
    const brief = makeBrief({ task_stage_id: 's1', assignee_name: null })

    const nonAdmin = render(
      <PipelineBoard
        briefs={[brief]}
        stages={STAGES}
        folderFilter={null}
        canManage={false}
        viewerId="someone"
        stageCounts={{}}
      />,
    )
    const nonAdminCard = screen.getByText('Test Brief').closest('[draggable]') as HTMLElement
    expect(within(nonAdminCard).queryByText('Unassigned')).toBeNull()
    nonAdmin.unmount()

    render(
      <PipelineBoard
        briefs={[brief]}
        stages={STAGES}
        folderFilter={null}
        canManage
        viewerId="admin-1"
        stageCounts={{}}
      />,
    )
    const adminCard = screen.getByText('Test Brief').closest('[draggable]') as HTMLElement
    expect(within(adminCard).getByText('Unassigned')).toBeInTheDocument()
  })
})

describe('PipelineBoard — column header counts', () => {
  it('shows the server stage_counts total, not the number of rows actually loaded', () => {
    // The board pages in 25 at a time, so a column can hold far more briefs on
    // the server than the page has fetched into `briefs` so far. Before this
    // fix the header read items.length (the loaded rows in that column), which
    // undercounts everything not yet fetched — and the scroll sentinel sits
    // below the columns, so a tall column could hide the undercounted rest of
    // the board from ever loading.
    const brief = makeBrief({ task_stage_id: 's2' })
    render(
      <PipelineBoard
        briefs={[brief]}
        stages={STAGES}
        folderFilter={null}
        canManage
        viewerId="admin-1"
        stageCounts={{ s1: 3, s2: 40, unassigned: 2 }}
      />,
    )

    const header = screen.getByText('Review').closest('div')!
    expect(within(header).getByText('40')).toBeInTheDocument()
    expect(within(header).queryByText('1')).toBeNull()
  })

  it("reads the 'unassigned' key for the Unassigned column, not a stage id", () => {
    // assignee_name is set so the card's own owner pill reads a name, not the
    // literal text "Unassigned" — otherwise that pill and the column header
    // would tie on getByText('Unassigned').
    const brief = makeBrief({ task_stage_id: null, assignee_name: 'Someone' })
    render(
      <PipelineBoard
        briefs={[brief]}
        stages={STAGES}
        folderFilter={null}
        canManage
        viewerId="admin-1"
        stageCounts={{ unassigned: 7, s1: 0, s2: 0 }}
      />,
    )

    const header = screen.getByText('Unassigned').closest('div')!
    expect(within(header).getByText('7')).toBeInTheDocument()
  })
})
