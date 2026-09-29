/**
 * Why these rules matter: the copied text is pasted straight to editors, so
 * links must land under the right heading, and coverage must not count a brief
 * nobody delivered files for.
 */
import { describe, it, expect } from 'vitest'
import { copyText, group, matrix, NO_MODEL, parseTitle, scopes, subfolders, toBriefs, type PlaybookSource } from '../playbook'

const row = (id: string, path: string, title: string, over: Partial<PlaybookSource> = {}): PlaybookSource => ({
  id, token: `tok-${id}`, title, home_path: path, persona_label: null, angle_label: null,
  submission_count: 1, asset_count: 1, ...over,
})

const T = (model: string, hook: string) => `20260910 - ${model} - Frugal Phone Buyer - Fear - ${hook} - Two panel split static`

const ROWS = [
  row('a', 'ecom/Phones/Stokora/iPhone 17', T('i17', 'Tired of your battery')),
  row('b', 'ecom/Phones/Stokora/iPhone 9', T('i9', 'tired of your battery'), { asset_count: 0, angle_label: 'A1' }),
  row('c', 'ecom/Phones/Stokora/iPhone 17', T('i17', 'Cheaper - by far')),
  row('d', 'ecom/Phones/Stokora', 'Loose brief at the brand root'),
  row('x', 'ecom/Phones/Joolabs/iPhone 17', T('i17', 'Other brand')),
]
const briefs = () => toBriefs(ROWS, 'ecom/Phones/Stokora', 'https://ff.test')

describe('playbook', () => {
  it('keeps a hook that itself contains " - "', () => {
    expect(parseTitle(T('i17', 'Cheaper - by far')).hook).toBe('Cheaper - by far')
  })

  it('scopes to one brand folder and reads the model off the first subfolder', () => {
    const b = briefs()
    expect(b.map((x) => x.id).sort()).toEqual(['a', 'b', 'c', 'd'])
    expect(b.find((x) => x.id === 'd')!.model).toBe(NO_MODEL)
    expect(b.find((x) => x.id === 'a')!.url).toBe('https://ff.test/submit/tok-a')
    expect(scopes(ROWS).find((s) => s.path === 'ecom/Phones/Stokora')!.count).toBe(4)
  })

  it('lists only the folders one level down, so each brand is one click', () => {
    expect(subfolders(ROWS, '').map((f) => f.name)).toEqual(['ecom'])
    expect(subfolders(ROWS, 'ecom/Phones')).toEqual([
      { path: 'ecom/Phones/Joolabs', name: 'Joolabs', count: 1 },
      { path: 'ecom/Phones/Stokora', name: 'Stokora', count: 4 },
    ])
  })

  it('groups by model in natural order, unfiled last', () => {
    expect(group(briefs(), 'model').map(([h]) => h)).toEqual(['iPhone 9', 'iPhone 17', NO_MODEL])
  })

  it('groups by brief case-insensitively, so one brief cloned per model is one group', () => {
    const g = group(briefs(), 'brief')
    const battery = g.find(([h]) => h.toLowerCase() === 'tired of your battery')!
    expect(battery[1].map((b) => b.model)).toEqual(['iPhone 9', 'iPhone 17'])
  })

  it('copies links under the heading, labelled by what the heading leaves out', () => {
    const picked = briefs().filter((b) => b.id === 'a' || b.id === 'b')
    expect(copyText(picked, 'model')).toBe(
      'iPhone 9\ntired of your battery: https://ff.test/submit/tok-b\n\niPhone 17\nTired of your battery: https://ff.test/submit/tok-a',
    )
    expect(copyText(picked, 'brief')).toBe(
      'Tired of your battery\niPhone 9: https://ff.test/submit/tok-b\niPhone 17: https://ff.test/submit/tok-a',
    )
  })

  it('counts coverage by delivered files, not submissions', () => {
    const m = matrix(briefs())
    expect(m.cell('Frugal Phone Buyer', 'A1')).toEqual({ total: 1, withFiles: 0 })
    expect(m.angles).toEqual(['A1', '—'])
  })
})
