/**
 * The status chips and the pill on each tile both read this hook. /task-stages
 * is platform-admin only, so for anyone else it must report no stages at all —
 * otherwise the page renders a filter that cannot work and pills that cannot
 * be named.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'

let mockUser: { is_superadmin: boolean; is_subadmin: boolean } | null = null
vi.mock('@/stores/auth-store', () => ({ useAuthStore: () => ({ user: mockUser }) }))

import { SWRConfig } from 'swr'
import * as React from 'react'
import { useTaskStageOrder } from '../task-stages'

const STAGES = [
  { id: 's2', name: 'Needs review', position: 2, color: '#f59e0b', is_default: false },
  { id: 's1', name: 'In progress', position: 1, color: null, is_default: true },
]

function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    children,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUser = null
  vi.mocked(api.get).mockResolvedValue(STAGES as never)
})

describe('useTaskStageOrder', () => {
  it('fetches nothing for a non-admin, so the chip row disappears', async () => {
    const { result } = renderHook(() => useTaskStageOrder(), { wrapper })
    expect(result.current.available).toBe(false)
    expect(result.current.stages).toEqual([])
    expect(api.get).not.toHaveBeenCalled()
  })

  it('names the stage behind an id, for the pill on a tile', async () => {
    mockUser = { is_superadmin: true, is_subadmin: false }
    const { result, rerender } = renderHook(() => useTaskStageOrder(), { wrapper })
    await vi.waitFor(() => expect(result.current.stages).toHaveLength(2))
    rerender()
    expect(result.current.stageOf('s2')?.name).toBe('Needs review')
    expect(result.current.stageOf('s2')?.color).toBe('#f59e0b')
  })

  it('returns null for no stage, so an untriaged tile shows no pill', async () => {
    mockUser = { is_superadmin: true, is_subadmin: false }
    const { result } = renderHook(() => useTaskStageOrder(), { wrapper })
    await vi.waitFor(() => expect(result.current.stages).toHaveLength(2))
    expect(result.current.stageOf(null)).toBeNull()
    expect(result.current.stageOf(undefined)).toBeNull()
  })

  it('returns null for a stage that has since been deleted', async () => {
    // A deleted stage leaves its id on old assets. Rendering "undefined" there
    // would look like a bug in the pill rather than a stale stamp.
    mockUser = { is_superadmin: false, is_subadmin: true }
    const { result } = renderHook(() => useTaskStageOrder(), { wrapper })
    await vi.waitFor(() => expect(result.current.stages).toHaveLength(2))
    expect(result.current.stageOf('gone')).toBeNull()
  })
})
