/**
 * The search box must feel instant while costing one request per word, not one
 * per keystroke — so the raw value and the settled value have to diverge.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useDebounced } from '../use-debounced'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useDebounced', () => {
  it('returns the first value immediately, so the grid is not empty on mount', () => {
    const { result } = renderHook(() => useDebounced('iphone'))
    expect(result.current).toBe('iphone')
  })

  it('holds the old value until the delay passes', () => {
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 250), {
      initialProps: { v: '' },
    })
    rerender({ v: 'i' })
    expect(result.current).toBe('')
    act(() => vi.advanceTimersByTime(249))
    expect(result.current).toBe('')
  })

  it('settles on the last value typed, not on every one in between', () => {
    // Four keystrokes inside the window must cost one request, not four.
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 250), {
      initialProps: { v: '' },
    })
    for (const v of ['i', 'ip', 'iph', 'ipho']) {
      rerender({ v })
      act(() => vi.advanceTimersByTime(100))
    }
    expect(result.current).toBe('')
    act(() => vi.advanceTimersByTime(250))
    expect(result.current).toBe('ipho')
  })
})
