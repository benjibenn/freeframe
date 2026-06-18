import { describe, it, expect } from 'vitest'
import { mergeSuggestions } from '../suggestions'

const tags = [
  { tag: 'b-roll', count: 10 },
  { tag: 'hook', count: 5 },
  { tag: 'testimonial', count: 2 },
  { tag: 'body', count: 1 },
]

describe('mergeSuggestions', () => {
  it('empty query: recent first, then by frequency', () => {
    expect(mergeSuggestions(tags, ['body'], '', [])).toEqual(
      ['body', 'b-roll', 'hook', 'testimonial'],
    )
  })

  it('excludes already-applied tags', () => {
    expect(mergeSuggestions(tags, [], '', ['b-roll'])).not.toContain('b-roll')
  })

  it('filters by query substring, case-insensitive', () => {
    // Uppercase 'B' matches 'b-roll' and 'body'; 'hook'/'testimonial' have no 'b'.
    expect(mergeSuggestions(tags, [], 'B', [])).toEqual(['b-roll', 'body'])
  })

  it('recent matches rank above frequent matches when both match query', () => {
    // Both 'b-roll' (freq 10) and 'body' (freq 1) match 'b'; recent floats 'body' first.
    expect(mergeSuggestions(tags, ['body'], 'b', [])).toEqual(['body', 'b-roll'])
  })

  it('caps at 8', () => {
    const many = Array.from({ length: 20 }, (_, i) => ({ tag: `t${i}`, count: i }))
    expect(mergeSuggestions(many, [], '', []).length).toBe(8)
  })
})
