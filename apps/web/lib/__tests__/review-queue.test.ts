/**
 * The queue's rules, apart from React. An item is one editor on one brief.
 * Deciding it removes it, and the next one slides into the same slot: that is
 * the auto-advance. Every listed item is still in Review on the server, so the
 * next page starts after them. A page that brings nothing new stops the
 * auto-fetch rather than looping. Within an item the reviewer flips between
 * the editor's files; moving to another item starts again at its first file,
 * so a revision comment never lands on a file from the previous editor.
 */
import { describe, it, expect } from 'vitest'
import {
  currentFile, initialQueue, nextOffset, preloadTargets, queueReducer, shouldFetchMore, type QueueState,
} from '../review-queue'
import type { ReviewFile, ReviewQueueItem, ReviewQueuePage } from '@/types'

const STAGES = { review: 'r', done: 'd', revision: 'v' }
const file = (id: string) => ({ asset_id: id, version_id: `v-${id}` }) as unknown as ReviewFile
const item = (n: number, files = 1) =>
  ({
    submission_id: `s${n}`,
    files: Array.from({ length: files }, (_, i) => file(`s${n}f${i}`)),
  }) as unknown as ReviewQueueItem
const page = (ns: number[], total: number, files = 1): ReviewQueuePage => ({
  items: ns.map((n) => item(n, files)), total, stages: STAGES,
})
const ids = (s: QueueState) => s.items.map((i) => i.submission_id)

function loaded(ns: number[], total = ns.length, from: QueueState = initialQueue, files = 1) {
  return queueReducer(from, { type: 'loaded', page: page(ns, total, files) })
}

describe('queueReducer', () => {
  it('appends a page without duplicating submissions already listed', () => {
    const s = loaded([2, 3], 4, loaded([1, 2], 4))
    expect(ids(s)).toEqual(['s1', 's2', 's3'])
    expect(s.total).toBe(4)
    expect(s.stages).toEqual(STAGES)
  })

  it('keeps the same slot after a decision, so the next editor slides in', () => {
    const s = queueReducer(loaded([1, 2, 3]), { type: 'removed', submissionId: 's1' })
    expect(s.items[s.index].submission_id).toBe('s2')
    expect(s.total).toBe(2)
  })

  it('stays on the last item when the last one is decided', () => {
    let s = queueReducer(loaded([1, 2]), { type: 'next' })
    s = queueReducer(s, { type: 'removed', submissionId: 's2' })
    expect(s.index).toBe(0)
    expect(s.items[s.index].submission_id).toBe('s1')
  })

  it('empties cleanly when the only item is decided', () => {
    const s = queueReducer(loaded([1]), { type: 'removed', submissionId: 's1' })
    expect(s.items).toEqual([])
    expect(s.index).toBe(0)
    expect(currentFile(s)).toBeNull()
  })

  it('keeps the current item when one before it disappears', () => {
    let s = queueReducer(queueReducer(loaded([1, 2, 3]), { type: 'next' }), { type: 'next' })
    s = queueReducer(s, { type: 'removed', submissionId: 's1' })
    expect(s.items[s.index].submission_id).toBe('s3')
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
    s = queueReducer(s, { type: 'removed', submissionId: 's1' })
    expect(s.stalled).toBe(false)
  })
})

describe('files within an item', () => {
  it('starts on the first file and flips through the rest, clamped at the ends', () => {
    let s = loaded([1], 1, initialQueue, 3)
    expect(currentFile(s)?.asset_id).toBe('s1f0')
    s = queueReducer(s, { type: 'prevFile' })
    expect(currentFile(s)?.asset_id).toBe('s1f0')
    s = queueReducer(queueReducer(queueReducer(s, { type: 'nextFile' }), { type: 'nextFile' }), { type: 'nextFile' })
    expect(currentFile(s)?.asset_id).toBe('s1f2')
    s = queueReducer(s, { type: 'selectFile', index: 1 })
    expect(currentFile(s)?.asset_id).toBe('s1f1')
  })

  it('goes back to the first file on moving to another item, so a comment cannot hit the wrong editor', () => {
    let s = queueReducer(loaded([1, 2], 2, initialQueue, 3), { type: 'nextFile' })
    s = queueReducer(s, { type: 'next' })
    expect(currentFile(s)?.asset_id).toBe('s2f0')
    s = queueReducer(queueReducer(s, { type: 'nextFile' }), { type: 'removed', submissionId: 's2' })
    expect(currentFile(s)?.asset_id).toBe('s1f0')
  })

  it('has no current file for an editor who uploaded nothing', () => {
    expect(currentFile(loaded([1], 1, initialQueue, 0))).toBeNull()
  })
})

describe('queue paging', () => {
  it('asks the server for the items after the ones still listed', () => {
    expect(nextOffset(loaded([1, 2, 3], 10))).toBe(3)
  })

  it('wants more when five or fewer remain after the current item', () => {
    expect(shouldFetchMore(loaded([1, 2, 3, 4, 5, 6, 7], 20))).toBe(false)
    expect(shouldFetchMore(loaded([1, 2, 3, 4, 5, 6], 20))).toBe(true)
    expect(shouldFetchMore(loaded([1, 2, 3], 3))).toBe(false)
  })

  it('preloads the two items after the current one', () => {
    expect(preloadTargets(loaded([1, 2, 3, 4])).map((i) => i.submission_id)).toEqual(['s2', 's3'])
  })
})
