/**
 * Why this component exists: a title typed as one free-text box could miss a
 * slot, and the playbook then reads the brief as having no persona and no lens
 * at all. The fields make the six slots separate boxes, and the preview is what
 * lets someone confirm the title before it is written.
 *
 * The convention toggle is kept because /submissions also creates requests that
 * are not ad briefs ("Video Editor Interview") — forcing a persona on those
 * would put a fiction in the coverage matrix.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { BriefTitleFields, EMPTY_BRIEF_TITLE, type BriefTitleValue } from '../brief-title-fields'

const filled: BriefTitleValue = {
  useConvention: true, title: '', date: '20260910', sku: 'iPhone 17',
  persona: 'Frugal Phone Buyer', lens: 'Fear', hook: 'Battery dies by 3pm',
  format: 'Static', angle: 'A28 Battery anxiety',
}

describe('BriefTitleFields', () => {
  it('previews the title it will write', () => {
    render(<BriefTitleFields value={filled} onChange={vi.fn()} />)

    expect(screen.getByTestId('title-preview')).toHaveTextContent(
      '20260910 - iPhone 17 - Frugal Phone Buyer - Fear - Battery dies by 3pm - Static',
    )
  })

  it('names the empty slot instead of previewing a broken title', () => {
    render(<BriefTitleFields value={{ ...filled, lens: '' }} onChange={vi.fn()} />)

    expect(screen.getByTestId('title-preview')).toHaveTextContent(/lens/i)
  })

  it('keeps the angle out of the title but still asks for it', async () => {
    // Angle is not a slot — it is the label the coverage matrix counts, so a brief
    // created without one is uncounted however well it is titled.
    render(<BriefTitleFields value={filled} onChange={vi.fn()} />)

    expect(screen.getByTestId('title-preview')).not.toHaveTextContent('A28')
    expect(screen.getByLabelText(/angle/i)).toHaveValue('A28 Battery anxiety')
  })

  it('reports each edit as the whole value, so the form holds one piece of state', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<BriefTitleFields value={{ ...EMPTY_BRIEF_TITLE }} onChange={onChange} />)

    await user.type(screen.getByLabelText(/hook/i), 'B')

    expect(onChange).toHaveBeenCalledWith({ ...EMPTY_BRIEF_TITLE, hook: 'B' })
  })

  it('falls back to one free-text title when the convention is off', () => {
    render(<BriefTitleFields value={{ ...filled, useConvention: false }} onChange={vi.fn()} />)

    expect(screen.getByLabelText(/^title$/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/hook/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('title-preview')).not.toBeInTheDocument()
  })
})
