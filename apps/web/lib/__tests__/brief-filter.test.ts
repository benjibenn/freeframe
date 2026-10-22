/**
 * A folder of a hundred briefs is unreadable by scrolling. These filters are
 * the alternative, so each one has to narrow exactly what it claims — and the
 * file-count map leaves out briefs with no submissions, which is the detail a
 * naive implementation gets wrong.
 */
import { describe, it, expect } from 'vitest'
import {
  filterBriefs,
  briefFiltersAreOff,
  NO_BRIEF_FILTERS,
  type BriefFilterState,
} from '../brief-filter'

const BRIEFS = [
  { id: 'b1', assignee_id: 'u1', task_stage_id: 's1' },
  { id: 'b2', assignee_id: null, task_stage_id: 's2' },
  { id: 'b3', assignee_id: null, task_stage_id: null },
]
// GET /brief-file-counts omits briefs with no submissions, so b2 and b3 are
// absent rather than present with 0.
const COUNTS = { b1: 4 }

const state = (over: Partial<BriefFilterState> = {}): BriefFilterState => ({
  ...NO_BRIEF_FILTERS,
  ...over,
})

const ids = (rows: { id: string }[]) => rows.map((r) => r.id)

describe('filterBriefs', () => {
  it('returns everything when no filter is on', () => {
    expect(ids(filterBriefs(BRIEFS, COUNTS, state()))).toEqual(['b1', 'b2', 'b3'])
  })

  it('keeps only briefs an editor has submitted to', () => {
    expect(ids(filterBriefs(BRIEFS, COUNTS, state({ files: 'with' })))).toEqual(['b1'])
  })

  it('finds the briefs still waiting on an editor', () => {
    // A brief missing from the count map has nothing, so it belongs here. Reading
    // the gap as "unknown" would hide exactly the briefs this filter is for.
    expect(ids(filterBriefs(BRIEFS, COUNTS, state({ files: 'without' })))).toEqual([
      'b2',
      'b3',
    ])
  })

  it('finds the briefs on nobody‘s desk', () => {
    expect(ids(filterBriefs(BRIEFS, COUNTS, state({ unassignedOnly: true })))).toEqual([
      'b2',
      'b3',
    ])
  })

  it('treats two stage chips as either, since a brief sits at one stage', () => {
    expect(
      ids(filterBriefs(BRIEFS, COUNTS, state({ stageIds: ['s1', 's2'] }))),
    ).toEqual(['b1', 'b2'])
  })

  it('reaches untriaged briefs through the "none" chip', () => {
    expect(ids(filterBriefs(BRIEFS, COUNTS, state({ stageIds: ['none'] })))).toEqual([
      'b3',
    ])
  })

  it('ANDs the filters, so each one narrows the last', () => {
    expect(
      ids(
        filterBriefs(
          BRIEFS,
          COUNTS,
          state({ files: 'without', unassignedOnly: true, stageIds: ['s2'] }),
        ),
      ),
    ).toEqual(['b2'])
  })

  it('can narrow to nothing rather than quietly falling back to everything', () => {
    expect(
      ids(filterBriefs(BRIEFS, COUNTS, state({ files: 'with', stageIds: ['none'] }))),
    ).toEqual([])
  })
})

describe('briefFiltersAreOff', () => {
  it('is true for the default state', () => {
    expect(briefFiltersAreOff(NO_BRIEF_FILTERS)).toBe(true)
  })

  it('is false once anything is set', () => {
    expect(briefFiltersAreOff(state({ files: 'with' }))).toBe(false)
    expect(briefFiltersAreOff(state({ unassignedOnly: true }))).toBe(false)
    expect(briefFiltersAreOff(state({ stageIds: ['s1'] }))).toBe(false)
  })
})
