/**
 * File view has to survive the things that happen around it: clicking into a
 * subfolder, a refresh, and a tag filter being switched on while it is active.
 */
import { describe, it, expect } from 'vitest'
import { projectUrl, isFileViewActive, assetsBasePath } from '../folder-view'

describe('projectUrl', () => {
  it('keeps the view when navigating into a folder', () => {
    // Without this, opening a model's folder from a flattened store silently
    // drops back to the brief listing.
    expect(projectUrl('p1', 'f1', true)).toBe('/projects/p1?folder=f1&view=files')
  })

  it('drops the view param when file view is off', () => {
    expect(projectUrl('p1', 'f1', false)).toBe('/projects/p1?folder=f1')
  })

  it('has no query at all at the project root in folder view', () => {
    expect(projectUrl('p1', null, false)).toBe('/projects/p1')
  })

  it('carries the view at the project root', () => {
    expect(projectUrl('p1', null, true)).toBe('/projects/p1?view=files')
  })
})

describe('isFileViewActive', () => {
  const off = { filteringByTagOrLabel: false, openBriefId: null }

  it('is on when nothing else owns the grid', () => {
    expect(isFileViewActive(true, off)).toBe(true)
  })

  it('yields to a tag filter, which is a project-wide search', () => {
    expect(
      isFileViewActive(true, { ...off, filteringByTagOrLabel: true }),
    ).toBe(false)
  })

  it("yields to an open brief, which shows that brief's own files", () => {
    expect(isFileViewActive(true, { ...off, openBriefId: 'b1' })).toBe(false)
  })

  it('is off when the toggle is off', () => {
    expect(isFileViewActive(false, off)).toBe(false)
  })
})

describe('assetsBasePath', () => {
  it('flattens a folder server-side, subtree and briefs included', () => {
    expect(
      assetsBasePath('p1', {
        fileViewActive: true,
        currentFolderId: 'f1',
        assetsQuery: 'folder_id=f1',
      }),
    ).toBe('/projects/p1/folder-files?folder_id=f1')
  })

  it('flattens the whole project at root', () => {
    expect(
      assetsBasePath('p1', {
        fileViewActive: true,
        currentFolderId: null,
        assetsQuery: 'folder_id=root',
      }),
    ).toBe('/projects/p1/folder-files?folder_id=root')
  })

  it('keeps the folder-scoped listing, filters and all, in folder view', () => {
    expect(
      assetsBasePath('p1', {
        fileViewActive: false,
        currentFolderId: 'f1',
        assetsQuery: 'tag=hero&tag=q4',
      }),
    ).toBe('/projects/p1/assets?tag=hero&tag=q4')
  })
})
