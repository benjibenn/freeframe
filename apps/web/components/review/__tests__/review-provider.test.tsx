/**
 * Opening a file used to wait for three round trips in a row: the asset, then its
 * versions, then comments. The asset and its versions do not depend on each other,
 * so they are asked for together. The provider's own unscoped comment list is not
 * fetched outside share mode. The page reads comments through useComments, per
 * version, and nothing else on that page read the provider's copy.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
import { ReviewProvider, useReview } from '../review-provider'

function Probe() {
  const { asset, versions, isLoading } = useReview()
  return <p>{isLoading ? 'loading' : `${asset?.name} · ${versions.length} versions`}</p>
}

const ASSET = { id: 'a1', name: 'hook.mp4', asset_type: 'video', latest_version: null }
const VERSIONS = [
  { id: 'v1', asset_id: 'a1', version_number: 1, processing_status: 'ready', files: [] },
]

describe('ReviewProvider — authenticated mode', () => {
  let resolvers: Record<string, (v: unknown) => void>

  beforeEach(() => {
    vi.clearAllMocks()
    resolvers = {}
    vi.mocked(api.get).mockImplementation(((url: string) =>
      new Promise((resolve) => {
        resolvers[url] = resolve
      })) as never)
  })

  it('asks for the asset and its versions together', async () => {
    render(
      <ReviewProvider assetId="a1">
        <Probe />
      </ReviewProvider>,
    )
    // Neither request has been answered, and both are already in flight.
    await waitFor(() =>
      expect(Object.keys(resolvers).sort()).toEqual(['/assets/a1', '/assets/a1/versions']),
    )
    await act(async () => {
      resolvers['/assets/a1'](ASSET)
      resolvers['/assets/a1/versions'](VERSIONS)
    })
    expect(await screen.findByText('hook.mp4 · 1 versions')).toBeInTheDocument()
  })

  it('does not fetch the unscoped comment list the page never reads', async () => {
    render(
      <ReviewProvider assetId="a1">
        <Probe />
      </ReviewProvider>,
    )
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/assets/a1/versions'))
    expect(api.get).not.toHaveBeenCalledWith('/assets/a1/comments')
  })
})
