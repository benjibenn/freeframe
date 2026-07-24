import { describe, it, expect } from 'vitest'
import { rangeBetween, type SelectableItem } from '../selection'

const items: SelectableItem[] = [
  { kind: 'folder', id: 'f1' },
  { kind: 'folder', id: 'f2' },
  { kind: 'asset', id: 'a1' },
  { kind: 'asset', id: 'a2' },
  { kind: 'asset', id: 'a3' },
]

describe('rangeBetween', () => {
  it('returns inclusive slice when anchor precedes target', () => {
    const r = rangeBetween(items, { kind: 'folder', id: 'f2' }, { kind: 'asset', id: 'a2' })
    expect(r.map((i) => i.id)).toEqual(['f2', 'a1', 'a2'])
  })

  it('is order-agnostic (target before anchor)', () => {
    const r = rangeBetween(items, { kind: 'asset', id: 'a3' }, { kind: 'folder', id: 'f1' })
    expect(r.map((i) => i.id)).toEqual(['f1', 'f2', 'a1', 'a2', 'a3'])
  })

  it('spans folders into assets across the boundary', () => {
    const r = rangeBetween(items, { kind: 'folder', id: 'f1' }, { kind: 'asset', id: 'a1' })
    expect(r.map((i) => i.id)).toEqual(['f1', 'f2', 'a1'])
  })

  it('single item when anchor equals target', () => {
    const r = rangeBetween(items, { kind: 'asset', id: 'a2' }, { kind: 'asset', id: 'a2' })
    expect(r.map((i) => i.id)).toEqual(['a2'])
  })

  it('falls back to [target] when anchor is not present', () => {
    const r = rangeBetween(items, { kind: 'asset', id: 'gone' }, { kind: 'asset', id: 'a2' })
    expect(r.map((i) => i.id)).toEqual(['a2'])
  })
})
