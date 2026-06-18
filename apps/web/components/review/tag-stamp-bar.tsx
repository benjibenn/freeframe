'use client'

import React, { useEffect, useRef, useState } from 'react'
import { Trash2, Plus, Check, X } from 'lucide-react'
import { cn, formatTimecode } from '@/lib/utils'
import { useTagPalette, type PaletteTag } from '@/hooks/use-tag-palette'
import { useFrameTags } from '@/hooks/use-frame-tags'
import { useToast } from '@/components/shared/toast'

// ─── Props ────────────────────────────────────────────────────────────────────

export interface TagStampBarProps {
  projectId: string
  assetId: string
  versionId: string
  durationSeconds: number
  getCurrentTime: () => number
  onSeek: (time: number) => void
  canEdit: boolean
  enableHotkeys?: boolean
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isEditableTarget(el: Element | null): boolean {
  if (!el) return false
  const tag = (el as HTMLElement).tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
  if ((el as HTMLElement).isContentEditable) return true
  return false
}

function chipStyle(color: string): React.CSSProperties {
  return { backgroundColor: `${color}26`, borderColor: `${color}66`, color }
}

function swatchStyle(color: string): React.CSSProperties {
  return { backgroundColor: color }
}

// ─── Palette chip ─────────────────────────────────────────────────────────────

interface PaletteChipProps {
  tag: PaletteTag
  index: number
  canEdit: boolean
  onStamp: (tag: PaletteTag) => void
  onUpdate: (id: string, patch: { label?: string; color?: string }) => Promise<void>
  onDelete: (id: string) => Promise<void>
}

function PaletteChip({ tag, index, canEdit, onStamp, onUpdate, onDelete }: PaletteChipProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(tag.label)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  const commitEdit = async () => {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== tag.label) {
      await onUpdate(tag.id, { label: trimmed })
    } else {
      setDraft(tag.label)
    }
    setEditing(false)
  }

  const cancelEdit = () => {
    setDraft(tag.label)
    setEditing(false)
  }

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5" style={{ borderColor: `${tag.color}66`, backgroundColor: `${tag.color}26` }}>
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); void commitEdit() }
            if (e.key === 'Escape') cancelEdit()
          }}
          className="w-20 text-[11px] bg-transparent outline-none"
          style={{ color: tag.color }}
        />
        <button onClick={() => void commitEdit()} className="text-text-tertiary hover:text-text-primary transition-colors" title="Save">
          <Check className="h-3 w-3" />
        </button>
        <button onClick={cancelEdit} className="text-text-tertiary hover:text-text-primary transition-colors" title="Cancel">
          <X className="h-3 w-3" />
        </button>
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1 group/chip">
      <button
        onClick={() => onStamp(tag)}
        onDoubleClick={() => canEdit && setEditing(true)}
        title={index < 9 ? `${tag.label} (press ${index + 1})` : tag.label}
        className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide transition-all hover:opacity-80 active:scale-95"
        style={chipStyle(tag.color)}
      >
        {index < 9 && (
          <span className="text-[9px] font-mono opacity-60">{index + 1}</span>
        )}
        <span
          className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
          style={swatchStyle(tag.color)}
        />
        {tag.label}
      </button>
      {canEdit && (
        <button
          onClick={() => void onDelete(tag.id)}
          className="opacity-0 group-hover/chip:opacity-100 transition-opacity p-0.5 rounded hover:bg-bg-hover text-text-tertiary hover:text-status-error"
          title={`Delete "${tag.label}"`}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
    </span>
  )
}

// ─── Add-label inline form ────────────────────────────────────────────────────

const DEFAULT_COLORS = [
  '#f59e0b', '#10b981', '#f43f5e', '#6366f1', '#0ea5e9', '#ec4899', '#84cc16', '#f97316',
]

interface AddLabelFormProps {
  onAdd: (label: string, color: string) => Promise<void>
}

