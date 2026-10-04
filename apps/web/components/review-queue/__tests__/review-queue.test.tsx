/**
 * An admin should clear a queue of editors without leaving the page. An item
 * is one editor on one brief: A moves that editor to Done and moves on, R jumps
 * to the comment box and sending it moves the editor to Revision with the
 * comment pinned on the file on screen, arrows skip between editors, [ and ]
 * flip between that editor's files. Decisions go through the same editor-stage
 * endpoint the /tasks board uses. The letter keys must do nothing while typing
 * a comment, or "Logo is cropped" would approve the editor at the first "a".
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
import type { ReviewFile, ReviewQueueItem, ReviewQueuePage } from '@/types'

const STAGES = { review: 'st-review', done: 'st-done', revision: 'st-revision' }

function file(n: number, i: number, over: Partial<ReviewFile> = {}): ReviewFile {
  return {
    asset_id: `a${n}-${i}`, version_id: `v${n}-${i}`, file_name: `hook-${n}-${i}.png`, asset_type: 'image',
    thumbnail_url: `https://s3/t${n}-${i}`, preview_url: `https://s3/p${n}-${i}`,
    canva_url: `https://www.canva.com/design/${n}-${i}/edit`,
    ...over,
  }
}

function item(n: number, over: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    submission_id: `s${n}`, brief_id: `b${n}`, brief_title: `Brief ${n}`, brief_token: 'tok',
    project_id: `p${n}`, editor_id: `u${n}`, editor_name: `Editor ${n}`, expected_stage_id: 'st-review',
    waited_since: '2026-10-01T00:00:00Z', files: [file(n, 0)],
    ...over,
  }
}

const page = (items: ReviewQueueItem[], total = items.length): ReviewQueuePage => ({ items, total, stages: STAGES })
const heading = (name: string) => screen.findByRole('heading', { level: 2, name })
const commentBox = () => screen.getByLabelText(/what needs to change/i)
const openSource = () => screen.getByRole('link', { name: /open source/i })

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockResolvedValue(page([item(1), item(2), item(3)]) as never)
  vi.mocked(api.patch).mockResolvedValue({} as never)
})

describe('ReviewQueue — keys', () => {
  it("A moves the editor on screen to Done through the editor-stage endpoint and moves on", async () => {
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    await user.keyboard('a')
    expect(api.patch).toHaveBeenCalledWith('/submission-links/b1/editors/u1/task-stage', {
      task_stage_id: 'st-done', expected_stage_id: 'st-review',
    })
    await heading('Brief 2')
  })

  it('R focuses the comment box; sending it moves the editor to Revision with the comment and moves on', async () => {
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    await user.keyboard('r')
    expect(commentBox()).toHaveFocus()
    expect(commentBox()).toHaveValue('')
    await user.type(commentBox(), 'Logo is cropped')
    await user.click(screen.getByRole('button', { name: /send back/i }))
    expect(api.patch).toHaveBeenCalledWith('/submission-links/b1/editors/u1/task-stage', {
      task_stage_id: 'st-revision', expected_stage_id: 'st-review',
      comment: 'Logo is cropped', version_id: 'v1-0',
    })
    await heading('Brief 2')
  })

  it('pins the revision comment on the file being looked at, not the first one', async () => {
    vi.mocked(api.get).mockResolvedValue(page([item(1, { files: [file(1, 0), file(1, 1)] })]) as never)
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    await user.keyboard(']')
    await user.type(commentBox(), 'Wrong price')
    await user.click(screen.getByRole('button', { name: /send back/i }))
    expect(api.patch).toHaveBeenCalledWith('/submission-links/b1/editors/u1/task-stage', expect.objectContaining({
      version_id: 'v1-1',
    }))
  })

  it('[ and ] flip between the editor’s files, and so does clicking a thumbnail', async () => {
    vi.mocked(api.get).mockResolvedValue(page([item(1, { files: [file(1, 0), file(1, 1), file(1, 2)] })]) as never)
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    expect(screen.getByText(/\[ \] switch file/i)).toBeInTheDocument()
    expect(openSource()).toHaveAttribute('href', 'https://www.canva.com/design/1-0/edit')
    await user.keyboard(']')
    expect(openSource()).toHaveAttribute('href', 'https://www.canva.com/design/1-1/edit')
    await user.keyboard('[[') // '[[' is a literal '[' in user-event
    expect(openSource()).toHaveAttribute('href', 'https://www.canva.com/design/1-0/edit')
    await user.click(screen.getByRole('button', { name: 'hook-1-2.png' }))
    expect(openSource()).toHaveAttribute('href', 'https://www.canva.com/design/1-2/edit')
    expect(screen.getByRole('button', { name: 'hook-1-2.png' })).toHaveAttribute('aria-pressed', 'true')
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('ignores the shortcut keys while typing in the comment box', async () => {
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    await user.click(commentBox())
    await user.keyboard('ar')
    expect(api.patch).not.toHaveBeenCalled()
    expect(commentBox()).toHaveValue('ar')
  })

  it('arrow keys skip editors without deciding', async () => {
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    await user.keyboard('{ArrowRight}')
    await heading('Brief 2')
    await user.keyboard('{ArrowLeft}')
    await heading('Brief 1')
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('will not send an editor back with an empty comment', async () => {
    render(<ReviewQueue />)
    await heading('Brief 1')
    expect(screen.getByRole('button', { name: /send back/i })).toBeDisabled()
  })

  it('ignores key auto-repeat so holding A cannot approve editors unseen', async () => {
    render(<ReviewQueue />)
    await heading('Brief 1')
    fireEvent.keyDown(document, { key: 'a', repeat: true })
    expect(api.patch).not.toHaveBeenCalled()
    await heading('Brief 1')
  })
})

describe('ReviewQueue — failures', () => {
  it('a failed decision leaves the editor in place with an error', async () => {
    vi.mocked(api.patch).mockRejectedValueOnce(Object.assign(new Error('Server exploded'), { status: 500 }))
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    await user.keyboard('a')
    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Server exploded'))
    expect(screen.getByRole('heading', { level: 2, name: 'Brief 1' })).toBeInTheDocument()
  })

  it('drops an editor someone else already moved out of Review, and says so', async () => {
    vi.mocked(api.patch).mockRejectedValueOnce(
      Object.assign(new Error('This editor is no longer in that stage'), { status: 409 }),
    )
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    await user.keyboard('a')
    await heading('Brief 2')
    expect(toastError).toHaveBeenCalledWith(expect.stringMatching(/already moved out of Review/))
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
    await heading('Brief 1')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/review-queue?limit=20&offset=3'))
  })

  it('preloads the next two editors’ first previews', async () => {
    render(<ReviewQueue />)
    await heading('Brief 1')
    const srcs = Array.from(document.querySelectorAll('img[data-preload]')).map((i) => i.getAttribute('src'))
    expect(srcs).toEqual(['https://s3/p2-0', 'https://s3/p3-0'])
  })
})

describe('ReviewQueue — what is shown', () => {
  it('names the brief, links to it, and names the editor and how many files they sent', async () => {
    vi.mocked(api.get).mockResolvedValue(page([item(1, { files: [file(1, 0), file(1, 1)] })]) as never)
    render(<ReviewQueue />)
    await heading('Brief 1')
    expect(screen.getByRole('link', { name: 'Brief 1' })).toHaveAttribute('href', '/projects/requests/b1')
    expect(screen.getByText('Editor 1')).toBeInTheDocument()
    expect(screen.getByText('2 files')).toBeInTheDocument()
  })

  it('says "No source link" rather than hiding the gap', async () => {
    vi.mocked(api.get).mockResolvedValue(page([item(1, { files: [file(1, 0, { canva_url: null })] })]) as never)
    render(<ReviewQueue />)
    await heading('Brief 1')
    expect(screen.getByText('No source link')).toBeInTheDocument()
  })

  it('never turns a javascript: source value into a clickable link', async () => {
    vi.mocked(api.get).mockResolvedValue(
      page([item(1, { files: [file(1, 0, { canva_url: 'javascript:alert(1)' })] })]) as never,
    )
    render(<ReviewQueue />)
    await heading('Brief 1')
    expect(screen.queryByRole('link', { name: /open source/i })).toBeNull()
    expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument()
  })

  it('shows a still-processing file as its thumbnail, not a broken player', async () => {
    vi.mocked(api.get).mockResolvedValue(page([item(1, { files: [file(1, 0, { preview_url: null })] })]) as never)
    render(<ReviewQueue />)
    await heading('Brief 1')
    expect(screen.getByText(/still processing/i)).toBeInTheDocument()
  })

  it('shows an editor with no files as such; they can be approved but not sent back about a file', async () => {
    vi.mocked(api.get).mockResolvedValue(page([item(1, { files: [] })]) as never)
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await heading('Brief 1')
    expect(screen.getByText('No files uploaded.')).toBeInTheDocument()
    await user.type(commentBox(), 'Where is it?')
    expect(screen.getByRole('button', { name: /send back/i })).toBeDisabled()
  })

  it('says "Nothing to review." when the queue is empty', async () => {
    vi.mocked(api.get).mockResolvedValue(page([]) as never)
    render(<ReviewQueue />)
    expect(await screen.findByText('Nothing to review.')).toBeInTheDocument()
  })
})

describe('ReviewQueue — load failure', () => {
  it('shows an error and a Retry instead of "Nothing to review." when the first load fails', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(Object.assign(new Error('Server exploded'), { status: 500 }))
    render(<ReviewQueue />)
    expect(await screen.findByText('Could not load the review queue')).toBeInTheDocument()
    expect(screen.queryByText('Nothing to review.')).toBeNull()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('Retry re-runs the load, and an editor shows once it succeeds', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(Object.assign(new Error('Server exploded'), { status: 500 }))
    const user = userEvent.setup()
    render(<ReviewQueue />)
    await screen.findByText('Could not load the review queue')
    await user.click(screen.getByRole('button', { name: /retry/i }))
    await heading('Brief 1')
  })
})
