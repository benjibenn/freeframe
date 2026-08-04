/**
 * Tour look-ahead — which step the overlay is allowed to skip forward to when
 * the current step's target isn't on screen.
 *
 * Intent encoded:
 * - a target that lives in persistent layout chrome (the sidebar) is present on
 *   every dashboard page, so finding it proves nothing about where the user is;
 *   look-ahead must ignore those steps or it strands the tour on them;
 * - a page-scoped target being present DOES mean the user navigated there, so
 *   look-ahead must still follow them — that's the feature, not a bug;
 * - look-ahead never moves backwards, so a user who clicks Back into a step
 *   whose target is off-page stays put and reads its `waitingFor` copy.
 *
 * Regression: the tour auto-started on step 'library' instead of 'upload'.
 * `sidebar-library` is rendered by the dashboard layout outside `{children}`,
 * so it matched immediately while step 0's `upload-button` was still gated
 * behind `canUpload` and the project's first fetch. Back then bounced forward
 * again on the next poll, making the tour impossible to rewind.
 */
import { describe, it, expect } from 'vitest'

import { TOUR_STEPS, lookAheadIndex } from '../tour-steps'

const indexOfStep = (id: string) => TOUR_STEPS.findIndex((s) => s.id === id)

/** Builds an `isPresent` predicate from the set of targets currently in the DOM. */
const present = (...targets: string[]) => (target: string) => targets.includes(target)

describe('lookAheadIndex', () => {
  it('does not jump to a sidebar step just because the sidebar is mounted', () => {
    // The exact production case: tour starts at step 0 on a project page before
    // the upload button has rendered. The only matching target anywhere is the
    // always-mounted sidebar link.
    expect(lookAheadIndex(0, present('sidebar-library'))).toBe(-1)
  })

  it('stays put when Back lands on an off-page step and only the sidebar matches', () => {
    // Back from 'library' to 'comments'. `comments-tab` never exists on a project
    // page, so without this the next poll re-jumped to 'library' within 250ms.
    const comments = indexOfStep('comments')
    expect(lookAheadIndex(comments, present('sidebar-library'))).toBe(-1)
  })

  it('still follows the user to a page-scoped target that has appeared', () => {
    // User navigated to an asset page while the tour sat on step 0.
    expect(lookAheadIndex(0, present('comments-tab'))).toBe(indexOfStep('comments'))
  })

  it('never looks backwards', () => {
    const library = indexOfStep('library')
    expect(lookAheadIndex(library, present('upload-button'))).toBe(-1)
  })

  it('picks the nearest matching page-scoped step when several are present', () => {
    expect(lookAheadIndex(0, present('comments-tab', 'library-keywords'))).toBe(
      indexOfStep('comments'),
    )
  })

  it('marks exactly the sidebar step as always-mounted', () => {
    // Guards the data: if a future step targets layout chrome it must opt in too,
    // and no page-scoped step should be excluded from look-ahead by accident.
    const flagged = TOUR_STEPS.filter((s) => s.alwaysMounted).map((s) => s.id)
    expect(flagged).toEqual(['library'])
  })
})
