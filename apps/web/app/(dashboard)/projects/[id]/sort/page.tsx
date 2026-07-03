'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import type { AssetResponse, AssetStatus } from '@/types'
import { TagStampBar } from '@/components/review/tag-stamp-bar'
import { useVideoPlayer } from '@/hooks/use-video-player'
import { useSorterQueue } from '@/hooks/use-sorter-queue'
import { useSorterStore, getBindings } from '@/stores/sorter-store'
import { keyToAction } from '@/lib/sorter/keymap'
import { enqueueWrite } from '@/lib/sorter/write-queue'
import { TagInput } from '@/components/sorter/tag-input'
import { SlotBar } from '@/components/sorter/slot-bar'
import { useToast } from '@/components/shared/toast'
import { ShortcutsHint } from '@/components/ui/shortcuts-hint'
import { useSSE } from '@/hooks/use-sse'

const SORTER_SHORTCUTS = [
  {
    title: 'Navigation',
    items: [
      { keys: ['↑'], label: 'Previous asset' },
      { keys: ['↓'], label: 'Next asset' },
      { keys: ['Esc'], label: 'Exit sorter' },
    ],
  },
  {
    title: 'Playback',
    items: [
      { keys: ['Space'], label: 'Play / pause' },
      { keys: ['←'], label: 'Seek back 5 s' },
      { keys: ['→'], label: 'Seek forward 5 s' },
    ],
  },
  {
    title: 'Tagging',
    items: [
      { keys: ['1–9'], label: 'Toggle tag slot 1–9' },
      { keys: ['T'], label: 'Open tag input' },
      { keys: ['A'], label: 'Apply all tags' },
    ],
  },
  {
    title: 'Actions',
    items: [
      { keys: ['D'], label: 'Archive current asset' },
      { keys: ['Z'], label: 'Undo last action' },
    ],
  },
]

type Op =
  | { type: 'tag-add'; assetId: string; tag: string }
  | { type: 'tag-remove'; assetId: string; tag: string }
  | { type: 'archive'; asset: AssetResponse; index: number; prevStatus: AssetStatus }

