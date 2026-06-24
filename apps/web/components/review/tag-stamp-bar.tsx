'use client'

import React, { useEffect, useRef, useState } from 'react'
import ReactDOM from 'react-dom'
import useSWR from 'swr'
import { Trash2, Check, X, Plus, Square } from 'lucide-react'
import { cn, formatTimecode } from '@/lib/utils'
import { api } from '@/lib/api'
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
  pendingStart: number | null
  onStart: () => void
  onEnd: () => void
  onCancelPending: () => void
  onUpdate: (id: string, patch: { label?: string; color?: string }) => Promise<void>
  onDelete: (id: string) => Promise<void>
}

function PaletteChip({
  tag,
  index,
  canEdit,
  pendingStart,
  onStart,
  onEnd,
  onCancelPending,
  onUpdate,
  onDelete,
}: PaletteChipProps) {
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
    if (trimmed && trimmed !== tag.label) await onUpdate(tag.id, { label: trimmed })
    else setDraft(tag.label)
    setEditing(false)
  }

  const cancelEdit = () => {
    setDraft(tag.label)
    setEditing(false)
  }

  // Renaming mode
  if (editing) {
    return (
      <span
        className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5"
        style={{ borderColor: `${tag.color}66`, backgroundColor: `${tag.color}26` }}
      >
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
        <button onClick={() => void commitEdit()} className="text-text-tertiary hover:text-text-primary transition-colors"><Check className="h-3 w-3" /></button>
        <button onClick={cancelEdit} className="text-text-tertiary hover:text-text-primary transition-colors"><X className="h-3 w-3" /></button>
      </span>
    )
  }

  // Pending state — chip pulses, shows start time, End button appears
  if (pendingStart !== null) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span
          className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide animate-pulse"
          style={chipStyle(tag.color)}
        >
          <span className="inline-block w-1.5 h-1.5 rounded-full shrink-0" style={swatchStyle(tag.color)} />
          {tag.label}
          <span className="font-mono text-[10px] opacity-70 ml-0.5">{formatTimecode(pendingStart)}</span>
        </span>
        <button
          onClick={onEnd}
          title="Mark end here"
          className="inline-flex items-center gap-0.5 rounded border px-1.5 py-0.5 text-[11px] font-semibold transition-all hover:opacity-80 active:scale-95"
          style={{ backgroundColor: `${tag.color}40`, borderColor: `${tag.color}88`, color: tag.color }}
        >
          <Square className="h-2.5 w-2.5 fill-current" />
          End
        </button>
        <button
          onClick={onCancelPending}
          title="Cancel stamp"
          className="p-0.5 rounded hover:bg-bg-hover text-text-tertiary hover:text-status-error transition-colors"
        >
          <X className="h-3 w-3" />
        </button>
      </span>
    )
  }

  // Normal state — clicking chip marks start
  return (
    <span className="inline-flex items-center gap-1 group/chip">
      <button
        onClick={onStart}
        onDoubleClick={() => canEdit && setEditing(true)}
        title={
          index < 9
            ? `Mark start for "${tag.label}" (press ${index + 1})`
            : `Mark start for "${tag.label}"`
        }
        className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide transition-all hover:opacity-80 active:scale-95"
        style={chipStyle(tag.color)}
      >
        {index < 9 && (
          <span className="text-[9px] font-mono opacity-60">{index + 1}</span>
        )}
        <span className="inline-block w-1.5 h-1.5 rounded-full shrink-0" style={swatchStyle(tag.color)} />
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

// ─── Add label form ───────────────────────────────────────────────────────────

const DEFAULT_COLORS = [
  '#f59e0b', '#10b981', '#f43f5e', '#6366f1', '#0ea5e9', '#ec4899', '#84cc16', '#f97316',
]

interface AddLabelFormProps {
  open: boolean
  projectId: string
  onAdd: (label: string, color: string) => Promise<void>
  onClose: () => void
}

function AddLabelForm({ open, projectId, onAdd, onClose }: AddLabelFormProps) {
  const [label, setLabel] = useState('')
  const [color, setColor] = useState(DEFAULT_COLORS[0])
  const [highlight, setHighlight] = useState(0)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [dropdownRect, setDropdownRect] = useState<DOMRect | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: frameLabels } = useSWR<{ label: string; count: number }[]>(
    open ? `/projects/${projectId}/frame-tag-labels` : null,
    (k: string) => api.get<{ label: string; count: number }[]>(k),
  )

  useEffect(() => {
    if (open) {
      setLabel('')
      setColor(DEFAULT_COLORS[0])
      setHighlight(0)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  // Update dropdown portal position
  useEffect(() => {
    if (!dropdownOpen || !inputRef.current) { setDropdownRect(null); return }
    const update = () => { if (inputRef.current) setDropdownRect(inputRef.current.getBoundingClientRect()) }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => { window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true) }
  }, [dropdownOpen])

  const q = label.trim().toLowerCase()
  const suggestions = (frameLabels ?? [])
    .map((l) => l.label)
    .filter((l) => q === '' || l.includes(q))
    .slice(0, 10)

  const commit = async (value?: string) => {
    const trimmed = (value ?? label).trim().toLowerCase()
    if (!trimmed) return
    await onAdd(trimmed, color)
    onClose()
  }

  if (!open) return null

  return (
    <span className="inline-flex items-center gap-1 rounded border border-border-focus bg-bg-elevated px-1.5 py-0.5">
      <input
        ref={inputRef}
        value={label}
        onChange={(e) => { setLabel(e.target.value); setHighlight(0); setDropdownOpen(true) }}
        onFocus={() => setDropdownOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); void commit(suggestions[highlight]) }
          if (e.key === 'Escape') { e.preventDefault(); if (dropdownOpen) { setDropdownOpen(false) } else { onClose() } }
          if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight((h) => Math.min(h + 1, suggestions.length - 1)); setDropdownOpen(true) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)) }
        }}
        placeholder="New label…"
        className="w-24 text-[11px] bg-transparent outline-none text-text-primary placeholder:text-text-tertiary"
      />
      {dropdownOpen && suggestions.length > 0 && dropdownRect && typeof document !== 'undefined' &&
        ReactDOM.createPortal(
          <ul
            style={{ position: 'fixed', top: dropdownRect.bottom + 4, left: dropdownRect.left, minWidth: dropdownRect.width, zIndex: 9999 }}
            className="rounded-md border border-border bg-bg-secondary shadow-lg overflow-hidden"
          >
            {suggestions.map((s, i) => (
              <li key={s}>
                <button
                  type="button"
                  onMouseEnter={() => setHighlight(i)}
                  onMouseDown={(e) => { e.preventDefault(); void commit(s) }}
                  className={`w-full text-left px-3 py-1.5 text-xs ${i === highlight ? 'bg-bg-hover text-text-primary' : 'text-text-secondary'}`}
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>,
          document.body,
        )
      }
      <div className="flex gap-0.5">
        {DEFAULT_COLORS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setColor(c)}
            className={cn(
              'w-3 h-3 rounded-full border-2 transition-all',
              color === c ? 'border-white scale-110' : 'border-transparent',
            )}
            style={{ backgroundColor: c }}
          />
        ))}
      </div>
      <button type="button" onClick={() => void commit()} className="text-text-tertiary hover:text-text-primary transition-colors"><Check className="h-3 w-3" /></button>
      <button type="button" onClick={onClose} className="text-text-tertiary hover:text-text-primary transition-colors"><X className="h-3 w-3" /></button>
    </span>
  )
}

