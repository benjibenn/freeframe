'use client'

import * as React from 'react'
import useSWR, { mutate as globalMutate } from 'swr'
import { Tag, X } from 'lucide-react'
import { api } from '@/lib/api'

export function AssetTagsEditor({
  assetId,
  projectId,
  initialTags,
  canEdit,
}: {
  assetId: string
  projectId: string
  initialTags: string[]
  canEdit: boolean
}) {
  const [tags, setTags] = React.useState<string[]>(initialTags)
  const [input, setInput] = React.useState('')
  const [error, setError] = React.useState('')
  const [highlight, setHighlight] = React.useState(0)
  const [dropdownOpen, setDropdownOpen] = React.useState(false)
  const wrapperRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    setTags(initialTags)
    setInput('')
    setError('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId])

  const { data: projectTags } = useSWR<{ tag: string; count: number }[]>(
    canEdit ? `/projects/${projectId}/tags` : null,
    (k: string) => api.get<{ tag: string; count: number }[]>(k),
  )

  // Close dropdown when clicking outside
  React.useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const persist = async (next: string[]) => {
    const prev = tags
    setTags(next)
    setError('')
    try {
      await api.put(`/assets/${assetId}/tags`, { tags: next })
      globalMutate(`/assets/${assetId}`)
      globalMutate(`/projects/${projectId}/tags`)
    } catch (e: unknown) {
      setTags(prev)
      setError(e instanceof Error ? e.message : 'Failed to save tags')
    }
  }

  const addTag = (value?: string) => {
    const t = (value ?? input).trim().toLowerCase().replace(/\s+/g, ' ')
    setInput('')
    setDropdownOpen(false)
    setHighlight(0)
    if (t && !tags.includes(t)) persist([...tags, t])
  }

  const removeTag = (t: string) => persist(tags.filter((x) => x !== t))

  const q = input.trim().toLowerCase()
  const suggestions = (projectTags ?? [])
    .map((t) => t.tag)
    .filter((t) => !tags.includes(t) && (q === '' || t.includes(q)))
    .slice(0, 8)

  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide flex items-center gap-1">
        <Tag className="h-3 w-3" />
        Tags
      </label>

      {tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-1 rounded-full bg-bg-tertiary border border-border px-2 py-0.5 text-xs text-text-secondary"
            >
              {t}
              {canEdit && (
                <button
                  type="button"
                  onClick={() => removeTag(t)}
                  className="text-text-tertiary hover:text-text-primary transition-colors"
                  aria-label={`Remove tag ${t}`}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      ) : (
        !canEdit && <p className="text-xs text-text-tertiary">No tags</p>
      )}

      {canEdit && (
        <div ref={wrapperRef} className="relative flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                setHighlight(0)
                setDropdownOpen(true)
              }}
              onFocus={() => setDropdownOpen(true)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addTag(suggestions[highlight] ?? undefined)
                } else if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  setHighlight((h) => Math.min(h + 1, suggestions.length - 1))
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  setHighlight((h) => Math.max(h - 1, 0))
                } else if (e.key === 'Escape') {
                  setDropdownOpen(false)
                }
              }}
              placeholder="Add tag..."
              className="flex h-8 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus transition-colors"
            />
            {dropdownOpen && suggestions.length > 0 && (
              <ul className="absolute z-50 left-0 right-0 top-full mt-1 rounded-md border border-border bg-bg-secondary shadow-lg overflow-hidden">
                {suggestions.map((t, i) => (
                  <li key={t}>
                    <button
                      type="button"
                      onMouseEnter={() => setHighlight(i)}
                      onMouseDown={(e) => { e.preventDefault(); addTag(t) }}
                      className={`w-full text-left px-3 py-1.5 text-sm ${
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
          <button
            type="button"
            onClick={() => addTag()}
            className="rounded-md border border-border bg-bg-secondary px-3 h-8 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Add
          </button>
        </div>
      )}

      {error && <p className="text-xs text-status-error">{error}</p>}
    </div>
  )
}
