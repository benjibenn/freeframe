/**
 * Which project the tour walks the user through.
 *
 * Intent encoded:
 * - only `editor` membership qualifies: the tour teaches uploading and
 *   revising, which reviewers and viewers cannot do;
 * - a project that already has assets beats a newer empty one, because the two
 *   asset steps are only reachable when an asset exists — the heuristic
 *   optimises for the tour being complete, not for recency;
 * - no editor project means no tour at all, which is how "editors only" is
 *   enforced for both the auto-start and the ? button.
 */
import { describe, it, expect } from 'vitest'

import { resolveTargetProject } from '../tour-context'
import type { Project } from '@/types'

const project = (over: Partial<Project>): Project =>
  ({
    id: 'p',
    name: 'p',
    description: null,
    created_by: 'u',
    project_type: 'personal',
    created_at: '2026-01-01T00:00:00Z',
    deleted_at: null,
    asset_count: 0,
    role: 'editor',
    ...over,
  }) as Project

describe('resolveTargetProject', () => {
  it('returns null when the user is editor on nothing', () => {
    expect(
      resolveTargetProject([
        project({ id: 'a', role: 'owner' }),
        project({ id: 'b', role: 'viewer' }),
        project({ id: 'c', role: 'reviewer' }),
      ]),
    ).toBeNull()
  })

  it('returns null for an empty project list', () => {
    expect(resolveTargetProject([])).toBeNull()
  })

  it('ignores projects where the user is not an editor', () => {
    const found = resolveTargetProject([
      project({ id: 'owned', role: 'owner', asset_count: 99 }),
      project({ id: 'mine', role: 'editor', asset_count: 1 }),
    ])
    expect(found?.id).toBe('mine')
  })

  it('prefers a project with assets over a newer empty one', () => {
    const found = resolveTargetProject([
      project({ id: 'empty-new', asset_count: 0, created_at: '2026-08-01T00:00:00Z' }),
      project({ id: 'full-old', asset_count: 3, created_at: '2026-01-01T00:00:00Z' }),
    ])
    expect(found?.id).toBe('full-old')
  })

  it('picks the newest among projects that all have assets', () => {
    const found = resolveTargetProject([
      project({ id: 'old', asset_count: 1, created_at: '2026-01-01T00:00:00Z' }),
      project({ id: 'new', asset_count: 1, created_at: '2026-08-01T00:00:00Z' }),
    ])
    expect(found?.id).toBe('new')
  })

  it('falls back to the newest empty project when none has assets', () => {
    const found = resolveTargetProject([
      project({ id: 'old', asset_count: 0, created_at: '2026-01-01T00:00:00Z' }),
      project({ id: 'new', asset_count: 0, created_at: '2026-08-01T00:00:00Z' }),
    ])
    expect(found?.id).toBe('new')
  })

  it('treats a missing asset_count as empty', () => {
    const found = resolveTargetProject([
      project({ id: 'unknown', asset_count: undefined, created_at: '2026-08-01T00:00:00Z' }),
      project({ id: 'known', asset_count: 2, created_at: '2026-01-01T00:00:00Z' }),
    ])
    expect(found?.id).toBe('known')
  })
})
