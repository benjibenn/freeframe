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
