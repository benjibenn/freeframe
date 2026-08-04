/**
 * Tour step metadata — where each step's target lives, and which steps a given
 * context can actually reach.
 *
 * Intent encoded:
 * - a step's page is what makes navigation possible; 'asset' cannot resolve
 *   without an assetId, so it must yield null rather than a broken URL;
 * - the two asset steps are dropped when the target project has no assets, so
 *   the tour never parks on a page that cannot exist;
 * - the library step deliberately has no page: it spotlights the sidebar link
 *   from wherever the user already is, and navigating would contradict its copy.
 */
import { describe, it, expect } from 'vitest'

import { TOUR_STEPS, stepHref, visibleSteps, type TourContext } from '../tour-steps'

const WITH_ASSET: TourContext = { projectId: 'p1', assetId: 'a1' }
const NO_ASSET: TourContext = { projectId: 'p1', assetId: null }

describe('stepHref', () => {
  it('resolves the project page', () => {
    expect(stepHref('project', WITH_ASSET)).toBe('/projects/p1')
  })

  it('resolves the asset page', () => {
    expect(stepHref('asset', WITH_ASSET)).toBe('/projects/p1/assets/a1')
  })

  it('resolves the library page', () => {
    expect(stepHref('library', NO_ASSET)).toBe('/library')
  })

  it('returns null for an asset page with no asset', () => {
    expect(stepHref('asset', NO_ASSET)).toBeNull()
  })
})

describe('visibleSteps', () => {
  it('keeps every step when an asset exists', () => {
    expect(visibleSteps(WITH_ASSET)).toHaveLength(TOUR_STEPS.length)
  })

  it('drops exactly the asset steps when there is no asset', () => {
    const ids = visibleSteps(NO_ASSET).map((s) => s.id)
    expect(ids).not.toContain('new-version')
    expect(ids).not.toContain('comments')
    expect(ids).toHaveLength(TOUR_STEPS.length - 2)
  })

  it('preserves step order when filtering', () => {
    const ids = visibleSteps(NO_ASSET).map((s) => s.id)
    expect(ids).toEqual(['upload', 'grid', 'library', 'keywords', 'video-labels', 'done'])
  })
})

describe('TOUR_STEPS page metadata', () => {
  it('assigns the page where each target actually lives', () => {
    const pages = Object.fromEntries(TOUR_STEPS.map((s) => [s.id, s.page]))
    expect(pages).toEqual({
      upload: 'project',
      grid: 'project',
      'new-version': 'asset',
      comments: 'asset',
      library: undefined,
      keywords: 'library',
      'video-labels': 'library',
      done: undefined,
    })
  })
})
