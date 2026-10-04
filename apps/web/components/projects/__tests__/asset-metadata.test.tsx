/**
 * The assignee picker needs the project's member list, but most visits to a file
 * never open it. The list is fetched on first use, or at once when the file
 * already has an assignee, whose name the picker has to show.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SWRConfig } from 'swr'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn(), put: vi.fn() } }))
import { api } from '@/lib/api'
import { AssetMetadataEditor } from '../asset-metadata'
import type { Asset } from '@/types'

const BASE = {
  id: 'a1', project_id: 'p1', name: 'hook.mp4', rating: null, due_date: null, assignee_id: null,
} as unknown as Asset

function renderEditor(asset: Asset) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <AssetMetadataEditor asset={asset} projectId="p1" canEdit />
    </SWRConfig>,
  )
}

const membersRequested = () =>
  vi.mocked(api.get).mock.calls.some(([u]) => u === '/projects/p1/members')

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockImplementation(((url: string) =>
    Promise.resolve(
      url === '/projects/p1/members'
        ? [{ id: 'm1', project_id: 'p1', user_id: 'u1', role: 'editor' }]
        : [],
    )) as never)
})

describe('AssetMetadataEditor — member list', () => {
  it('does not fetch members until the assignee picker is used', async () => {
    const user = userEvent.setup()
    renderEditor(BASE)
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/projects/p1/metadata-fields'))
    expect(membersRequested()).toBe(false)

    await user.click(document.querySelector('[data-field-shortcut="assignee"]') as HTMLElement)
    await waitFor(() => expect(membersRequested()).toBe(true))
  })

  it('fetches members at once when the file already has an assignee', async () => {
    renderEditor({ ...BASE, assignee_id: 'u1' } as Asset)
    await waitFor(() => expect(membersRequested()).toBe(true))
  })
})
