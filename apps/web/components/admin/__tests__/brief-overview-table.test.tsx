/**
 * The feature in one test: an admin picks a brief and immediately sees the
 * structured brief, who uploaded, and a preview of what they uploaded — with no
 * navigation to an edit form or a per-submitter project.
 */
import { useEffect, useState } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SWRConfig } from 'swr'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
vi.mock('@/components/projects/brief-view', () => ({
  BriefView: ({ data }: { data: Record<string, unknown> }) => <p>brief: {String(data.title)}</p>,
}))
import { api } from '@/lib/api'
import { BriefOverviewTable, type BriefOverviewRow } from '../brief-overview-table'
import { NO_FILTERS, overviewQuery, type OverviewFilters } from '@/lib/brief-overview-query'

const ROWS: BriefOverviewRow[] = [
  {
    id: 'a1',
    token: 'tok-a1',
    title: 'The test report — iPhone 17 Pro Max',
    instructions: null,
    is_enabled: true,
    expires_at: null,
    created_at: '2026-09-10T02:51:30Z',
    home_project_id: null,
    home_folder_id: null,
    home_path: 'ecom/Phones/Store 1/Iphone 17 Pro Max',
    persona_label: 'Nervous First-Time Buyer',
    angle_label: 'Performance',
    problem: 'Battery health unknown',
    has_brief: false,
    has_brief_json: true,
    reference_image_count: 2,
    reference_video_count: 0,
    submission_count: 1,
    asset_count: 1,
    submissions: [
      {
        id: 's1',
        user_id: 'u1',
        user_name: 'Ada Editor',
        user_email: 'ada@example.com',
        display_name: null,
        project_id: 'p1',
        paid_at: null,
        created_at: '2026-09-10T03:00:00Z',
        asset_count: 1,
        files: [
          { asset_id: 'f1', name: 'battery-report-v3.png', thumbnail_url: 'https://s3/thumb.jpg' },
        ],
      },
    ],
  },
  {
    id: 'b2',
    token: 'tok-b2',
    title: 'Pick your side — iPhone 17 Pro Max',
    instructions: null,
    is_enabled: true,
    expires_at: null,
    created_at: '2026-09-10T02:32:55Z',
    home_project_id: null,
    home_folder_id: null,
    home_path: 'ecom/Phones/Store 1/Iphone 17 Pro Max',
    persona_label: 'Nervous First-Time Buyer',
    angle_label: 'Contrarian',
    problem: null,
    has_brief: false,
    has_brief_json: false,
    reference_image_count: 1,
    reference_video_count: 0,
    submission_count: 0,
    asset_count: 0,
    submissions: [],
  },
]

function Harness({ rows, onQuery }: { rows: BriefOverviewRow[]; onQuery?: (qs: string) => void }) {
  const [filters, setFilters] = useState<OverviewFilters>(NO_FILTERS)
  useEffect(() => {
    onQuery?.(overviewQuery(filters))
  }, [filters, onQuery])
  return (
    <BriefOverviewTable
      rows={rows}
      total={rows.length}
      filters={filters}
      onFiltersChange={setFilters}
      submitters={[{ id: 'u1', label: 'Ada Editor' }]}
    />
  )
}

function renderTable(rows: BriefOverviewRow[] = ROWS, onQuery?: (qs: string) => void) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <Harness rows={rows} onQuery={onQuery} />
    </SWRConfig>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockResolvedValue({ brief_json: { title: 'The test report' } } as never)
})