function AddLabelForm({ onAdd }: AddLabelFormProps) {
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [color, setColor] = useState(DEFAULT_COLORS[0])
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus()
  }, [open])

  const submit = async () => {
    const trimmed = label.trim()
    if (!trimmed) return
    setSaving(true)
    try {
      await onAdd(trimmed, color)
      setLabel('')
      setColor(DEFAULT_COLORS[0])
      setOpen(false)
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-0.5 rounded border border-dashed border-border px-1.5 py-0.5 text-[11px] text-text-tertiary hover:text-text-secondary hover:border-border-focus transition-colors"
      >
        <Plus className="h-3 w-3" />
        Add tag
      </button>
    )
  }

  return (
    <span className="inline-flex items-center gap-1 rounded border border-border-focus bg-bg-elevated px-1.5 py-0.5">
      <input
        ref={inputRef}
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); void submit() }
          if (e.key === 'Escape') setOpen(false)
        }}
        placeholder="label"
        className="w-20 text-[11px] bg-transparent outline-none text-text-primary placeholder:text-text-tertiary"
      />
      <div className="flex gap-0.5">
        {DEFAULT_COLORS.map((c) => (
          <button
            key={c}
            onClick={() => setColor(c)}
            className={cn(
              'w-3 h-3 rounded-full border-2 transition-all',
              color === c ? 'border-white scale-110' : 'border-transparent',
            )}
            style={{ backgroundColor: c }}
            title={c}
          />
        ))}
      </div>
      <button
        onClick={() => void submit()}
        disabled={saving || !label.trim()}
        className="text-text-tertiary hover:text-text-primary transition-colors disabled:opacity-40"
        title="Add"
      >
        <Check className="h-3 w-3" />
      </button>
      <button
        onClick={() => setOpen(false)}
        className="text-text-tertiary hover:text-text-primary transition-colors"
        title="Cancel"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  )
}

// ─── Stamped list row ─────────────────────────────────────────────────────────

interface StampedRowProps {
  id: string
  timecodeStart: number
  label: string
  color: string
  canEdit: boolean
  onSeek: (t: number) => void
  onDelete: (id: string) => Promise<void>
}

