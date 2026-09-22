/**
 * The reports page's scoping rules.
 *
 * The first version of this page shipped a real bug: a date range filtered which
 * ROWS survived but rendered all-time counts inside them, so a two-day window
 * showed one person's 129 lifetime briefs. The first describe block below exists
 * to make that specific failure impossible to reintroduce.
 *
 * Intent encoded:
 * - a count must always mean "inside the window", never "ever";
 * - a brief only appears when it RECEIVED FILES in the window — a brief created
 *   in the window with nothing uploaded is an empty folder, not work;
 * - "awaiting work" deliberately ignores the window, because narrowing to briefs
 *   that got work and then counting briefs with no work always yields zero;
 * - search hides rows without redefining any count;
 * - date bounds compare as LOCAL calendar days, since `<input type="date">`
 *   emits a local day while the API returns UTC instants.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  NO_FILTERS,
  ReportsView,
  awaitingWork,
  localDay,
  scopeBriefs,
  scopeFiles,
  scopeUsers,
  totalsFor,
  type Filters,
  type ReportBriefRow,
  type ReportFileRow,
  type ReportPayload,
  type ReportUserRow,
} from '../reports-view'

const ALICE = '11111111-1111-1111-1111-111111111111'
const BOB = '22222222-2222-2222-2222-222222222222'

// Midday local time, so the local calendar day is unambiguous wherever this runs.
const day = (d: string) => new Date(`${d}T12:00:00`).toISOString()

const brief = (over: Partial<ReportBriefRow> = {}): ReportBriefRow => ({
  id: 'b1',
  title: 'Hook test',
  home_path: 'ecom/Phones',
  created_at: day('2026-01-05'),
  is_enabled: true,
  persona_label: null,
  angle_label: null,
  submitters: [{ user_id: ALICE, name: 'Ali', submitted_at: day('2026-01-06') }],
  ...over,
})

const person = (over: Partial<ReportUserRow> = {}): ReportUserRow => ({
  user_id: ALICE,
  name: 'Ali',
  email: 'ali@example.com',
  ...over,
})

const file = (over: Partial<ReportFileRow> = {}): ReportFileRow => ({
  asset_id: 'f1',
  name: 'cut-01.mp4',
  created_at: day('2026-09-22'),
  project_id: 'p1',
  brief_id: 'b1',
  brief_title: 'Hook test',
  user_id: ALICE,
  user_name: 'Ali',
  ...over,
})

const WINDOW: Filters = { ...NO_FILTERS, from: '2026-09-21', to: '2026-09-22' }

describe('a windowed count never reports lifetime work', () => {
  // The regression: 2 files in the window, 3 before it. The old code showed 5.
  const files = [
    file({ asset_id: 'in1', brief_id: 'b1', created_at: day('2026-09-21') }),
    file({ asset_id: 'in2', brief_id: 'b2', created_at: day('2026-09-22') }),
    file({ asset_id: 'old1', brief_id: 'b3', created_at: day('2026-03-01') }),
    file({ asset_id: 'old2', brief_id: 'b4', created_at: day('2026-04-01') }),
    file({ asset_id: 'old3', brief_id: 'b5', created_at: day('2026-05-01') }),
  ]
  const briefs = ['b1', 'b2', 'b3', 'b4', 'b5'].map((id) => brief({ id, title: id }))
  const scoped = scopeFiles(files, WINDOW)

  it('counts only the files uploaded inside the window', () => {
    expect(scoped).toHaveLength(2)
  })

  it('credits a person with the briefs they uploaded into IN the window', () => {
    const rows = scopeUsers([person()], scoped, WINDOW)
    expect(rows).toHaveLength(1)
    // Two briefs touched in the window, not the five they have ever touched.
    expect(rows[0].brief_count).toBe(2)
    expect(rows[0].file_count).toBe(2)
    expect(localDay(rows[0].last_upload_at!)).toBe('2026-09-22')
  })

  it('lists only the briefs that received files in the window', () => {
    const rows = scopeBriefs(briefs, scoped, WINDOW)
    expect(rows.map((r) => r.id).sort()).toEqual(['b1', 'b2'])
    expect(rows.every((r) => r.file_count === 1)).toBe(true)
  })

  it('drops a brief created in the window that received nothing', () => {
    // Explicitly Ben's call: an empty folder is not work, whenever it was made.
    const fresh = brief({ id: 'empty', created_at: day('2026-09-21'), submitters: [] })
    expect(scopeBriefs([fresh], scoped, WINDOW).map((r) => r.id)).not.toContain('empty')
  })

  it('drops a person who uploaded nothing in the window', () => {
    expect(scopeUsers([person({ user_id: BOB, name: 'Bo' })], scoped, WINDOW)).toHaveLength(0)
  })
})

describe('window boundaries', () => {
  it('reads a UTC instant as the viewer local calendar day', () => {
    expect(localDay(day('2026-09-10'))).toBe('2026-09-10')
  })

  it('keeps a file uploaded on either boundary day', () => {
    const files = [
      file({ asset_id: 'a', created_at: day('2026-09-21') }),
      file({ asset_id: 'b', created_at: day('2026-09-22') }),
      file({ asset_id: 'c', created_at: day('2026-09-23') }),
    ]
    expect(scopeFiles(files, WINDOW).map((f) => f.asset_id)).toEqual(['a', 'b'])
  })

  it('counts everything when no window is set', () => {
    const files = [file({ asset_id: 'a' }), file({ asset_id: 'b', created_at: day('2020-01-01') })]
    expect(scopeFiles(files, NO_FILTERS)).toHaveLength(2)
  })
})

describe('submitter filter', () => {
  const files = [
    file({ asset_id: 'a', user_id: ALICE, user_name: 'Ali' }),
    file({ asset_id: 'b', user_id: BOB, user_name: 'Bo', brief_id: 'b2' }),
  ]

  it('scopes counts to the chosen person, not just the visible rows', () => {
    const mine: Filters = { ...NO_FILTERS, userId: BOB }
    const scoped = scopeFiles(files, mine)
    expect(scoped.map((f) => f.asset_id)).toEqual(['b'])
    const rows = scopeUsers([person(), person({ user_id: BOB, name: 'Bo' })], scoped, mine)
    expect(rows).toHaveLength(1)
    expect(rows[0].file_count).toBe(1)
  })
})

describe('submissions are accepts, not uploads', () => {
  it('counts people who accepted inside the window', () => {
    const b = brief({
      submitters: [
        { user_id: ALICE, name: 'Ali', submitted_at: day('2026-09-21') },
        { user_id: BOB, name: 'Bo', submitted_at: day('2026-01-01') },
      ],
    })
    const scoped = scopeFiles([file()], WINDOW)
    const [row] = scopeBriefs([b], scoped, WINDOW)
    // Bo accepted in January; only Ali's accept lands in the window.
    expect(row.submitter_count).toBe(1)
    // Uploaders are a separate list: who delivered, regardless of when they joined.
    expect(row.uploader_names).toEqual(['Ali'])
  })
})

describe('awaiting work ignores the window on purpose', () => {
  const briefs = [brief({ id: 'done' }), brief({ id: 'never' })]
  const allFiles = [file({ brief_id: 'done' })]

  it('counts briefs that have never received a file', () => {
    expect(awaitingWork(briefs, allFiles, NO_FILTERS)).toBe(1)
  })

  it('stays meaningful inside a window, where a scoped count would be zero', () => {
    // scopeBriefs returns only briefs WITH files, so counting "no files" among
    // them is always 0. This is why the tile is computed from the full set.
    const scoped = scopeFiles(allFiles, WINDOW)
    expect(scopeBriefs(briefs, scoped, WINDOW).filter((b) => b.file_count === 0)).toHaveLength(0)
    expect(awaitingWork(briefs, allFiles, WINDOW)).toBe(1)
  })

  it('answers per person when a submitter is chosen', () => {
    const accepted = brief({
      id: 'bobs',
      submitters: [{ user_id: BOB, name: 'Bo', submitted_at: day('2026-01-01') }],
    })
    // Bo accepted one brief and delivered nothing.
    expect(awaitingWork([accepted], allFiles, { ...NO_FILTERS, userId: BOB })).toBe(1)
    // Alice never accepted it, so it is not hers to be awaiting.
    expect(awaitingWork([accepted], allFiles, { ...NO_FILTERS, userId: ALICE })).toBe(0)
  })
})

describe('totals', () => {
  it('report the scoped rows', () => {
    const scoped = scopeFiles([file(), file({ asset_id: 'f2' })], WINDOW)
    const briefs = scopeBriefs([brief()], scoped, WINDOW)
    const users = scopeUsers([person()], scoped, WINDOW)
    const t = totalsFor(briefs, users, scoped, 7)
    expect(t).toEqual({
      brief_count: 1,
      submission_count: 0, // Ali accepted in January, outside the window.
      file_count: 2,
      submitter_count: 1,
      briefs_awaiting_work: 7,
    })
  })
})

describe('ReportsView', () => {
  const data: ReportPayload = {
    briefs: [brief({ id: 'b1', title: 'Hook test' }), brief({ id: 'b2', title: 'Untouched' })],
    users: [person(), person({ user_id: BOB, name: 'Bo', email: 'bo@example.com' })],
    files: [
      file({ asset_id: 'f1', brief_id: 'b1', brief_title: 'Hook test' }),
      file({ asset_id: 'f2', brief_id: 'b1', brief_title: 'Hook test', user_id: BOB, user_name: 'Bo' }),
    ],
  }

  it('shows the brief that got files and hides the one that did not', async () => {
    const u = userEvent.setup()
    render(<ReportsView data={data} />)
    await u.click(screen.getByRole('button', { name: 'By brief' }))
    expect(screen.getByText('Hook test')).toBeInTheDocument()
    expect(screen.queryByText('Untouched')).not.toBeInTheDocument()
  })

  it('search hides rows without changing a count', async () => {
    const u = userEvent.setup()
    render(<ReportsView data={data} />)

    await u.click(screen.getByRole('button', { name: 'By user' }))
    // Query by cell, not by text: the names also appear as <option>s in the
    // submitter picker, which search does not touch.
    expect(screen.getByRole('cell', { name: 'Bo' })).toBeInTheDocument()

    // Both delivered one file each; searching for one must not alter the other's
    // number, only remove the row.
    await u.type(screen.getByLabelText('Search'), 'Ali')
    expect(screen.queryByRole('cell', { name: 'Bo' })).not.toBeInTheDocument()
    const alice = screen.getByRole('cell', { name: 'Ali' }).closest('tr')!
    expect(alice.textContent).toContain('ali@example.com')
    // Still 1 brief / 1 file — the search removed a row, not a file.
    expect(Array.from(alice.cells).map((c) => c.textContent)).toEqual([
      'Ali',
      'ali@example.com',
      '1',
      '1',
      'Sep 22, 2026',
    ])
  })

  it('explains the window instead of silently dropping briefs', async () => {
    const u = userEvent.setup()
    render(<ReportsView data={data} />)
    expect(screen.queryByText(/Briefs with no uploads/)).not.toBeInTheDocument()
    await u.type(screen.getByLabelText('From date'), '2026-09-21')
    expect(screen.getByText(/Briefs with no uploads in that window are not listed/)).toBeInTheDocument()
  })

  it('marks the awaiting-work tile as all time so it is not read as windowed', () => {
    render(<ReportsView data={data} />)
    expect(screen.getByText('Awaiting work')).toBeInTheDocument()
    expect(screen.getByText('all time')).toBeInTheDocument()
  })

  it('lists every submitter in the picker, including one who delivered nothing', () => {
    render(<ReportsView data={data} />)
    const picker = screen.getByLabelText('Submitter') as HTMLSelectElement
    expect(Array.from(picker.options).map((o) => o.textContent)).toEqual(['Everyone', 'Ali', 'Bo'])
  })
})
