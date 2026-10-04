/**
 * An admin should clear a queue of files without leaving the page:
 * A approves and moves on, R jumps to the comment box and sending it rejects
 * and moves on, arrows skip. The letter keys must do nothing while typing a
 * comment, or "Logo is cropped" would approve the file at the first "a".
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
const toastError = vi.fn()
vi.mock('@/components/shared/toast', () => ({
  useToast: () => ({ success: vi.fn(), error: toastError, info: vi.fn(), warning: vi.fn() }),
}))
import { api } from '@/lib/api'
import { ReviewQueue } from '../review-queue'
import type { ReviewQueueItem, ReviewQueuePage } from '@/types'

const STAGES = { review: 'st-review', done: 'st-done', revision: 'st-revision' }

function item(n: number, over: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    asset_id: `a${n}`, version_id: `v${n}`, project_id: 'p1', asset_type: 'image',
    file_name: `hook-${n}.png`, brief_id: 'b1', brief_title: 'Battery brief', brief_token: 'tok',
    editor_name: 'Ada', thumbnail_url: `https://s3/t${n}`, preview_url: `https://s3/p${n}`,
    canva_url: 'https://www.canva.com/design/x/edit', submitted_at: '2026-10-01T00:00:00Z',
    ...over,
  }
}

const page = (items: ReviewQueueItem[], total = items.length): ReviewQueuePage => ({ items, total, stages: STAGES })
const heading = (name: string) => screen.findByRole('heading', { level: 2, name })
const commentBox = () => screen.getByLabelText(/what needs to change/i)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockResolvedValue(page([item(1), item(2), item(3)]) as never)
  vi.mocked(api.patch).mockResolvedValue({} as never)
})

describe('ReviewQueue — keys', () => {
  it('A approves the file on screen and moves to the next', async () => {
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('hook-1.png')
    await user.keyboard('a')
    expect(api.patch).toHaveBeenCalledWith('/assets/a1/task-stage', {
      task_stage_id: 'st-done', expected_stage_id: 'st-review',
    })
    await heading('hook-2.png')
  })

  it('R focuses the comment box; sending it rejects with the comment and moves on', async () => {
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('hook-1.png')
    await user.keyboard('r')
    expect(commentBox()).toHaveFocus()
    expect(commentBox()).toHaveValue('')
    await user.type(commentBox(), 'Logo is cropped')
    await user.click(screen.getByRole('button', { name: /send back/i }))
    expect(api.patch).toHaveBeenCalledWith('/assets/a1/task-stage', {
      task_stage_id: 'st-revision', expected_stage_id: 'st-review',
      comment: 'Logo is cropped', version_id: 'v1',
    })
    await heading('hook-2.png')
  })

  it('ignores the shortcut keys while typing in the comment box', async () => {
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('hook-1.png')
    await user.click(commentBox())
    await user.keyboard('ar')
    expect(api.patch).not.toHaveBeenCalled()
    expect(commentBox()).toHaveValue('ar')
  })

  it('arrow keys skip without deciding', async () => {
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('hook-1.png')
    await user.keyboard('{ArrowRight}')
    await heading('hook-2.png')
    await user.keyboard('{ArrowLeft}')
    await heading('hook-1.png')
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('will not send a file back with an empty comment', async () => {
    render(<ReviewQueue />)
    await heading('hook-1.png')
    expect(screen.getByRole('button', { name: /send back/i })).toBeDisabled()
  })

  it('ignores key auto-repeat so holding A cannot approve files unseen', async () => {
    render(<ReviewQueue />)
    await heading('hook-1.png')
    fireEvent.keyDown(document, { key: 'a', repeat: true })
    expect(api.patch).not.toHaveBeenCalled()
    await heading('hook-1.png')
  })
})

describe('ReviewQueue — failures', () => {
  it('a failed decision leaves the file in place with an error', async () => {
    vi.mocked(api.patch).mockRejectedValueOnce(Object.assign(new Error('Server exploded'), { status: 500 }))
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('hook-1.png')
    await user.keyboard('a')
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Server exploded'))
    expect(screen.getByRole('heading', { level: 2, name: 'hook-1.png' })).toBeInTheDocument()
  })

  it('drops a file someone else already moved out of Review', async () => {
    vi.mocked(api.patch).mockRejectedValueOnce(
      Object.assign(new Error('This file is no longer in that stage'), { status: 409 }),
    )
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('hook-1.png')
    await user.keyboard('a')
    await heading('hook-2.png')
  })

  it('shows a missing stage as a banner', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(
      Object.assign(new Error('Missing task stage: Revision'), { status: 409 }),
    )
    render(<ReviewQueue />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Missing task stage: Revision')
  })
})

describe('ReviewQueue — loading ahead', () => {
  it('fetches the next page when five or fewer remain', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce(page([item(1), item(2), item(3)], 10) as never)
      .mockResolvedValueOnce(page([item(4)], 10) as never)
    render(<ReviewQueue />)
    await heading('hook-1.png')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/review-queue?limit=20&offset=3'))
  })

  it('preloads the next two previews', async () => {
    render(<ReviewQueue />)
    await heading('hook-1.png')
    const srcs = Array.from(document.querySelectorAll('img[data-preload]')).map((i) => i.getAttribute('src'))
    expect(srcs).toEqual(['https://s3/p2', 'https://s3/p3'])
  })
})

describe('ReviewQueue — what is shown', () => {
  it('links to the editable source design', async () => {
    render(<ReviewQueue />)
    await heading('hook-1.png')
    expect(screen.getByRole('link', { name: /open source/i })).toHaveAttribute(
      'href', 'https://www.canva.com/design/x/edit',
    )
  })

  it('says "No source link" rather than hiding the gap', async () => {
    vi.mocked(api.get).mockResolvedValue(page([item(1, { canva_url: null })]) as never)
    render(<ReviewQueue />)
    await heading('hook-1.png')
    expect(screen.getByText('No source link')).toBeInTheDocument()
  })

  it('never turns a javascript: source value into a clickable link', async () => {
    vi.mocked(api.get).mockResolvedValue(
      page([item(1, { canva_url: 'javascript:alert(1)' })]) as never,
    )
    render(<ReviewQueue />)
    await heading('hook-1.png')
    expect(screen.queryByRole('link', { name: /open source/i })).toBeNull()
    expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument()
  })

  it('shows a still-processing file as its thumbnail, not a broken player', async () => {
    vi.mocked(api.get).mockResolvedValue(page([item(1, { preview_url: null })]) as never)
    render(<ReviewQueue />)
    await heading('hook-1.png')
    expect(screen.getByText(/still processing/i)).toBeInTheDocument()
  })

  it('says "Nothing to review." when the queue is empty', async () => {
    vi.mocked(api.get).mockResolvedValue(page([]) as never)
    render(<ReviewQueue />)
    expect(await screen.findByText('Nothing to review.')).toBeInTheDocument()
  })
})
