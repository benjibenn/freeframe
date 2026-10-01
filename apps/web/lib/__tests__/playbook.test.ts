/**
 * Why these rules matter: the copied text is pasted straight to editors, so
 * links must land under the right heading, and coverage must not count a brief
 * nobody delivered files for.
 */
import { describe, it, expect } from 'vitest'
import {
  buildTitle, copyText, group, matrix, NO_MODEL, parseTitle, scopes, subfolders, titleProblem,
  todayStamp, toBriefs, type PlaybookSource, type TitleParts,
} from '../playbook'

const row = (id: string, path: string, title: string, over: Partial<PlaybookSource> = {}): PlaybookSource => ({
  id, token: `tok-${id}`, title, home_path: path, persona_label: null, angle_label: null,
  submission_count: 1, asset_count: 1, ...over,
})

const T = (model: string, hook: string) => `20260910 - ${model} - Frugal Phone Buyer - Fear - ${hook} - Two panel split static`

const ROWS = [
  row('a', 'ecom/Phones/Globex/iPhone 17', T('i17', 'Tired of your battery')),
  row('b', 'ecom/Phones/Globex/iPhone 9', T('i9', 'tired of your battery'), { asset_count: 0, angle_label: 'A1' }),
  row('c', 'ecom/Phones/Globex/iPhone 17', T('i17', 'Cheaper - by far')),
  row('d', 'ecom/Phones/Globex', 'Loose brief at the brand root'),
  row('x', 'ecom/Phones/Acme/iPhone 17', T('i17', 'Other brand')),
]
const briefs = () => toBriefs(ROWS, 'ecom/Phones/Globex', 'https://ff.test')

describe('playbook', () => {
  it('keeps a hook that itself contains " - "', () => {
    expect(parseTitle(T('i17', 'Cheaper - by far')).hook).toBe('Cheaper - by far')
  })

  it('scopes to one brand folder and reads the model off the first subfolder', () => {
    const b = briefs()
    expect(b.map((x) => x.id).sort()).toEqual(['a', 'b', 'c', 'd'])
    expect(b.find((x) => x.id === 'd')!.model).toBe(NO_MODEL)
    expect(b.find((x) => x.id === 'a')!.url).toBe('https://ff.test/submit/tok-a')
    expect(scopes(ROWS).find((s) => s.path === 'ecom/Phones/Globex')!.count).toBe(4)
  })

  it('lists only the folders one level down, so each brand is one click', () => {
    expect(subfolders(ROWS, '').map((f) => f.name)).toEqual(['ecom'])
    expect(subfolders(ROWS, 'ecom/Phones')).toEqual([
      { path: 'ecom/Phones/Acme', name: 'Acme', count: 1 },
      { path: 'ecom/Phones/Globex', name: 'Globex', count: 4 },
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

/**
 * buildTitle is parseTitle's inverse, and the two must not drift: the create form
 * writes titles with one and the playbook reads them with the other. A round trip
 * is the only assertion that fails when either side changes alone.
 */
describe('buildTitle', () => {
  const parts: TitleParts = {
    date: '20260910', sku: 'iPhone 17 Pro Max', persona: 'Frugal Phone Buyer',
    lens: 'Fear', hook: 'Battery dies by 3pm', format: 'Static',
  }

  it('writes a title parseTitle reads back unchanged', () => {
    const title = buildTitle(parts)
    expect(title).toBe('20260910 - iPhone 17 Pro Max - Frugal Phone Buyer - Fear - Battery dies by 3pm - Static')
    expect(parseTitle(title)).toEqual({
      persona: 'Frugal Phone Buyer', lens: 'Fear', hook: 'Battery dies by 3pm', format: 'Static',
    })
  })

  it('round-trips a hook that contains the separator', () => {
    const title = buildTitle({ ...parts, hook: 'Cracked screen - again' })
    expect(parseTitle(title).hook).toBe('Cracked screen - again')
    expect(parseTitle(title).lens).toBe('Fear')
  })

  it('stamps today when no date is given', () => {
    expect(buildTitle({ ...parts, date: '' }).startsWith(`${todayStamp()} - `)).toBe(true)
    expect(todayStamp()).toMatch(/^\d{8}$/)
  })

  it('names the part that is missing, so the form can say which box to fill', () => {
    expect(titleProblem({ ...parts, lens: '  ' })).toMatch(/lens/i)
    expect(titleProblem({ ...parts, hook: '' })).toMatch(/hook/i)
    expect(titleProblem(parts)).toBeNull()
  })

  it('refuses the separator in any part but the hook', () => {
    // Anywhere else it shifts every later slot: the lens would be read as the hook.
    expect(titleProblem({ ...parts, persona: 'Frugal - Buyer' })).toMatch(/persona/i)
    expect(titleProblem({ ...parts, sku: 'iPhone - 17' })).toMatch(/sku/i)
    expect(titleProblem({ ...parts, hook: 'Cracked - again' })).toBeNull()
  })
})
