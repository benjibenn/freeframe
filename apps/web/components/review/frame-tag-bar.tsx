'use client'

import React, { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { cn, formatTimecode } from '@/lib/utils'
import { useReviewStore } from '@/stores/review-store'
import { useFrameTags } from '@/hooks/use-frame-tags'
import { useToast } from '@/components/shared/toast'

// ─── Label config ─────────────────────────────────────────────────────────────

const LABELS = ['hook', 'body', 'cta'] as const
type Label = (typeof LABELS)[number]

const LABEL_COLORS: Record<Label, string> = {
  hook: '#f59e0b',
  body: '#10b981',
  cta:  '#f43f5e',
}

const LABEL_BG: Record<Label, string> = {
  hook: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
  body: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
  cta:  'bg-rose-500/20 text-rose-400 border-rose-500/40',
}

function labelColor(label: string): string {
  return LABEL_COLORS[label as Label] ?? '#6366f1'
}

function labelBg(label: string): string {
  return LABEL_BG[label as Label] ?? 'bg-indigo-500/20 text-indigo-400 border-indigo-500/40'
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface FrameTagBarProps {
  assetId: string
  versionId: string
  durationSeconds: number
  canEdit: boolean
}

// ─── Component ────────────────────────────────────────────────────────────────

export function FrameTagBar({ assetId, versionId, durationSeconds, canEdit }: FrameTagBarProps) {
  const { frameTags, createFrameTag, deleteFrameTag } = useFrameTags(assetId, versionId)
  const playheadTime = useReviewStore((s) => s.playheadTime)
  const seekTo = useReviewStore((s) => s.seekTo)
  const { toast } = useToast()

  const [selectedLabel, setSelectedLabel] = useState<Label>('hook')
  const [adding, setAdding] = useState(false)

  const handleAdd = async () => {
    if (adding) return
    setAdding(true)
    try {
      await createFrameTag(playheadTime, selectedLabel)
    } catch {
      toast('Failed to add frame tag', 'error')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteFrameTag(id)
    } catch {
      toast('Failed to delete frame tag', 'error')
    }
  }

  const timeToPercent = (t: number) =>
    durationSeconds > 0 ? Math.max(0, Math.min(100, (t / durationSeconds) * 100)) : 0

  return (
    <div className="px-3 py-2 border-t border-border bg-bg-secondary space-y-2">
      {/* ── Marker strip — hidden when duration is unknown/zero (positions would be meaningless) */}
      {frameTags.length > 0 && durationSeconds > 0 && (
        <div className="relative w-full h-4 rounded-sm bg-bg-tertiary overflow-visible">
          {frameTags.map((tag) => (
            <button
              key={tag.id}
              title={`${tag.label} @ ${formatTimecode(tag.timecode_start)}`}
              onClick={() => seekTo(tag.timecode_start, true)}
              className="absolute top-0 -translate-x-1/2 w-2 h-4 flex items-center justify-center hover:scale-110 transition-transform"
              style={{ left: `${timeToPercent(tag.timecode_start)}%` }}
            >
              <span
                className="block w-1.5 h-4 rounded-[2px] opacity-90"
                style={{ backgroundColor: labelColor(tag.label) }}
              />
            </button>
          ))}
        </div>
      )}

      {/* ── Tag list ── */}
      {frameTags.length > 0 && (
        <div className="flex flex-col gap-1 max-h-32 overflow-y-auto">
          {frameTags.map((tag) => (
            <div
              key={tag.id}
              className="flex items-center gap-2 group/tag"
            >
              <button
                onClick={() => seekTo(tag.timecode_start, true)}
                className="flex items-center gap-2 flex-1 min-w-0 text-left hover:opacity-80 transition-opacity"
              >
                <span
                  className={cn(
                    'shrink-0 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border',
                    labelBg(tag.label),
                  )}
                >
                  {tag.label}
                </span>
                <span className="font-mono text-[11px] text-text-tertiary">
                  {formatTimecode(tag.timecode_start)}
                </span>
              </button>
              {canEdit && (
                <button
                  onClick={() => handleDelete(tag.id)}
                  className="shrink-0 opacity-0 group-hover/tag:opacity-100 transition-opacity p-0.5 rounded hover:bg-bg-hover text-text-tertiary hover:text-status-error"
                  title="Delete tag"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Add control ── */}
      {canEdit && (
        <div className="flex items-center gap-2">
          {/* Label picker */}
          <div className="flex gap-1">
            {LABELS.map((l) => (
              <button
                key={l}
                onClick={() => setSelectedLabel(l)}
                className={cn(
                  'text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border transition-all',
                  selectedLabel === l
                    ? labelBg(l)
                    : 'border-border text-text-tertiary hover:text-text-secondary',
                )}
              >
                {l}
              </button>
            ))}
          </div>
          <button
            onClick={handleAdd}
            disabled={adding}
            className="ml-auto text-[11px] px-2 py-1 rounded bg-bg-tertiary border border-border text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
          >
            + at {formatTimecode(playheadTime)}
          </button>
        </div>
      )}
    </div>
  )
}
