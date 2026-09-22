/**
 * The reports page's filter semantics.
 *
 * Intent encoded:
 * - one filter bar drives all four tabs, so switching tab must re-cut the SAME
 *   question rather than silently widen it;
 * - the summary tiles are recomputed from the filtered rows — tiles showing
 *   platform-wide numbers above a narrowed table would be actively misleading;
 * - "awaiting work" counts briefs with no files, which is exactly the row a
 *   file-derived view would delete, so briefs are filtered on their own dates;
 * - date bounds are compared as LOCAL calendar days, because `<input type="date">`
 *   emits a local day while the API returns UTC instants.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  NO_FILTERS,
  ReportsView,
  filterBriefs,
  filterFiles,
  filterUsers,
  localDay,
  visibleTotals,
  type ReportBriefRow,
  type ReportFileRow,
  type ReportPayload,
  type ReportUserRow,
} from '../reports-view'

const ALICE = '11111111-1111-1111-1111-111111111111'
const BOB = '22222222-2222-2222-2222-222222222222'

// Midday local time, so the local calendar day is unambiguous in any timezone
// the suite happens to run in.
const day = (d: string) => new Date(`${d}T12:00:00`).toISOString()

const brief = (over: Partial<ReportBriefRow> = {}): ReportBriefRow => ({
  id: 'b1',
  title: 'Hook test',
  home_path: 'ecom/Phones',
  created_at: day('2026-09-10'),
  is_enabled: true,
  persona_label: null,
  angle_label: null,
  submission_count: 1,
  file_count: 2,
  submitter_ids: [ALICE],
  submitter_names: ['Ali'],
  last_upload_at: day('2026-09-12'),
  ...over,
})

const user = (over: Partial<ReportUserRow> = {}): ReportUserRow => ({
  user_id: ALICE,
  name: 'Ali',
  email: 'ali@example.com',
  brief_count: 1,
  file_count: 2,
  last_upload_at: day('2026-09-12'),
  ...over,
})

const file = (over: Partial<ReportFileRow> = {}): ReportFileRow => ({
  asset_id: 'f1',
  name: 'cut-01.mp4',
  created_at: day('2026-09-12'),
  project_id: 'p1',
  brief_id: 'b1',
  brief_title: 'Hook test',
  user_id: ALICE,
  user_name: 'Ali',
  ...over,
})

describe('date handling', () => {
  it('reads a UTC instant as the viewer local calendar day', () => {
    expect(localDay(day('2026-09-10'))).toBe('2026-09-10')
  })

  it('keeps a brief created on the boundary day inside the range', () => {
    const rows = [brief({ created_at: day('2026-09-10') })]
    expect(filterBriefs(rows, { ...NO_FILTERS, from: '2026-09-10' })).toHaveLength(1)
    expect(filterBriefs(rows, { ...NO_FILTERS, to: '2026-09-10' })).toHaveLength(1)
    expect(filterBriefs(rows, { ...NO_FILTERS, from: '2026-09-11' })).toHaveLength(0)
  })

  it('excludes a person with no uploads once a range is set, but not before', () => {
    const rows = [user({ last_upload_at: null, file_count: 0 })]
    expect(filterUsers(rows, NO_FILTERS)).toHaveLength(1)
    expect(filterUsers(rows, { ...NO_FILTERS, from: '2026-09-01' })).toHaveLength(0)
  })
})

describe('submitter filter', () => {
  it('keeps a brief only when the chosen person actually submitted to it', () => {
    const rows = [
      brief({ id: 'mine', submitter_ids: [ALICE, BOB] }),
      brief({ id: 'theirs', submitter_ids: [BOB], submitter_names: ['Bo'] }),
    ]
    const kept = filterBriefs(rows, { ...NO_FILTERS, userId: ALICE })
    expect(kept.map((r) => r.id)).toEqual(['mine'])
  })

  it('narrows files and people to the chosen person', () => {
    const files = [file({ asset_id: 'a' }), file({ asset_id: 'b', user_id: BOB })]
    expect(filterFiles(files, { ...NO_FILTERS, userId: BOB }).map((f) => f.asset_id)).toEqual(['b'])
    expect(filterUsers([user(), user({ user_id: BOB })], { ...NO_FILTERS, userId: BOB })).toHaveLength(1)
  })
})

describe('search', () => {
  it('matches the whole line an admin can read, not one guessed field', () => {
    const rows = [brief()]
    for (const q of ['hook', 'Phones', 'Ali']) {
      expect(filterBriefs(rows, { ...NO_FILTERS, query: q })).toHaveLength(1)
    }
    expect(filterBriefs(rows, { ...NO_FILTERS, query: 'nothing' })).toHaveLength(0)
  })
})

describe('summary tiles', () => {
  it('counts what is on screen, not the whole platform', () => {
    const briefs = [brief({ id: 'b1' }), brief({ id: 'b2', file_count: 0, submission_count: 0 })]
    const totals = visibleTotals(briefs, [user()], [file()])
    expect(totals.brief_count).toBe(2)
    expect(totals.file_count).toBe(1)
    expect(totals.submitter_count).toBe(1)
  })

  it('counts a brief with submitters but no files as awaiting work', () => {
    const accepted = brief({ id: 'b2', file_count: 0, submission_count: 3 })
    expect(visibleTotals([accepted], [], []).briefs_awaiting_work).toBe(1)
    expect(visibleTotals([brief()], [], []).briefs_awaiting_work).toBe(0)
  })
})

describe('ReportsView', () => {
  const data: ReportPayload = {
    totals: {
      brief_count: 2,
      submission_count: 2,
      file_count: 1,
      submitter_count: 2,
      briefs_awaiting_work: 1,
    },
    briefs: [
      brief({ id: 'b1', title: 'Hook test' }),
      brief({
        id: 'b2',
        title: 'Untouched',
        file_count: 0,
        submission_count: 0,
        submitter_ids: [],
        submitter_names: [],
        last_upload_at: null,
      }),
    ],
    users: [user(), user({ user_id: BOB, name: 'Bo', email: 'bo@example.com', file_count: 0 })],
    files: [file()],
  }

  it('shows every tab and keeps one filter across them', async () => {
    const u = userEvent.setup()
    render(<ReportsView data={data} />)

    await u.type(screen.getByLabelText('Search'), 'Untouched')

    await u.click(screen.getByRole('button', { name: 'By brief' }))
    expect(screen.getByText('Untouched')).toBeInTheDocument()
    expect(screen.queryByText('Hook test')).not.toBeInTheDocument()

    // Same filter still applies after switching tab: the one matching brief has
    // no files, so the file tab is empty rather than showing everything again.
    await u.click(screen.getByRole('button', { name: 'Files' }))
    expect(screen.getByText('No files match these filters.')).toBeInTheDocument()
  })

  it('restores the full set when the filters are cleared', async () => {
    const u = userEvent.setup()
    render(<ReportsView data={data} />)

    await u.type(screen.getByLabelText('Search'), 'Untouched')
    await u.click(screen.getByRole('button', { name: 'By brief' }))
    expect(screen.queryByText('Hook test')).not.toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByText('Hook test')).toBeInTheDocument()
  })

  it('lists every submitter in the picker, including one who has uploaded nothing', () => {
    render(<ReportsView data={data} />)
    const picker = screen.getByLabelText('Submitter') as HTMLSelectElement
    expect(Array.from(picker.options).map((o) => o.textContent)).toEqual(['Everyone', 'Ali', 'Bo'])
  })
})