// ─── Stamped list row ─────────────────────────────────────────────────────────

interface StampedRowProps {
  id: string
  timecodeStart: number
  timecodeEnd?: number
  label: string
  color: string
  canEdit: boolean
  onSeek: (t: number) => void
  onDelete: (id: string) => Promise<void>
}

function StampedRow({ id, timecodeStart, timecodeEnd, label, color, canEdit, onSeek, onDelete }: StampedRowProps) {
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
          {timecodeEnd !== undefined
            ? `${formatTimecode(timecodeStart)} → ${formatTimecode(timecodeEnd)}`
            : formatTimecode(timecodeStart)}
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

  const [pendingRange, setPendingRange] = useState<{ label: string; color: string; start: number } | null>(null)
  const [addFormOpen, setAddFormOpen] = useState(false)

  // ── Start stamp for a chip ────────────────────────────────────────────────────
  const handleStart = (tag: PaletteTag) => {
    if (pendingRange) {
      toast(`Finish the "${pendingRange.label}" stamp first`, 'error', 2500)
      return
    }
    const t = getCurrentTime()
    setPendingRange({ label: tag.label, color: tag.color, start: t })
  }

  // ── End stamp for the pending chip ────────────────────────────────────────────
  const handleEnd = async (tag: PaletteTag) => {
    if (!pendingRange || pendingRange.label !== tag.label) return
    const t = getCurrentTime()
    if (t <= pendingRange.start) {
      toast('Seek past the start point first', 'error', 2500)
      return
    }
    try {
      await createFrameTag(pendingRange.start, pendingRange.label, t)
      toast(`"${pendingRange.label}" stamped`, 'success', 2000)
    } catch {
      toast('Failed to save stamp', 'error')
    }
    setPendingRange(null)
  }

  // ── Hotkeys 1–9 and V ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!enableHotkeys || !canEdit) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (isEditableTarget(document.activeElement)) return

      if (e.key === 'Escape') {
        if (pendingRange) { setPendingRange(null); toast('Stamp cancelled', 'info', 1500) }
        if (addFormOpen) setAddFormOpen(false)
        return
      }

      if (e.key === 'v' || e.key === 'V') {
        e.preventDefault()
        setAddFormOpen((o) => !o)
        return
      }

      const digit = parseInt(e.key, 10)
      if (isNaN(digit) || digit < 1 || digit > 9) return
      const tag = palette[digit - 1]
      if (!tag) return
      e.preventDefault()

      if (pendingRange) {
        if (pendingRange.label === tag.label) {
          void handleEnd(tag)
        } else {
          toast(`Finish the "${pendingRange.label}" stamp first`, 'error', 2500)
        }
      } else {
        handleStart(tag)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enableHotkeys, canEdit, palette, pendingRange, addFormOpen])

  // ── Palette label handlers ────────────────────────────────────────────────────
  const handleUpdate = async (id: string, patch: { label?: string; color?: string }) => {
    try { await updateLabel(id, patch) }
    catch { toast('Failed to update label', 'error') }
  }

  const handleDeleteLabel = async (id: string) => {
    try { await deleteLabel(id) }
    catch { toast('Failed to delete label', 'error') }
  }

  const handleAddLabel = async (label: string, color: string) => {
    try { await createLabel(label, color) }
    catch { toast('Failed to add label', 'error') }
  }

  // ── Stamp delete ──────────────────────────────────────────────────────────────
  const handleDeleteStamp = async (id: string) => {
    try { await deleteFrameTag(id) }
    catch { toast('Failed to delete stamp', 'error') }
  }

  // ── Color lookup ──────────────────────────────────────────────────────────────
  const colorForLabel = (label: string): string =>
    palette.find((p) => p.label === label)?.color ?? '#6366f1'

  // ── Marker strip ──────────────────────────────────────────────────────────────
  const timeToPercent = (t: number) =>
    durationSeconds > 0 ? Math.max(0, Math.min(100, (t / durationSeconds) * 100)) : 0

  const sortedStamps = [...frameTags].sort((a, b) => a.timecode_start - b.timecode_start)

  return (
    <div className="px-3 py-2 border-t border-border bg-bg-secondary space-y-2">

      {/* ── Palette chips + Add label ── */}
      <div className="flex flex-wrap items-center gap-1.5">
        {palette.map((tag, i) => (
          <PaletteChip
            key={tag.id}
            tag={tag}
            index={i}
            canEdit={canEdit}
            pendingStart={pendingRange?.label === tag.label ? pendingRange.start : null}
            onStart={() => handleStart(tag)}
            onEnd={() => void handleEnd(tag)}
            onCancelPending={() => setPendingRange(null)}
            onUpdate={handleUpdate}
            onDelete={handleDeleteLabel}
          />
        ))}
        {palette.length === 0 && !canEdit && (
          <span className="text-[11px] text-text-tertiary">No stamps configured</span>
        )}
        {canEdit && (
          addFormOpen ? (
            <AddLabelForm
              open={addFormOpen}
              projectId={projectId}
              onAdd={handleAddLabel}
              onClose={() => setAddFormOpen(false)}
            />
          ) : (
            <button
              onClick={() => setAddFormOpen(true)}
              title="Add label (V)"
              className="inline-flex items-center gap-0.5 rounded border border-dashed border-border px-1.5 py-0.5 text-[11px] text-text-tertiary hover:text-text-secondary hover:border-border-focus transition-colors"
            >
              <Plus className="h-3 w-3" />
              Add label
            </button>
          )
        )}
      </div>

      {/* ── Marker strip ── */}
      {sortedStamps.length > 0 && durationSeconds > 0 && (
        <div className="relative w-full h-4 rounded-sm bg-bg-tertiary overflow-visible">
          {sortedStamps.map((stamp) => {
            const color = colorForLabel(stamp.label)
            if (stamp.timecode_end !== undefined) {
              const startPct = timeToPercent(stamp.timecode_start)
              const endPct = timeToPercent(stamp.timecode_end)
              return (
                <button
                  key={stamp.id}
                  title={`${stamp.label}: ${formatTimecode(stamp.timecode_start)} → ${formatTimecode(stamp.timecode_end)}`}
                  onClick={() => onSeek(stamp.timecode_start)}
                  className="absolute top-0 h-4 hover:opacity-80 transition-opacity rounded-[2px]"
                  style={{
                    left: `${startPct}%`,
                    width: `${Math.max(endPct - startPct, 0.5)}%`,
                    backgroundColor: `${color}cc`,
                    borderLeft: `2px solid ${color}`,
                  }}
                />
              )
            }
            return (
              <button
                key={stamp.id}
                title={`${stamp.label} @ ${formatTimecode(stamp.timecode_start)}`}
                onClick={() => onSeek(stamp.timecode_start)}
                className="absolute top-0 -translate-x-1/2 w-2 h-4 flex items-center justify-center hover:scale-110 transition-transform"
                style={{ left: `${timeToPercent(stamp.timecode_start)}%` }}
              >
                <span
                  className="block w-1.5 h-4 rounded-[2px] opacity-90"
                  style={{ backgroundColor: color }}
                />
              </button>
            )
          })}
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
              timecodeEnd={stamp.timecode_end}
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
