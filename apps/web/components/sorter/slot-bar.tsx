'use client'

import * as React from 'react'
import { api } from '@/lib/api'
import { useSorterStore, getBindings } from '@/stores/sorter-store'

interface SlotBarProps {
  projectId: string
  currentTags: string[]
  onToggleSlot: (slot: number, keyword: string) => void
}

export function SlotBar({ projectId, currentTags, onToggleSlot }: SlotBarProps) {
  const bindings = useSorterStore((s) => getBindings(s, projectId))
  const setBinding = useSorterStore((s) => s.setBinding)
  const applied = new Set(currentTags)

  const rebind = (slot: number) => {
    const kw = window.prompt(`Keyword for slot ${slot}:`, bindings[slot] ?? '')
    if (kw && kw.trim()) setBinding(projectId, slot, kw)
  }

  const makeCollection = async (keyword: string) => {
    // Smart collection that filters on this keyword (backend _apply_smart_filter
    // matches assets whose keywords JSONB contains it) — turns the slot into a
    // browsable view of everything sorted into it.
    await api.post(`/projects/${projectId}/collections`, {
      name: keyword,
      filter_rules: { keywords: [keyword] },
    })
  }

  return (
    <div className="flex gap-1.5">
      {Array.from({ length: 9 }, (_, i) => i + 1).map((slot) => {
        const kw = bindings[slot]
        const isApplied = kw ? applied.has(kw) : false
        return (
          <div key={slot} className="flex flex-col items-center">
            <button
              type="button"
              disabled={!kw}
              onClick={() => kw && onToggleSlot(slot, kw)}
              className={`h-10 w-16 rounded-md border text-xs transition-colors ${
                isApplied
                  ? 'border-border-focus bg-bg-hover text-text-primary'
                  : 'border-border bg-bg-secondary text-text-secondary'
              } ${!kw ? 'opacity-40' : ''}`}
            >
              <span className="block font-mono">{slot}</span>
              <span className="block truncate px-1">{kw ?? '—'}</span>
            </button>
            <div className="mt-0.5 flex gap-1">
              <button type="button" onClick={() => rebind(slot)}
                className="text-[10px] text-text-tertiary hover:text-text-primary">edit</button>
              {kw && (
                <button type="button" onClick={() => makeCollection(kw)}
                  className="text-[10px] text-text-tertiary hover:text-text-primary">+coll</button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
