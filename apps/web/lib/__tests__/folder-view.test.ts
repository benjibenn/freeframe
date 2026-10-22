/**
 * A flattened grid holds files from the submitters' own projects. Everything
 * that must change in that state — the endpoint, the containers, the writes the
 * page withholds — reads one gate, so these tests pin the gate rather than the
 * toggle: a name query flattens the grid just as the toggle does, and the gate
 * has to say so or the withheld writes come back.
 */
import { describe, it, expect } from 'vitest'
import {
  projectUrl,
  isFlattened,
  assetsBasePath,
  searchScopeHint,
} from '../folder-view'

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

describe('isFlattened', () => {
  const base = {
    fileView: false,
    query: '',
    filteringByTagOrLabel: false,
    openBriefId: null,
  }

  it('is on when the toggle is on', () => {
    expect(isFlattened({ ...base, fileView: true })).toBe(true)
  })

  it('is on for a name query alone, with the toggle off', () => {
    // Searching one folder level finds nothing when the files sit in subfolders
    // and briefs, which is the normal shape here.
    expect(isFlattened({ ...base, query: 'iphone 17' })).toBe(true)
  })

  it('ignores a query that is only whitespace', () => {
    expect(isFlattened({ ...base, query: '   ' })).toBe(false)
  })

  it('yields to a tag filter, which is a project-wide search', () => {
    expect(
      isFlattened({ ...base, fileView: true, filteringByTagOrLabel: true }),
    ).toBe(false)
  })

  it("yields to an open brief, which shows that brief's own files", () => {
    expect(isFlattened({ ...base, query: 'hero', openBriefId: 'b1' })).toBe(false)
  })

  it('is off when nothing flattens it', () => {
    expect(isFlattened(base)).toBe(false)
  })
})

describe('assetsBasePath', () => {
  const base = { currentFolderId: 'f1', assetsQuery: 'folder_id=f1', query: '' }

  it('flattens a folder server-side, subtree and briefs included', () => {
    expect(assetsBasePath('p1', { ...base, flattened: true })).toBe(
      '/projects/p1/folder-files?folder_id=f1',
    )
  })

  it('flattens the whole project at root', () => {
    expect(
      assetsBasePath('p1', {
        ...base,
        flattened: true,
        currentFolderId: null,
        assetsQuery: 'folder_id=root',
      }),
    ).toBe('/projects/p1/folder-files?folder_id=root')
  })

  it('keeps the folder-scoped listing, filters and all, in folder view', () => {
    expect(
      assetsBasePath('p1', {
        ...base,
        flattened: false,
        assetsQuery: 'tag=hero&tag=q4',
      }),
    ).toBe('/projects/p1/assets?tag=hero&tag=q4')
  })

  it('sends the query to the server, so it covers more than the loaded pages', () => {
    // The grid pages at 50. Filtering in the browser would claim "no matches"
    // for a file that simply had not loaded yet.
    expect(
      assetsBasePath('p1', { ...base, flattened: true, query: 'iphone 17' }),
    ).toBe('/projects/p1/folder-files?folder_id=f1&q=iphone%2017')
  })

  it('narrows a tag search by the query too', () => {
    expect(
      assetsBasePath('p1', {
        ...base,
        flattened: false,
        assetsQuery: 'tag=hero',
        query: 'fear',
      }),
    ).toBe('/projects/p1/assets?tag=hero&q=fear')
  })

  it('leaves the path alone for a whitespace query', () => {
    expect(
      assetsBasePath('p1', { ...base, flattened: true, query: '  ' }),
    ).toBe('/projects/p1/folder-files?folder_id=f1')
  })
})

describe('searchScopeHint', () => {
  it('says the search reaches the whole subtree when flattened', () => {
    expect(
      searchScopeHint({ flattened: true, filteringByTagOrLabel: false }, 'Store 1'),
    ).toBe('Searching everything under Store 1')
  })

  it('says it is only this folder otherwise', () => {
    expect(
      searchScopeHint({ flattened: false, filteringByTagOrLabel: false }, 'Store 1'),
    ).toBe('Searching Store 1')
  })

  it('names the tag search, which ignores the folder', () => {
    expect(
      searchScopeHint({ flattened: false, filteringByTagOrLabel: true }, 'Store 1'),
    ).toBe('Searching the tagged files')
  })
})
