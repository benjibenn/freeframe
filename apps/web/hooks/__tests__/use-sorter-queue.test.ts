import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))
import { api } from '@/lib/api'
import { useSorterQueue } from '../use-sorter-queue'

const A = (id: string) => ({ id, keywords: [] })

beforeEach(() => {
  vi.mocked(api.get).mockReset()
})

describe('useSorterQueue', () => {
  it('loads assets and navigates with clamping', async () => {
    vi.mocked(api.get).mockResolvedValue([A('1'), A('2'), A('3')] as never)
    const { result } = renderHook(() => useSorterQueue('proj-1'))
    await waitFor(() => expect(result.current.assets.length).toBe(3))

    expect(result.current.current?.id).toBe('1')
    act(() => result.current.prev()) // clamps at 0
    expect(result.current.index).toBe(0)
    act(() => result.current.next())
    expect(result.current.current?.id).toBe('2')
  })

  it('removeCurrent drops the asset and keeps index valid', async () => {
    vi.mocked(api.get).mockResolvedValue([A('1'), A('2')] as never)
    const { result } = renderHook(() => useSorterQueue('proj-1'))
    await waitFor(() => expect(result.current.assets.length).toBe(2))
    act(() => result.current.removeCurrent())
    expect(result.current.assets.map((a) => a.id)).toEqual(['2'])
    expect(result.current.current?.id).toBe('2')
  })

  it('requests the tag filter and exclude_archived when provided', async () => {
    vi.mocked(api.get).mockResolvedValue([] as never)
    renderHook(() => useSorterQueue('proj-1', 'hook'))
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    const url: string = vi.mocked(api.get).mock.calls[0][0] as string
    expect(url).toContain('tag=hook')
    expect(url).toContain('exclude_archived=true')
  })
})
