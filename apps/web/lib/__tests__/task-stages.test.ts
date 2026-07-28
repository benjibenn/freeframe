/**
 * Pipeline-stage ordering — the backing logic for the grid's "Status" sort after
 * review status was removed from the product.
 *
 * Intent encoded:
 * - assets order by their stage's admin-configured `position`, not by stage id or
 *   name, so renaming or reordering stages in settings immediately changes the sort;
 * - assets with no stage sort AFTER every real stage, so untriaged work collects at
 *   the end of an ascending sort instead of leading it;
 * - /task-stages is platform-admin only, so `available` is false for everyone else —
 *   callers hide the sort rather than render one that silently does nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

const authState = { user: null as { is_superadmin?: boolean; is_subadmin?: boolean } | null }
vi.mock('@/stores/auth-store', () => ({
  useAuthStore: () => authState,
}))

import { api } from '@/lib/api'
import { useTaskStageOrder } from '../task-stages'

const STAGES = [
  { id: 'pending', name: 'Pending', position: 1, color: null, is_default: true },
  { id: 'review', name: 'Review', position: 3, color: null, is_default: false },
  { id: 'done', name: 'Done', position: 5, color: null, is_default: false },
]

beforeEach(() => {
  vi.mocked(api.get).mockReset()
  authState.user = { is_superadmin: true }
})

describe('useTaskStageOrder', () => {
  it('orders stages by their configured position', async () => {
    vi.mocked(api.get).mockResolvedValue(STAGES as never)
    const { result } = renderHook(() => useTaskStageOrder())
    await waitFor(() => expect(result.current.positionOf('done')).toBe(5))

    expect(result.current.positionOf('pending')).toBe(1)
    expect(result.current.positionOf('review')).toBe(3)
    // Ascending sort therefore runs Pending → Review → Done.
    expect(result.current.positionOf('pending')).toBeLessThan(result.current.positionOf('review'))
    expect(result.current.positionOf('review')).toBeLessThan(result.current.positionOf('done'))
  })

  it('sorts unassigned and unknown stages after every real stage', async () => {
    vi.mocked(api.get).mockResolvedValue(STAGES as never)
    const { result } = renderHook(() => useTaskStageOrder())
    await waitFor(() => expect(result.current.positionOf('done')).toBe(5))

    // Untriaged work goes last, not first.
    expect(result.current.positionOf(null)).toBeGreaterThan(result.current.positionOf('done'))
    expect(result.current.positionOf(undefined)).toBeGreaterThan(result.current.positionOf('done'))
    // A stage deleted out from under an asset must not sort it to the front.
    expect(result.current.positionOf('deleted-stage')).toBeGreaterThan(result.current.positionOf('done'))
  })

  it('reports unavailable and fetches nothing for non-admins', () => {
    authState.user = { is_superadmin: false, is_subadmin: false }
    const { result } = renderHook(() => useTaskStageOrder())

    expect(result.current.available).toBe(false)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('is available to sub-admins, not just superadmins', () => {
    authState.user = { is_superadmin: false, is_subadmin: true }
    const { result } = renderHook(() => useTaskStageOrder())

    expect(result.current.available).toBe(true)
  })
})
