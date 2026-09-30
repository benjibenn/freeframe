/**
 * Why this exists: a new version upload starts the instant a file is picked, so
 * without this prompt the required source link would have nowhere to be typed and
 * every revision would fail at the API with a 422.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { SourceLinkPrompt } from '../source-link-prompt'

describe('SourceLinkPrompt', () => {
  it('will not upload until a link is given', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<SourceLinkPrompt fileName="hook1-v2.mp4" onCancel={vi.fn()} onConfirm={onConfirm} />)

    const upload = screen.getByRole('button', { name: 'Upload' })
    expect(upload).toBeDisabled()

    await user.type(screen.getByLabelText('Source link'), '  https://figma.com/file/abc  ')
    await user.click(upload)

    // Trimmed: a stray space would be stored in the comment verbatim.
    expect(onConfirm).toHaveBeenCalledWith('https://figma.com/file/abc')
  })

  it('whitespace alone is not a link', async () => {
    const user = userEvent.setup()
    render(<SourceLinkPrompt fileName="v2.mp4" onCancel={vi.fn()} onConfirm={vi.fn()} />)

    await user.type(screen.getByLabelText('Source link'), '   ')

    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled()
  })

  it('names the file being uploaded, so the right link gets pasted', () => {
    render(<SourceLinkPrompt fileName="hook3-swedish.png" onCancel={vi.fn()} onConfirm={vi.fn()} />)

    expect(screen.getByText(/hook3-swedish\.png/)).toBeInTheDocument()
  })

  it('cancelling uploads nothing', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(<SourceLinkPrompt fileName="v2.mp4" onCancel={onCancel} onConfirm={onConfirm} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
