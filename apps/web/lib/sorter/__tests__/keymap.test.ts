import { describe, it, expect } from 'vitest'
import { keyToAction } from '../keymap'

describe('keyToAction', () => {
  it('maps navigation and seek', () => {
    expect(keyToAction('ArrowUp', 3)).toEqual({ kind: 'prev' })
    expect(keyToAction('ArrowDown', 3)).toEqual({ kind: 'next' })
    expect(keyToAction('ArrowLeft', 3)).toEqual({ kind: 'seek', delta: -3 })
    expect(keyToAction('ArrowRight', 4)).toEqual({ kind: 'seek', delta: 4 })
    expect(keyToAction(' ', 3)).toEqual({ kind: 'togglePlay' })
  })

  it('maps number keys 1-9 to slots', () => {
    expect(keyToAction('1', 3)).toEqual({ kind: 'slot', slot: 1 })
    expect(keyToAction('9', 3)).toEqual({ kind: 'slot', slot: 9 })
    expect(keyToAction('0', 3)).toBeNull()
  })

  it('maps letter shortcuts', () => {
    expect(keyToAction('a', 3)).toEqual({ kind: 'applyAll' })
    expect(keyToAction('t', 3)).toEqual({ kind: 'focusTag' })
    expect(keyToAction('f', 3)).toEqual({ kind: 'filter' })
    expect(keyToAction('d', 3)).toEqual({ kind: 'archive' })
    expect(keyToAction('z', 3)).toEqual({ kind: 'undo' })
    expect(keyToAction('Escape', 3)).toEqual({ kind: 'exit' })
  })

  it("maps 'g' to autoTag", () => {
    expect(keyToAction('g', 5)).toEqual({ kind: 'autoTag' })
  })

  it('returns null for unmapped keys', () => {
    expect(keyToAction('q', 3)).toBeNull()
  })
})
