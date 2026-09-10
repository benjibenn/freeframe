/**
 * The feature in one test: an admin picks a brief and immediately sees the
 * structured brief, who uploaded, and a preview of what they uploaded — with no
 * navigation to an edit form or a per-submitter project.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { BriefOverviewTable, type BriefOverviewRow } from '../brief-overview-table'

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
    brief_json: { title: 'The test report', product: 'iPhone 17 Pro Max' },
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
    brief_json: null,
    reference_image_count: 1,
    reference_video_count: 0,
    submission_count: 0,
    asset_count: 0,
    submissions: [],
  },
]

describe('BriefOverviewTable', () => {
  it('lists every brief with its persona, angle and counts', () => {
    render(<BriefOverviewTable rows={ROWS} />)
    // One selectable row per brief. The title also appears in the detail header
    // for whichever row is selected, so assert on the list buttons specifically.
    expect(screen.getByRole('button', { name: /The test report/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Pick your side/ })).toBeInTheDocument()
    expect(screen.getAllByText('Nervous First-Time Buyer')).toHaveLength(2)
  })

  it('shows the uploader and a thumbnail of the upload when a brief is selected', async () => {
    const user = userEvent.setup()
    render(<BriefOverviewTable rows={ROWS} />)

    await user.click(screen.getByRole('button', { name: /The test report/ }))

    expect(screen.getByText('Ada Editor')).toBeInTheDocument()
    expect(screen.getByText('ada@example.com')).toBeInTheDocument()

    const thumb = screen.getByAltText('battery-report-v3.png')
    expect(thumb).toHaveAttribute('src', 'https://s3/thumb.jpg')
  })

  it('says so plainly when a brief has no submissions yet', async () => {
    const user = userEvent.setup()
    render(<BriefOverviewTable rows={ROWS} />)
    await user.click(screen.getByRole('button', { name: /Pick your side/ }))
    expect(screen.getByText(/no submissions yet/i)).toBeInTheDocument()
  })
})

describe('BriefOverviewTable — reference media', () => {
  it('renders the owner-uploaded reference images the brief was built from', async () => {
    const user = userEvent.setup()
    render(<BriefOverviewTable rows={ROWS} />)
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
    const { container } = render(<BriefOverviewTable rows={withVideo} />)
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
    render(<BriefOverviewTable rows={bare} />)
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
describe('BriefOverviewTable — filters', () => {
  it('narrows to briefs that actually have files when "Has files" is ticked', async () => {
    const user = userEvent.setup()
    render(<BriefOverviewTable rows={ROWS} />)

    await user.click(screen.getByLabelText(/has files/i))

    expect(screen.getByRole('button', { name: /The test report/ })).toBeInTheDocument()
    // Zero-file brief is gone from the list. Its title survives nowhere else,
    // since the detail pane falls through to the first visible brief.
    expect(screen.queryByRole('button', { name: /Pick your side/ })).toBeNull()
  })

  it('matches the name search against the title and the folder path', async () => {
    const user = userEvent.setup()
    render(<BriefOverviewTable rows={ROWS} />)
    const search = screen.getByLabelText(/search briefs by name/i)

    await user.type(search, 'pick your side')
    expect(screen.queryByRole('button', { name: /The test report/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Pick your side/ })).toBeInTheDocument()

    // The path is shown on the row, so it is fair game for the same box.
    await user.clear(search)
    await user.type(search, 'Iphone 17')
    expect(screen.getAllByRole('button', { name: /Iphone 17 Pro Max/ })).toHaveLength(2)
  })

  it('excludes briefs created outside the date range', async () => {
    const user = userEvent.setup()
    render(<BriefOverviewTable rows={ROWS} />)

    // Both briefs were created on 2026-09-10; a later "from" must empty the list
    // rather than silently ignoring the bound.
    await user.type(screen.getByLabelText(/created from/i), '2026-09-11')
    expect(screen.getByText(/no briefs match these filters/i)).toBeInTheDocument()
  })

  it('keeps a brief the filters hide from staying selected in the detail pane', async () => {
    const user = userEvent.setup()
    render(<BriefOverviewTable rows={ROWS} />)

    await user.click(screen.getByRole('button', { name: /Pick your side/ }))
    expect(screen.getByText(/no submissions yet/i)).toBeInTheDocument()

    // "Has files" hides the selected brief — the pane must move on, not keep
    // showing a brief that is no longer in the list.
    await user.click(screen.getByLabelText(/has files/i))
    expect(screen.queryByText(/no submissions yet/i)).toBeNull()
    expect(screen.getByText('Ada Editor')).toBeInTheDocument()
  })
})

describe('BriefOverviewTable — opening an upload', () => {
  it('links each uploaded file to its review screen with a route back here', async () => {
    const user = userEvent.setup()
    render(<BriefOverviewTable rows={ROWS} />)
    await user.click(screen.getByRole('button', { name: /The test report/ }))

    const link = screen.getByRole('link', { name: /battery-report-v3\.png/ })
    // project id comes from the SUBMISSION, asset id from the file: the review
    // route needs both, and the submitter's project is not the brief's home.
    expect(link).toHaveAttribute(
      'href',
      '/projects/p1/assets/f1?from=/admin/briefs',
    )
  })
})
