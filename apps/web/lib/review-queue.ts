import type { ReviewFile, ReviewQueueItem, ReviewQueuePage } from '@/types'

/**
 * The /review queue's state, apart from React. An item is one editor on one
 * brief, waiting in Review, with the files they delivered.
 *
 * A decided item is removed and the next slides into its slot: that is the
 * auto-advance. Every item still listed is still in Review on the server, ahead
 * of anything not yet loaded, so the next page starts at items.length.
 */
export interface QueueState {
  items: ReviewQueueItem[]
  index: number
  /** The file shown within the current item. Back to 0 whenever the item changes. */
  fileIndex: number
  total: number
  stages: ReviewQueuePage['stages'] | null
  /** The last page brought nothing new. Auto-fetch stops until a decision. */
  stalled: boolean
}

export type QueueAction =
  | { type: 'loaded'; page: ReviewQueuePage }
  | { type: 'next' }
  | { type: 'prev' }
  | { type: 'removed'; submissionId: string }
  | { type: 'nextFile' }
  | { type: 'prevFile' }
  | { type: 'selectFile'; index: number }

export const initialQueue: QueueState = {
  items: [], index: 0, fileIndex: 0, total: 0, stages: null, stalled: false,
}

function clampFile(state: QueueState, fileIndex: number): number {
  const count = state.items[state.index]?.files.length ?? 0
  return Math.min(Math.max(fileIndex, 0), Math.max(count - 1, 0))
}

export function queueReducer(state: QueueState, action: QueueAction): QueueState {
  switch (action.type) {
    case 'loaded': {
      const seen = new Set(state.items.map((i) => i.submission_id))
      const fresh = action.page.items.filter((i) => !seen.has(i.submission_id))
      return {
        ...state,
        items: [...state.items, ...fresh],
        total: action.page.total,
        stages: action.page.stages,
        stalled: fresh.length === 0,
      }
    }
    case 'next':
      return { ...state, index: Math.min(state.index + 1, Math.max(state.items.length - 1, 0)), fileIndex: 0 }
    case 'prev':
      return { ...state, index: Math.max(state.index - 1, 0), fileIndex: 0 }
    case 'removed': {
      const at = state.items.findIndex((i) => i.submission_id === action.submissionId)
      if (at === -1) return state
      const items = state.items.filter((_, i) => i !== at)
      const index =
        at < state.index ? state.index - 1 : Math.min(state.index, Math.max(items.length - 1, 0))
      return { ...state, items, index, fileIndex: 0, total: Math.max(state.total - 1, 0), stalled: false }
    }
    case 'nextFile':
      return { ...state, fileIndex: clampFile(state, state.fileIndex + 1) }
    case 'prevFile':
      return { ...state, fileIndex: clampFile(state, state.fileIndex - 1) }
    case 'selectFile':
      return { ...state, fileIndex: clampFile(state, action.index) }
  }
}

/** The file on screen, or null when the queue is empty or the editor uploaded nothing. */
export function currentFile(state: QueueState): ReviewFile | null {
  return state.items[state.index]?.files[state.fileIndex] ?? null
}

/** Server offset for the next page. */
export function nextOffset(state: QueueState): number {
  return state.items.length
}

export function hasMore(state: QueueState): boolean {
  return state.items.length < state.total
}

/** Keep a page ahead: fetch when `threshold` or fewer remain after the current item. */
export function shouldFetchMore(state: QueueState, threshold = 5): boolean {
  return !state.stalled && hasMore(state) && state.items.length - state.index - 1 <= threshold
}

/** The items after the current one whose previews are worth loading now. */
export function preloadTargets(state: QueueState, n = 2): ReviewQueueItem[] {
  return state.items.slice(state.index + 1, state.index + 1 + n)
}