export default function SorterPage() {
  const router = useRouter()
  const projectId = String(useParams().id)
  const queue = useSorterQueue(projectId)
  const seekStep = useSorterStore((s) => s.seekStep)
  const bindings = useSorterStore((s) => getBindings(s, projectId))
  const toast = useToast()

  const [streamUrl, setStreamUrl] = React.useState<string | null>(null)
  const [tagInputOpen, setTagInputOpen] = React.useState(false)
  const [recent, setRecent] = React.useState<string[]>([])
  const undoStack = React.useRef<Op[]>([])
  const player = useVideoPlayer(streamUrl)
  const current = queue.current

  useSSE(projectId, {
    onAutotagComplete: ({ asset_id, applied }) => {
      queue.patchById(asset_id, (prev) => Array.from(new Set([...prev, ...applied])))
    },
  })

  // Load the HLS stream URL whenever the current asset changes.
  React.useEffect(() => {
    if (!current) { setStreamUrl(null); return }
    let cancelled = false
    api.get<{ url: string }>(`/assets/${current.id}/stream`).then((r) => {
      if (!cancelled) setStreamUrl(r.url.startsWith('http') ? r.url : `${process.env.NEXT_PUBLIC_API_URL ?? ''}${r.url}`)
    })
    return () => { cancelled = true }
  }, [current?.id])

  const noteRecent = (tag: string) =>
    setRecent((r) => [tag, ...r.filter((t) => t !== tag)].slice(0, 10))

  const applyTag = (tag: string) => {
    if (!current) return
    const assetId = current.id
    const already = (current.keywords ?? []).includes(tag)
    if (already) return
    // Optimistic: add the tag immediately
    queue.patchCurrent((prev) => (prev.includes(tag) ? prev : [...prev, tag]))
    noteRecent(tag)
    enqueueWrite(assetId, async () => {
      try {
        const resp = await api.post<{ keywords: string[] }>(`/assets/${assetId}/tags/${encodeURIComponent(tag)}`)
        // Reconcile with server-authoritative keywords
        queue.patchCurrent(() => resp.keywords ?? [])
        undoStack.current.push({ type: 'tag-add', assetId, tag })
      } catch (err: unknown) {
        // Revert optimistic change
        queue.patchCurrent((prev) => prev.filter((t) => t !== tag))
        const msg = err instanceof Error ? err.message : 'Failed to add tag'
        toast.error(msg)
      }
    })
  }

  const removeTag = (tag: string) => {
    if (!current) return
    const assetId = current.id
    // Optimistic: remove immediately
    queue.patchCurrent((prev) => prev.filter((t) => t !== tag))
    enqueueWrite(assetId, async () => {
      try {
        const resp = await api.delete<{ keywords: string[] }>(`/assets/${assetId}/tags/${encodeURIComponent(tag)}`)
        // Reconcile with server-authoritative keywords
        queue.patchCurrent(() => resp.keywords ?? [])
        undoStack.current.push({ type: 'tag-remove', assetId, tag })
      } catch (err: unknown) {
        // Revert optimistic change
        queue.patchCurrent((prev) => (prev.includes(tag) ? prev : [...prev, tag]))
        const msg = err instanceof Error ? err.message : 'Failed to remove tag'
        toast.error(msg)
      }
    })
  }

  const archiveCurrent = () => {
    if (!current) return
    const asset = current
    const savedIndex = queue.index
    const prevStatus = asset.status
    queue.removeCurrent()
    undoStack.current.push({ type: 'archive', asset, index: savedIndex, prevStatus })
    enqueueWrite(asset.id, async () => {
      await api.patch(`/assets/${asset.id}`, { status: 'archived' })
    })
  }

  const undo = () => {
    const op = undoStack.current.pop()
    if (!op) return
    if (op.type === 'tag-add') {
      enqueueWrite(op.assetId, async () => {
        await api.delete(`/assets/${op.assetId}/tags/${encodeURIComponent(op.tag)}`)
      })
    } else if (op.type === 'tag-remove') {
      enqueueWrite(op.assetId, async () => {
        await api.post(`/assets/${op.assetId}/tags/${encodeURIComponent(op.tag)}`)
      })
    } else {
      enqueueWrite(op.asset.id, async () => {
        await api.patch(`/assets/${op.asset.id}`, { status: op.prevStatus })
      })
      queue.restoreAt(op.index, op.asset)
    }
  }

  const toggleSlot = (_slot: number, keyword: string) => {
    if (!current) return
    if ((current.keywords ?? []).includes(keyword)) removeTag(keyword)
    else applyTag(keyword)
  }

  // Global keyboard layer (suppressed while the TagInput is open — it stops propagation).
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (tagInputOpen) return
      const action = keyToAction(e.key, seekStep)
      if (!action) return
      e.preventDefault()
      switch (action.kind) {
        case 'prev': queue.prev(); break
        case 'next': queue.next(); break
        case 'seek': { const t = player.videoRef.current?.currentTime ?? 0; player.seek(t + action.delta); break }
        case 'togglePlay': player.togglePlay(); break
        case 'slot': break // 1-9 repurposed to TagStampBar hotkeys
        case 'applyAll': Object.values(bindings).forEach((kw) => kw && applyTag(kw)); break
        case 'focusTag': setTagInputOpen(true); break
        case 'filter': /* phase-1: filter UI handled by SlotBar/query; no-op hook point */ break
        case 'archive': archiveCurrent(); break
        case 'undo': undo(); break
        case 'exit': router.push(`/projects/${projectId}`); break
        case 'autoTag': {
          if (current) {
            api.post(`/assets/${current.id}/autotag`, {}).catch((err: unknown) => {
              const msg = err instanceof Error ? err.message : 'Auto-tag failed'
              toast.error(msg)
            })
          }
          break
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tagInputOpen, seekStep, bindings, current, player])

  if (queue.loading) return <div className="p-8 text-text-secondary">Loading…</div>
  if (!current) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3">
        <p className="text-text-secondary">Queue empty.</p>
        <button onClick={() => router.push(`/projects/${projectId}`)}
          className="text-sm text-text-primary underline">Back to project</button>
      </div>
    )
  }

  return (
    <div className="relative flex h-screen flex-col bg-black">
      <div className="flex items-center justify-between px-4 py-2 text-xs text-text-tertiary">
        <span>{queue.index + 1} / {queue.assets.length} — {current.name}</span>
        <ShortcutsHint groups={SORTER_SHORTCUTS} />
      </div>

      <div className="flex flex-1 items-center justify-center">
        <video
          ref={player.videoRef}
          className="max-h-full max-w-full"
          autoPlay
          loop
          controls={false}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 px-4 py-2">
        {(current.keywords ?? []).map((t) => (
          <button key={t} onClick={() => removeTag(t)}
            className="rounded-full border border-border bg-bg-tertiary px-2 py-0.5 text-xs text-text-secondary">
            {t} ✕
          </button>
        ))}
      </div>

      <div className="flex items-center justify-center px-4 pb-4">
        <SlotBar projectId={projectId} currentTags={current.keywords ?? []} onToggleSlot={toggleSlot} />
      </div>

      {current.latest_version?.id && (
        <TagStampBar
          projectId={projectId}
          assetId={current.id}
          versionId={current.latest_version.id}
          durationSeconds={current.latest_version.files?.[0]?.duration_seconds ?? 0}
          canEdit={true}
          enableHotkeys={true}
          getCurrentTime={() => player.videoRef.current?.currentTime ?? 0}
          onSeek={(t) => player.seek(t)}
        />
      )}

      {tagInputOpen && (
        <TagInput
          projectId={projectId}
          appliedTags={current.keywords ?? []}
          recent={recent}
          onApply={(tag) => { applyTag(tag); setTagInputOpen(false) }}
          onClose={() => setTagInputOpen(false)}
        />
      )}
    </div>
  )
}