describe('BriefOverviewTable', () => {
  it('lists every brief with its persona, angle and counts', () => {
    renderTable()
    // One selectable row per brief. The title also appears in the detail header
    // for whichever row is selected, so assert on the list buttons specifically.
    expect(screen.getByRole('button', { name: /The test report/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Pick your side/ })).toBeInTheDocument()
    expect(screen.getAllByText('Nervous First-Time Buyer')).toHaveLength(2)
  })

  it('shows the uploader and a thumbnail of the upload when a brief is selected', async () => {
    const user = userEvent.setup()
    renderTable()

    await user.click(screen.getByRole('button', { name: /The test report/ }))

    // 'Ada Editor' also appears as an <option> in the submitter filter, so
    // scope to the detail pane's own paragraph.
    expect(screen.getByText('Ada Editor', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText('ada@example.com')).toBeInTheDocument()

    const thumb = screen.getByAltText('battery-report-v3.png')
    expect(thumb).toHaveAttribute('src', 'https://s3/thumb.jpg')
  })

  it('says so plainly when a brief has no submissions yet', async () => {
    const user = userEvent.setup()
    renderTable()
    await user.click(screen.getByRole('button', { name: /Pick your side/ }))
    expect(screen.getByText(/no submissions yet/i)).toBeInTheDocument()
  })
})

describe('BriefOverviewTable — reference media', () => {
  it('renders the owner-uploaded reference images the brief was built from', async () => {
    const user = userEvent.setup()
    renderTable()
    await user.click(screen.getByRole('button', { name: /The test report/ }))

    // Reference media is served by position off the public submit route, so the
    // count is the only thing the payload needs to carry.
    const refs = screen.getAllByAltText(/reference \d/i)
    expect(refs).toHaveLength(2)
    expect(refs[0]).toHaveAttribute('src', '/submit/tok-a1/reference-image/0')
    expect(refs[1]).toHaveAttribute('src', '/submit/tok-a1/reference-image/1')
  })

  it('renders a player per reference video', async () => {
    const user = userEvent.setup()
    const withVideo: BriefOverviewRow[] = [
      { ...ROWS[0], reference_image_count: 0, reference_video_count: 1 },
    ]
    const { container } = renderTable(withVideo)
    await user.click(screen.getByRole('button', { name: /The test report/ }))

    const videos = container.querySelectorAll('video')
    expect(videos).toHaveLength(1)
    expect(videos[0].getAttribute('src')).toBe('/submit/tok-a1/reference-video/0')
  })

  it('says nothing about references when the brief has none', async () => {
    const user = userEvent.setup()
    const bare: BriefOverviewRow[] = [
      { ...ROWS[0], reference_image_count: 0, reference_video_count: 0 },
    ]
    renderTable(bare)
    await user.click(screen.getByRole('button', { name: /The test report/ }))
    expect(screen.queryByText(/^references$/i)).toBeNull()
  })
})

/**
 * Filters and the jump-to-review link.
 *
 * These encode the working habit the feature exists for: an admin sweeping 98
 * briefs needs to cut down to the ones with actual work in them, find one by the
 * name on screen, and open that upload where it can be commented on — without
 * leaving this page to do any of it.
 */
describe('BriefOverviewTable — filters go to the server', () => {
  // The list is paged, so filtering what is loaded would hide matches that sit
  // on a later page. Each control becomes a query parameter instead.
  it('asks for briefs with files when "Has files" is ticked', async () => {
    const user = userEvent.setup()
    const onQuery = vi.fn()
    renderTable(ROWS, onQuery)
    await user.click(screen.getByLabelText(/has files/i))
    expect(onQuery).toHaveBeenLastCalledWith('has_files=true')
  })

  it('sends the name search as q', async () => {
    const user = userEvent.setup()
    const onQuery = vi.fn()
    renderTable(ROWS, onQuery)
    await user.type(screen.getByLabelText(/search briefs by name/i), 'pick')
    expect(onQuery).toHaveBeenLastCalledWith('q=pick')
  })

  it('sends a date bound as the start of that day in the viewer’s timezone', async () => {
    const user = userEvent.setup()
    const onQuery = vi.fn()
    renderTable(ROWS, onQuery)
    await user.type(screen.getByLabelText(/created from/i), '2026-09-11')
    const qs = new URLSearchParams(onQuery.mock.lastCall![0])
    expect(qs.get('created_from')).toBe(new Date('2026-09-11T00:00:00').toISOString())
  })

  it('moves the detail pane on when the selected brief drops out of the results', async () => {
    const user = userEvent.setup()
    const table = (rows: BriefOverviewRow[]) => (
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <BriefOverviewTable rows={rows} total={rows.length} filters={NO_FILTERS} onFiltersChange={() => {}} submitters={[]} />
      </SWRConfig>
    )
    const { rerender } = render(table(ROWS))
    await user.click(screen.getByRole('button', { name: /Pick your side/ }))
    expect(screen.getByText(/no submissions yet/i)).toBeInTheDocument()

    rerender(table([ROWS[0]]))
    expect(screen.queryByText(/no submissions yet/i)).toBeNull()
    expect(screen.getByText('Ada Editor', { selector: 'p' })).toBeInTheDocument()
  })
})

describe('BriefOverviewTable — the structured brief loads on open', () => {
  it('fetches the brief for the selected row', async () => {
    renderTable()
    expect(await screen.findByText('brief: The test report')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/submission-links/a1')
  })

  it('does not fetch for a brief that has no structured brief', async () => {
    const user = userEvent.setup()
    renderTable()
    await user.click(screen.getByRole('button', { name: /Pick your side/ }))
    expect(screen.getByText(/no structured brief attached/i)).toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalledWith('/submission-links/b2')
  })
})

describe('BriefOverviewTable — opening an upload', () => {
  it('links each uploaded file to its review screen with a route back here', async () => {
    const user = userEvent.setup()
    renderTable()
    await user.click(screen.getByRole('button', { name: /The test report/ }))

    const link = screen.getByRole('link', { name: /battery-report-v3\.png/ })
    // project id comes from the SUBMISSION, asset id from the file: the review
    // route needs both, and the submitter's project is not the brief's home.
    expect(link).toHaveAttribute(
      'href',
      '/projects/p1/assets/f1?from=/admin/briefs',
    )
  })

  it('opens uploads in a new tab so the sweep keeps its filters and scroll', async () => {
    const user = userEvent.setup()
    renderTable()
    await user.click(screen.getByRole('button', { name: /The test report/ }))

    const link = screen.getByRole('link', { name: /battery-report-v3\.png/ })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer')
  })
})

describe('BriefOverviewTable — sharing a brief with editors', () => {
  // userEvent.setup() installs its own clipboard stub, so these assert on what
  // actually landed on the clipboard rather than on the call that put it there.
  it('copies the token-gated submit URL, not an admin-only route', async () => {
    const user = userEvent.setup()
    renderTable()
    await user.click(screen.getByRole('button', { name: /The test report/ }))
    await user.click(screen.getByRole('button', { name: /copy brief link/i }))

    // An editor has no dashboard account, so the link must be the public
    // /submit/<token> page — anything under /admin or /projects would 404 them.
    expect(await navigator.clipboard.readText()).toBe('http://localhost:3000/submit/tok-a1')
    expect(await screen.findByText(/copied/i)).toBeInTheDocument()
  })

  it('offers the link of whichever brief is selected, not the first one', async () => {
    const user = userEvent.setup()
    renderTable()
    await user.click(screen.getByRole('button', { name: /Pick your side/ }))
    await user.click(screen.getByRole('button', { name: /copy brief link/i }))

    expect(await navigator.clipboard.readText()).toBe('http://localhost:3000/submit/tok-b2')
  })
})
