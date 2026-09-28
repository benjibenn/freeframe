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
      <PipelineBoard briefs={[brief]} stages={STAGES} folderFilter={null} canManage viewerId="admin-1" />,
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
      />,
    )

    expect(columnItems('In Progress').getByText('Test Brief')).toBeInTheDocument()
    expect(columnItems('Review').queryByText('Test Brief')).toBeNull()
  })
})
