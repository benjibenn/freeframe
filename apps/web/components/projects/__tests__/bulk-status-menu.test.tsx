/**
 * One menu serves two call sites: the multi-select action bar at the bottom of
 * the grid, and the project toolbar at the top, where the pick applies to the
 * whole folder instead of a selection. The toolbar needed new props, so these
 * tests pin the bar's behaviour to the defaults — a silently flipped default
 * would make the bar's menu open off-screen or mislabel itself.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SWRConfig } from 'swr'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'

vi.mock('@/stores/auth-store', () => ({ useAuthStore: () => ({ user: mockUser }) }))

import { BulkStatusMenu } from '../bulk-status-menu'

let mockUser: { is_superadmin: boolean; is_subadmin: boolean } | null = null

const STAGES = [{ id: 's1', name: 'Review', position: 1, color: '#fff' }]

function renderMenu(props: Partial<React.ComponentProps<typeof BulkStatusMenu>> = {}) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <BulkStatusMenu onSetStage={props.onSetStage ?? vi.fn()} {...props} />
    </SWRConfig>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUser = { is_superadmin: true, is_subadmin: false }
  vi.mocked(api.get).mockResolvedValue(STAGES)
})

describe('BulkStatusMenu', () => {
  it('labels itself "Set status" and opens upward unless told otherwise', async () => {
    renderMenu()
    await userEvent.click(screen.getByRole('button', { name: /set status/i }))
    await waitFor(() => expect(screen.getByText('Review')).toBeInTheDocument())
    // Radix stamps the resolved side on the content wrapper.
    expect(document.querySelector('[data-side="top"]')).not.toBeNull()
    expect(screen.getByText('Pipeline stage')).toBeInTheDocument()
  })

  it('takes a toolbar label, downward side and scope wording', async () => {
    renderMenu({ label: 'Bulk status', side: 'bottom', scopeHint: 'Every file in Hooks' })
    await userEvent.click(screen.getByRole('button', { name: /bulk status/i }))
    await waitFor(() => expect(screen.getByText('Every file in Hooks')).toBeInTheDocument())
    expect(document.querySelector('[data-side="bottom"]')).not.toBeNull()
    expect(screen.queryByText('Pipeline stage')).toBeNull()
  })

  it('offers Unassigned so a folder can be cleared, not only set', async () => {
    const onSetStage = vi.fn()
    renderMenu({ onSetStage })
    await userEvent.click(screen.getByRole('button', { name: /set status/i }))
    await userEvent.click(await screen.findByText('Unassigned'))
    expect(onSetStage).toHaveBeenCalledWith(null)
  })

  it('renders nothing for a non-admin, so the stage never leaks to project editors', () => {
    mockUser = { is_superadmin: false, is_subadmin: false }
    const { container } = renderMenu()
    expect(container).toBeEmptyDOMElement()
    expect(api.get).not.toHaveBeenCalled()
  })
})
