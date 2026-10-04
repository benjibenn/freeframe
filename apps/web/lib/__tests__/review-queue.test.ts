/**
 * The queue's rules, apart from React. Deciding a file removes it, and the next
 * one slides into the same slot: that is the auto-advance. Every listed file is
 * still in Review on the server, so the next page starts after them. A page that
 * brings nothing new stops the auto-fetch rather than looping.
 */
import { describe, it, expect } from 'vitest'
import {
  initialQueue, nextOffset, preloadTargets, queueReducer, shouldFetchMore, type QueueState,
} from '../review-queue'
import type { ReviewQueueItem, ReviewQueuePage } from '@/types'

const STAGES = { review: 'r', done: 'd', revision: 'v' }
const item = (n: number) => ({ asset_id: `a${n}`, preview_url: `p${n}` }) as unknown as ReviewQueueItem
const page = (ns: number[], total: number): ReviewQueuePage => ({ items: ns.map(item), total, stages: STAGES })
const ids = (s: QueueState) => s.items.map((i) => i.asset_id)

function loaded(ns: number[], total = ns.length, from: QueueState = initialQueue) {
  return queueReducer(from, { type: 'loaded', page: page(ns, total) })
}

describe('queueReducer', () => {
  it('appends a page without duplicating files already listed', () => {
    const s = loaded([2, 3], 4, loaded([1, 2], 4))
    expect(ids(s)).toEqual(['a1', 'a2', 'a3'])
    expect(s.total).toBe(4)
    expect(s.stages).toEqual(STAGES)
  })

  it('keeps the same slot after a decision, so the next file slides in', () => {
    const s = queueReducer(loaded([1, 2, 3]), { type: 'removed', assetId: 'a1' })
    expect(s.items[s.index].asset_id).toBe('a2')
    expect(s.total).toBe(2)
  })

  it('stays on the last file when the last one is decided', () => {
    let s = queueReducer(loaded([1, 2]), { type: 'next' })
    s = queueReducer(s, { type: 'removed', assetId: 'a2' })
    expect(s.index).toBe(0)
    expect(s.items[s.index].asset_id).toBe('a1')
  })

  it('empties cleanly when the only file is decided', () => {
    const s = queueReducer(loaded([1]), { type: 'removed', assetId: 'a1' })
    expect(s.items).toEqual([])
    expect(s.index).toBe(0)
  })

  it('keeps the current file when one before it disappears', () => {
    let s = queueReducer(queueReducer(loaded([1, 2, 3]), { type: 'next' }), { type: 'next' })
    s = queueReducer(s, { type: 'removed', assetId: 'a1' })
    expect(s.items[s.index].asset_id).toBe('a3')
  })

  it('clamps next and prev at the ends', () => {
    let s = queueReducer(loaded([1, 2]), { type: 'prev' })
    expect(s.index).toBe(0)
    s = queueReducer(queueReducer(queueReducer(s, { type: 'next' }), { type: 'next' }), { type: 'next' })
    expect(s.index).toBe(1)
  })

  it('stops auto-fetching when a page brings nothing new, until something is decided', () => {
    let s = loaded([1, 2], 10, loaded([1, 2], 10))
    expect(s.stalled).toBe(true)
    expect(shouldFetchMore(s)).toBe(false)
    s = queueReducer(s, { type: 'removed', assetId: 'a1' })
    expect(s.stalled).toBe(false)
  })
})

describe('queue paging', () => {
  it('asks the server for the files after the ones still listed', () => {
    expect(nextOffset(loaded([1, 2, 3], 10))).toBe(3)
  })

  it('wants more when five or fewer remain after the current file', () => {
    expect(shouldFetchMore(loaded([1, 2, 3, 4, 5, 6, 7], 20))).toBe(false)
    expect(shouldFetchMore(loaded([1, 2, 3, 4, 5, 6], 20))).toBe(true)
    expect(shouldFetchMore(loaded([1, 2, 3], 3))).toBe(false)
  })

  it('preloads the two files after the current one', () => {
    expect(preloadTargets(loaded([1, 2, 3, 4])).map((i) => i.asset_id)).toEqual(['a2', 'a3'])
  })
})
