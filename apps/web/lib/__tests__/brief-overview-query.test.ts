/**
 * The overview's filters are applied by the server now (the list is paged).
 * The date inputs are local calendar days, and the server compares instants, so
 * the bounds must be the viewer's local midnights. Otherwise a brief created
 * that evening drops off a one-day range.
 */
import { describe, it, expect, vi } from 'vitest'
import { NO_FILTERS, fetchAllBriefOverview, overviewQuery } from '../brief-overview-query'

describe('overviewQuery', () => {
  it('sends nothing when no filter is set', () => {
    expect(overviewQuery(NO_FILTERS)).toBe('')
  })

  it('trims the search and passes the editor and has-files filters', () => {
    const qs = new URLSearchParams(overviewQuery({ ...NO_FILTERS, query: '  pick ', userId: 'u1', withFiles: true }))
    expect(qs.get('q')).toBe('pick')
    expect(qs.get('editor_id')).toBe('u1')
    expect(qs.get('has_files')).toBe('true')
  })

  it('bounds a date range by local midnights, end exclusive', () => {
    const qs = new URLSearchParams(overviewQuery({ ...NO_FILTERS, from: '2026-09-10', to: '2026-09-10' }))
    expect(qs.get('created_from')).toBe(new Date('2026-09-10T00:00:00').toISOString())
    expect(qs.get('created_to')).toBe(new Date('2026-09-11T00:00:00').toISOString())
  })
})

describe('fetchAllBriefOverview', () => {
  it('walks the pages until it has every brief', async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ items: Array.from({ length: 100 }, (_, i) => i), total: 130 })
      .mockResolvedValueOnce({ items: Array.from({ length: 30 }, (_, i) => 100 + i), total: 130 })
    const rows = await fetchAllBriefOverview<number>(get)
    expect(rows).toHaveLength(130)
    expect(get.mock.calls.map(([u]) => u)).toEqual([
      '/brief-overview?limit=100&offset=0',
      '/brief-overview?limit=100&offset=100',
    ])
  })

  it('stops on an empty page even if total says there is more', async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ items: [1], total: 5 })
      .mockResolvedValueOnce({ items: [], total: 5 })
    expect(await fetchAllBriefOverview<number>(get)).toEqual([1])
  })
})
