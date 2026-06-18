'use client'

import * as React from 'react'
import useSWR from 'swr'
import { api } from '@/lib/api'
import { mergeSuggestions, type TagCount } from '@/lib/sorter/suggestions'

interface TagInputProps {
  projectId: string
  appliedTags: string[]
  recent: string[]
  onApply: (tag: string) => void
  onClose: () => void
}

export function TagInput({ projectId, appliedTags, recent, onApply, onClose }: TagInputProps) {
  const [query, setQuery] = React.useState('')
  const [highlight, setHighlight] = React.useState(0)
  const ref = React.useRef<HTMLInputElement>(null)

  React.useEffect(() => { ref.current?.focus() }, [])

  const { data: projectTags } = useSWR<TagCount[]>(
    `/projects/${projectId}/tags`,
    (k: string) => api.get<TagCount[]>(k),
  )

  const suggestions = mergeSuggestions(projectTags ?? [], recent, query, appliedTags)

  const apply = (tag: string) => {
    const t = tag.trim().toLowerCase().replace(/\s+/g, ' ')
    if (t) onApply(t)
    setQuery('')
    setHighlight(0)
  }

  return (
    <div
      className="absolute bottom-20 left-1/2 -translate-x-1/2 w-80 rounded-lg border border-border bg-bg-secondary p-2 shadow-xl"
      onKeyDown={(e) => e.stopPropagation()} // don't trigger global sorter keys
    >
      <input
        ref={ref}
        value={query}
        onChange={(e) => { setQuery(e.target.value); setHighlight(0) }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            apply(suggestions[highlight] ?? query)
          } else if (e.key === 'ArrowDown') {
            e.preventDefault()
            setHighlight((h) => Math.min(h + 1, suggestions.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setHighlight((h) => Math.max(h - 1, 0))
          } else if (e.key === 'Escape') {
            e.preventDefault()
            onClose()
          }
        }}
        placeholder="Tag…"
        className="w-full h-9 rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary focus:outline-none focus:border-border-focus"
      />
      {suggestions.length > 0 && (
        <ul className="mt-1 max-h-48 overflow-auto">
          {suggestions.map((t, i) => (
            <li key={t}>
              <button
                type="button"
                onMouseEnter={() => setHighlight(i)}
                onClick={() => apply(t)}
                className={`w-full text-left px-3 py-1.5 text-sm rounded ${
                  i === highlight ? 'bg-bg-hover text-text-primary' : 'text-text-secondary'
                }`}
              >
                {t}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