function StampedRow({ id, timecodeStart, label, color, canEdit, onSeek, onDelete }: StampedRowProps) {
  return (
    <div className="flex items-center gap-2 group/stamp">
      <button
        onClick={() => onSeek(timecodeStart)}
        className="flex items-center gap-2 flex-1 min-w-0 text-left hover:opacity-80 transition-opacity"
      >
        <span
          className="shrink-0 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border"
          style={chipStyle(color)}
        >
          {label}
        </span>
        <span className="font-mono text-[11px] text-text-tertiary">
          {formatTimecode(timecodeStart)}
        </span>
      </button>
      {canEdit && (
        <button
          onClick={() => void onDelete(id)}
          className="shrink-0 opacity-0 group-hover/stamp:opacity-100 transition-opacity p-0.5 rounded hover:bg-bg-hover text-text-tertiary hover:text-status-error"
          title="Delete stamp"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export function TagStampBar({
  projectId,
  assetId,
  versionId,
  durationSeconds,
  getCurrentTime,
  onSeek,
  canEdit,
  enableHotkeys = false,
}: TagStampBarProps) {
  const { palette, createLabel, updateLabel, deleteLabel } = useTagPalette(projectId)
  const { frameTags, createFrameTag, deleteFrameTag } = useFrameTags(assetId, versionId)
  const { toast } = useToast()

  // ── Stamp a palette tag at current time ──────────────────────────────────────
  const stampTag = async (tag: PaletteTag) => {
    const t = getCurrentTime()
    try {
      await createFrameTag(t, tag.label)
      toast(`Stamped "${tag.label}" at ${formatTimecode(t)}`, 'success', 2000)
    } catch {
      toast(`Failed to stamp "${tag.label}"`, 'error')
    }
  }

  // ── Hotkeys 1–9 ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!enableHotkeys || !canEdit) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (isEditableTarget(document.activeElement)) return
      const digit = parseInt(e.key, 10)
      if (isNaN(digit) || digit < 1 || digit > 9) return
      const tag = palette[digit - 1]
      if (!tag) return
      e.preventDefault()
      void stampTag(tag)
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // stampTag intentionally omitted — palette is the real dep; recreating on every render is fine
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enableHotkeys, canEdit, palette])

  // ── Palette label handlers ────────────────────────────────────────────────────
  const handleUpdate = async (id: string, patch: { label?: string; color?: string }) => {
    try {
      await updateLabel(id, patch)
    } catch {
      toast('Failed to update label', 'error')
    }
  }

  const handleDeleteLabel = async (id: string) => {
    try {
      await deleteLabel(id)
    } catch {
      toast('Failed to delete label', 'error')
    }
  }

  const handleAddLabel = async (label: string, color: string) => {
    try {
      await createLabel(label, color)
    } catch {
      toast('Failed to add label', 'error')
    }
  }

  // ── Stamp delete ──────────────────────────────────────────────────────────────
  const handleDeleteStamp = async (id: string) => {
    try {
      await deleteFrameTag(id)
    } catch {
      toast('Failed to delete stamp', 'error')
    }
  }

  // ── Color lookup by label ─────────────────────────────────────────────────────
  const colorForLabel = (label: string): string => {
    return palette.find((p) => p.label === label)?.color ?? '#6366f1'
  }

  // ── Marker strip positions ────────────────────────────────────────────────────
  const timeToPercent = (t: number) =>
    durationSeconds > 0 ? Math.max(0, Math.min(100, (t / durationSeconds) * 100)) : 0

  const sortedStamps = [...frameTags].sort((a, b) => a.timecode_start - b.timecode_start)

  return (
    <div className="px-3 py-2 border-t border-border bg-bg-secondary space-y-2">

      {/* ── Palette chips ── */}
      <div className="flex flex-wrap items-center gap-1.5">
        {palette.map((tag, i) => (
          <PaletteChip
            key={tag.id}
            tag={tag}
            index={i}
            canEdit={canEdit}
            onStamp={stampTag}
            onUpdate={handleUpdate}
            onDelete={handleDeleteLabel}
          />
        ))}
        {canEdit && <AddLabelForm onAdd={handleAddLabel} />}
        {palette.length === 0 && !canEdit && (
          <span className="text-[11px] text-text-tertiary">No tags configured</span>
        )}
      </div>

      {/* ── Marker strip ── */}
      {sortedStamps.length > 0 && durationSeconds > 0 && (
        <div className="relative w-full h-4 rounded-sm bg-bg-tertiary overflow-visible">
          {sortedStamps.map((stamp) => (
            <button
              key={stamp.id}
              title={`${stamp.label} @ ${formatTimecode(stamp.timecode_start)}`}
              onClick={() => onSeek(stamp.timecode_start)}
              className="absolute top-0 -translate-x-1/2 w-2 h-4 flex items-center justify-center hover:scale-110 transition-transform"
              style={{ left: `${timeToPercent(stamp.timecode_start)}%` }}
            >
              <span
                className="block w-1.5 h-4 rounded-[2px] opacity-90"
                style={{ backgroundColor: colorForLabel(stamp.label) }}
              />
            </button>
          ))}
        </div>
      )}

      {/* ── Stamped list ── */}
      {sortedStamps.length > 0 && (
        <div className="flex flex-col gap-1 max-h-36 overflow-y-auto">
          {sortedStamps.map((stamp) => (
            <StampedRow
              key={stamp.id}
              id={stamp.id}
              timecodeStart={stamp.timecode_start}
              label={stamp.label}
              color={colorForLabel(stamp.label)}
              canEdit={canEdit}
              onSeek={onSeek}
              onDelete={handleDeleteStamp}
            />
          ))}
        </div>
      )}
    </div>
  )
}
