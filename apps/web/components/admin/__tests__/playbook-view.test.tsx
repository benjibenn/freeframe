/**
 * The feature in one test: pick a brand, tick briefs across models, and the
 * clipboard gets their submit links grouped under each model.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { PlaybookView } from '../playbook-view'
import type { PlaybookSource } from '@/lib/playbook'

const row = (id: string, model: string, hook: string, files = 1): PlaybookSource => ({
  id, token: `tok-${id}`, home_path: `ecom/Phones/Stokora/${model}`,
  title: `20260910 - x - Frugal Phone Buyer - Fear - ${hook} - Static`,
  persona_label: null, angle_label: 'A1', submission_count: 1, asset_count: files,
})

describe('PlaybookView', () => {
  it('copies the selected links grouped by model', async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })

    render(<PlaybookView origin="https://ff.test" rows={[
      row('a', 'iPhone 17', 'Battery'), row('b', 'iPhone 9', 'Battery', 0), row('c', 'iPhone 17', 'Price'),
    ]} />)

    // Drill in the way an admin does: top level, then each subfolder chip.
    for (const name of ['ecom', 'Phones', 'Stokora']) {
      await user.click(screen.getByRole('button', { name: new RegExp(`^${name} \\d+$`) }))
    }
    expect(window.location.search).toBe('?folder=ecom%2FPhones%2FStokora')
    // Frugal Phone Buyer × A1: 3 briefs, 2 with files. b has a submission but no files.
    expect(screen.getByRole('button', { name: '2/3' })).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Group'), 'model')
    for (const box of screen.getAllByLabelText(/^Select 2026.* Battery /)) await user.click(box)
    await user.click(screen.getByRole('button', { name: /selected by model/ }))

    expect(writeText).toHaveBeenCalledWith(
      'iPhone 9\nBattery: https://ff.test/submit/tok-b\n\niPhone 17\nBattery: https://ff.test/submit/tok-a',
    )
    expect(screen.getByRole('status')).toHaveTextContent('Copied 2 links across 2 models.')
  })

  it('opens the folder named in the URL, so a brand view can be bookmarked', () => {
    window.history.replaceState(null, '', '/admin/playbook?folder=ecom%2FPhones%2FStokora')
    render(<PlaybookView origin="https://ff.test" rows={[row('a', 'iPhone 17', 'Battery')]} />)

    expect(screen.getByText('1 briefs · 1 with files · 1 files')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^iPhone 17 1$/ })).toBeInTheDocument()
  })
})
