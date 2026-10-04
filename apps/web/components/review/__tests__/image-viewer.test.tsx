/**
 * A carousel used to request a /stream URL for every slide before showing the
 * first: one round trip per image, all in front of the first picture. Only the
 * slide on screen and the next one are asked for now, each by its own file id.
 */
import * as React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
vi.mock('react-zoom-pan-pinch', () => ({
  TransformWrapper: ({ children }: { children: unknown }) => (
    <>{typeof children === 'function' ? (children as () => React.ReactNode)() : (children as React.ReactNode)}</>
  ),
  TransformComponent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useControls: () => ({ zoomIn() {}, zoomOut() {}, resetTransform() {}, centerView() {} }),
}))
import { api } from '@/lib/api'
import { ImageViewer } from '../image-viewer'
import type { Asset, AssetVersion, MediaFile } from '@/types'

function file(id: string, order: number): MediaFile {
  return {
    id, version_id: 'v1', file_type: 'image', original_filename: `${id}.png`,
    mime_type: 'image/png', file_size_bytes: 1, s3_key_raw: `raw/${id}`,
    s3_key_processed: null, s3_key_thumbnail: null, width: null, height: null,
    duration_seconds: null, fps: null, sequence_order: order,
  } as unknown as MediaFile
}

const ASSET = { id: 'a1', name: 'carousel', asset_type: 'image_carousel' } as unknown as Asset
const VERSION = {
  id: 'v1', asset_id: 'a1', version_number: 1, processing_status: 'ready',
  // Out of order on purpose: slides are shown by sequence_order.
  files: [file('f3', 3), file('f1', 1), file('f2', 2), file('f4', 4)],
} as unknown as AssetVersion

const streamCalls = () =>
  vi.mocked(api.get).mock.calls.map(([u]) => String(u)).filter((u) => u.includes('/stream'))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockImplementation(((url: string) => {
    const id = new URL(url, 'http://x').searchParams.get('media_file_id')
    return Promise.resolve({ url: `https://s3/${id}` })
  }) as never)
})

describe('ImageViewer — carousel', () => {
  it('asks only for the slide on screen and the next one', async () => {
    render(<ImageViewer asset={ASSET} version={VERSION} />)
    expect(await screen.findByAltText('carousel')).toHaveAttribute('src', 'https://s3/f1')
    expect(streamCalls()).toEqual([
      '/assets/a1/stream?media_file_id=f1&version_id=v1',
      '/assets/a1/stream?media_file_id=f2&version_id=v1',
    ])
  })

  it('fetches one more slide per step and never re-fetches one it has', async () => {
    const user = userEvent.setup()
    render(<ImageViewer asset={ASSET} version={VERSION} />)
    await screen.findByAltText('carousel')

    await user.click(screen.getByRole('button', { name: 'Next image' }))
    await waitFor(() =>
      expect(screen.getByAltText('carousel')).toHaveAttribute('src', 'https://s3/f2'),
    )
    await waitFor(() => expect(streamCalls()).toHaveLength(3))
    expect(streamCalls()[2]).toBe('/assets/a1/stream?media_file_id=f3&version_id=v1')

    await user.click(screen.getByRole('button', { name: 'Previous image' }))
    expect(streamCalls()).toHaveLength(3)
  })
})
