'use client'

import * as React from 'react'
import Link from 'next/link'
import { ExternalLink } from 'lucide-react'
import { api } from '@/lib/api'
import { useToast } from '@/components/shared/toast'
import {
  initialQueue, nextOffset, preloadTargets, queueReducer, shouldFetchMore,
} from '@/lib/review-queue'
import { ReviewPreview } from './review-preview'
import type { ReviewQueuePage } from '@/types'

const PAGE_SIZE = 20

function statusOf(err: unknown): number | undefined {
  return typeof err === 'object' && err !== null ? (err as { status?: number }).status : undefined
}

function messageOf(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)
}

// source_link.normalize accepts any non-blank text (it may be a shared-drive
// path, not a URL), so this is not validation of the editor's input — it is
// what decides whether we hand the browser something it will navigate to.
// A `javascript:` value must never become a clickable href.
function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value)
}

/**
 * Files in the Review stage, one at a time. A approves (→ Done) and moves on.
 * R jumps to the comment box; sending it rejects (→ Revision) with that
 * comment, which the editor sees and is emailed. Arrows skip.
 */
export function ReviewQueue() {
  const toast = useToast()
  // useToast returns a fresh object each render; read it through a ref so the
  // loaders below keep a stable identity and do not refetch on every render.
  const toastRef = React.useRef(toast)
  toastRef.current = toast

  const [state, dispatch] = React.useReducer(queueReducer, initialQueue)
  const [banner, setBanner] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [loadError, setLoadError] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const [comment, setComment] = React.useState('')
  const loadingRef = React.useRef(false)
  const lastOffsetRef = React.useRef(0)
  const commentRef = React.useRef<HTMLTextAreaElement>(null)

  const load = React.useCallback(async (offset: number) => {
    if (loadingRef.current) return
    loadingRef.current = true
    lastOffsetRef.current = offset
    try {
      const page = await api.get<ReviewQueuePage>(`/review-queue?limit=${PAGE_SIZE}&offset=${offset}`)
      dispatch({ type: 'loaded', page })
      setBanner(null)
      setLoadError(false)
    } catch (err) {
      // 409 = a stage the queue needs is missing. Say which, so it can be fixed.
      if (statusOf(err) === 409) setBanner(messageOf(err, 'A review stage is missing'))
      else {
        // Otherwise the empty state would read "Nothing to review." — which a
        // reviewer takes as "queue is clear" rather than "this failed".
        toastRef.current.error(messageOf(err, 'Could not load the review queue'))
        setLoadError(true)
      }
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load(0)
  }, [load])

  // Keep a page ahead of the reviewer.
  React.useEffect(() => {
    if (!loading && shouldFetchMore(state)) void load(nextOffset(state))
  }, [state, loading, load])

  const current = state.items[state.index] ?? null

  React.useEffect(() => {
    setComment('')
  }, [current?.asset_id])

  const decide = React.useCallback(
    async (kind: 'approve' | 'reject') => {
      if (!current || !state.stages || busy) return
      const text = comment.trim()
      if (kind === 'reject' && !text) {
        commentRef.current?.focus()
        return
      }
      setBusy(true)
      try {
        await api.patch(`/assets/${current.asset_id}/task-stage`, {
          task_stage_id: kind === 'approve' ? state.stages.done : state.stages.revision,
          expected_stage_id: state.stages.review,
          ...(kind === 'reject' ? { comment: text, version_id: current.version_id } : {}),
        })
        dispatch({ type: 'removed', assetId: current.asset_id })
        commentRef.current?.blur()
      } catch (err) {
        if (statusOf(err) === 409) {
          // Someone else moved it out of Review: it is not ours to decide now.
          dispatch({ type: 'removed', assetId: current.asset_id })
          toastRef.current.error('That file was already moved out of Review by someone else.')
        } else {
          // Stays in place, no advance: the reviewer must see it did not happen.
          toastRef.current.error(messageOf(err, 'Could not update that file'))
        }
      } finally {
        setBusy(false)
      }
    },
    [current, state.stages, busy, comment],
  )

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'a' || e.key === 'A') {
        e.preventDefault()
        // Holding the key down must not approve a run of files unseen.
        if (e.repeat) return
        void decide('approve')
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        if (e.repeat) return
        commentRef.current?.focus()
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        dispatch({ type: 'next' })
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        dispatch({ type: 'prev' })
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [decide])

  if (banner) {
    return (
      <div className="p-6">
        <p role="alert" className="rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2 text-sm text-status-error">
          {banner}
        </p>
      </div>
    )
  }
  if (loading && !current) return <p className="p-6 text-sm text-text-tertiary">Loading…</p>
  if (loadError && !current) {
    return (
      <div className="flex flex-col items-start gap-3 p-6">
        <p className="text-sm text-text-secondary">Could not load the review queue</p>
        <button
          type="button"
          onClick={() => void load(lastOffsetRef.current)}
          className="rounded-md border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover"
        >
          Retry
        </button>
      </div>
    )
  }
  if (!current) return <p className="p-6 text-sm text-text-secondary">Nothing to review.</p>

  const preloads = preloadTargets(state)
    .map((i) => (i.asset_type === 'video' ? i.thumbnail_url : i.preview_url))
    .filter((u): u is string => !!u)

  return (
    <div className="grid h-full gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex min-h-[50vh] items-center justify-center overflow-hidden rounded-lg bg-bg-secondary">
        <ReviewPreview item={current} />
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between text-xs text-text-tertiary">
          <span className="tabular-nums">
            {state.index + 1} of {state.total}
          </span>
          <span className="flex gap-1">
            <button type="button" onClick={() => dispatch({ type: 'prev' })} className="rounded px-2 py-1 hover:bg-bg-hover">
              ← Previous
            </button>
            <button type="button" onClick={() => dispatch({ type: 'next' })} className="rounded px-2 py-1 hover:bg-bg-hover">
              Next →
            </button>
          </span>
        </div>

        <div>
          <h2 className="truncate text-base font-semibold text-text-primary">{current.file_name}</h2>
          {current.brief_id ? (
            <Link href={`/projects/requests/${current.brief_id}`} className="text-sm text-accent hover:underline">
              {current.brief_title}
            </Link>
          ) : (
            <p className="text-sm text-text-tertiary">No brief</p>
          )}
          <p className="mt-1 text-sm text-text-secondary">{current.editor_name ?? 'Unknown editor'}</p>
          <Link
            href={`/projects/${current.project_id}/assets/${current.asset_id}?from=/review`}
            target="_blank"
            className="mt-1 inline-block text-xs text-text-tertiary hover:underline"
          >
            Open file page
          </Link>
        </div>

        {current.canva_url && isHttpUrl(current.canva_url) ? (
          <a
            href={current.canva_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open source
          </a>
        ) : current.canva_url ? (
          // Not an http(s) URL — e.g. a shared-drive path. Show it, but never
          // as a clickable href: that is how a `javascript:` value would get
          // to execute in an admin's session.
          <p className="break-all rounded-md border border-dashed border-border px-3 py-2 text-center text-sm text-text-tertiary">
            {current.canva_url}
          </p>
        ) : (
          <p className="rounded-md border border-dashed border-border px-3 py-2 text-center text-sm text-text-tertiary">
            No source link
          </p>
        )}

        <button
          type="button"
          onClick={() => void decide('approve')}
          disabled={busy}
          className="rounded-md bg-status-success px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Approve (A)
        </button>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            void decide('reject')
          }}
          className="flex flex-col gap-2"
        >
          <textarea
            ref={commentRef}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                void decide('reject')
              } else if (e.key === 'Escape') {
                e.currentTarget.blur()
              }
            }}
            aria-label="What needs to change"
            placeholder="What needs to change? (R)"
            rows={4}
            className="w-full rounded-md border border-border bg-bg-secondary px-2 py-1.5 text-sm text-text-primary placeholder:text-text-tertiary"
          />
          <button
            type="submit"
            disabled={busy || !comment.trim()}
            className="rounded-md border border-status-error/40 px-3 py-2 text-sm text-status-error disabled:opacity-50"
          >
            Send back for revision (⌘↵)
          </button>
        </form>
      </div>

      {/* The next previews, loaded now so moving on is instant. */}
      <div hidden>
        {preloads.map((src) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={src} src={src} alt="" data-preload />
        ))}
      </div>
    </div>
  )
}
