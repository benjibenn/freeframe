import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SWRConfig } from 'swr'
import HubPage from '../page'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'

function renderHub() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <HubPage />
    </SWRConfig>,
  )
}

describe('HubPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders a tile per launchable app', async () => {
    vi.mocked(api.get).mockResolvedValue({
      apps: [
        { slug: 'freeframe', name: 'FreeFrame', launch_url: 'https://review.x', description: 'Review', icon: null },
        { slug: 'adstash', name: 'Adstash', launch_url: 'https://woof.x', description: 'Ads', icon: null },
      ],
    })
    renderHub()
    expect(await screen.findByText('FreeFrame')).toBeInTheDocument()
    expect(screen.getByText('Adstash')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /FreeFrame/i })).toHaveAttribute('href', 'https://review.x')
  })

  it('shows the empty state when no apps are assigned', async () => {
    vi.mocked(api.get).mockResolvedValue({ apps: [] })
    renderHub()
    expect(await screen.findByText(/no tools/i)).toBeInTheDocument()
  })

  it('shows an error state (and NO tiles) when the endpoint fails', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('boom'))
    renderHub()
    expect(await screen.findByText(/couldn.t load your tools/i)).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
