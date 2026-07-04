import { describe, it, expect, beforeEach } from 'vitest'
import { useSorterStore, getBindings } from '../sorter-store'

describe('sorter-store', () => {
  beforeEach(() => {
    useSorterStore.setState({ bindings: {}, seekStep: 3 })
  })

  it('sets and reads a per-project slot binding', () => {
    useSorterStore.getState().setBinding('proj-1', 2, 'B-Roll')
    expect(getBindings(useSorterStore.getState(), 'proj-1')[2]).toBe('b-roll') // normalized
  })

  it('keeps bindings isolated per project', () => {
    useSorterStore.getState().setBinding('proj-1', 1, 'hook')
    expect(getBindings(useSorterStore.getState(), 'proj-2')).toEqual({})
  })

  it('clears a binding', () => {
    const s = useSorterStore.getState()
    s.setBinding('proj-1', 1, 'hook')
    s.clearBinding('proj-1', 1)
    expect(getBindings(useSorterStore.getState(), 'proj-1')[1]).toBeUndefined()
  })

  it('updates seek step', () => {
    useSorterStore.getState().setSeekStep(5)
    expect(useSorterStore.getState().seekStep).toBe(5)
  })
})

it('getBindings returns a stable reference for projects with no bindings', () => {
  const state = useSorterStore.getState()
  // Same identity across calls — a fresh {} per call makes useSyncExternalStore
  // see a new snapshot every render and loop forever on binding-less projects.
  expect(getBindings(state, 'no-bindings-project')).toBe(
    getBindings(state, 'no-bindings-project'),
  )
})
