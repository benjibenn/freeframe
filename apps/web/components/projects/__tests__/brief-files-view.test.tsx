/**
 * Editors' work is not filed in the brief's folder: each editor submits into
 * their own project. Opening a brief from the folder view must still show those
 * files on one screen, and each file must open in the editor's project, where
 * the file actually is.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SWRConfig } from 'swr'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
import { BriefFilesView } from '../brief-files-view'

const SUBS = [
  { id: 's1', user_name: 'genesis', user_email: 'g@x.com', display_name: null, project_id: 'ed1', asset_count: 2 },
  { id: 's2', user_name: 'mia', user_email: 'm@x.com', display_name: 'Mia K', project_id: 'ed2', asset_count: 1 },
]
const FILES: Record<string, { id: string; name: string; thumbnail_url: string | null }[]> = {
  '/projects/ed1/assets': [
    { id: 'f1', name: 'French — French · EUR', thumbnail_url: 'https://cdn/f1.jpg' },
    { id: 'f2', name: 'Swedish — Swedish · SEK', thumbnail_url: null },
  ],
  '/projects/ed2/assets': [{ id: 'f3', name: 'Norwegian — Norwegian · NOK', thumbnail_url: null }],
}

function renderView() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <BriefFilesView briefId="b1" />
    </SWRConfig>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockImplementation(((url: string) =>
    Promise.resolve(url === '/submission-links/b1/submissions' ? SUBS : FILES[url] ?? [])) as never)
})

describe('BriefFilesView', () => {
  it("lists every editor's files, each linking into that editor's project", async () => {
    renderView()
    const french = await screen.findByText('French — French · EUR')
    expect(french.closest('a')).toHaveAttribute('href', '/projects/ed1/assets/f1')
    const norwegian = await screen.findByText('Norwegian — Norwegian · NOK')
    expect(norwegian.closest('a')).toHaveAttribute('href', '/projects/ed2/assets/f3')
    expect(screen.getByText('Swedish — Swedish · SEK')).toBeInTheDocument()
    // Display name wins over the account name, as on the brief settings page.
    expect(screen.getByText('Mia K')).toBeInTheDocument()
  })

  it('says so when no editor has submitted yet', async () => {
    vi.mocked(api.get).mockResolvedValue([] as never)
    renderView()
    expect(await screen.findByText('No submissions yet')).toBeInTheDocument()
  })
})
