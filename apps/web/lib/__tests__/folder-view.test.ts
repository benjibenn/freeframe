/**
 * A flattened grid holds files from the submitters' own projects. Everything
 * that must change in that state — the endpoint, the containers, the writes the
 * page withholds — reads one gate, so these tests pin the gate rather than the
 * toggle: a name query flattens the grid just as the toggle does, and the gate
 * has to say so or the withheld writes come back.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  projectUrl,
  isFlattened,
  assetsBasePath,
  searchScopeHint,
  initialFileView,
  readRememberedView,
  rememberView,
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
    stageIds: [] as string[],
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

  it('is on for a status chip alone, with the toggle off', () => {
    // Same reason as a query: at a store folder the files sit in the briefs
    // below, so filtering one folder level would show an empty grid.
    expect(isFlattened({ ...base, stageIds: ['s1'] })).toBe(true)
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
  const base = {
    currentFolderId: 'f1',
    assetsQuery: 'folder_id=f1',
    query: '',
    stageIds: [] as string[],
  }

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
      // URLSearchParams writes a space as "+", which is what a query string
      // means by it and what the API reads back.
    ).toBe('/projects/p1/folder-files?folder_id=f1&q=iphone+17')
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

  it('repeats stage_id per chip, so the API can OR them', () => {
    // Comma-joining would make the API read one bogus UUID and 422.
    expect(
      assetsBasePath('p1', { ...base, flattened: true, stageIds: ['s1', 's2'] }),
    ).toBe('/projects/p1/folder-files?folder_id=f1&stage_id=s1&stage_id=s2')
  })

  it('carries a query and the chips together', () => {
    expect(
      assetsBasePath('p1', {
        ...base,
        flattened: true,
        query: 'hero',
        stageIds: ['none'],
      }),
    ).toBe('/projects/p1/folder-files?folder_id=f1&q=hero&stage_id=none')
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

describe('initialFileView', () => {
  it('lets the URL win, so a pasted link lands where it says', () => {
    expect(initialFileView('files', false)).toBe(true)
    expect(initialFileView('', true)).toBe(false)
  })

  it('falls back to the remembered default when the URL says nothing', () => {
    // A project that is all briefs should open flat without a click.
    expect(initialFileView(null, true)).toBe(true)
  })

  it('opens in folder view when nothing says otherwise', () => {
    expect(initialFileView(null, false)).toBe(false)
  })
})

describe('readRememberedView / rememberView', () => {
  beforeEach(() => localStorage.clear())

  it('round-trips the choice per project', () => {
    rememberView('p1', true)
    rememberView('p2', false)
    expect(readRememberedView('p1')).toBe(true)
    expect(readRememberedView('p2')).toBe(false)
  })

  it('reports false for a project never seen', () => {
    expect(readRememberedView('p9')).toBe(false)
  })

  it('survives storage that throws, which private mode does', () => {
    // A forgotten preference must not take the toggle down with it.
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })
    expect(readRememberedView('p1')).toBe(false)
    expect(() => rememberView('p1', true)).not.toThrow()
    get.mockRestore()
    set.mockRestore()
  })
})
