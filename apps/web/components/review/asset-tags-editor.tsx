'use client'

import * as React from 'react'
import ReactDOM from 'react-dom'
import useSWR, { mutate as globalMutate } from 'swr'
import { Tag, X, Sparkles } from 'lucide-react'
import { api } from '@/lib/api'
import { useTagPalette } from '@/hooks/use-tag-palette'
import { useSSE } from '@/hooks/use-sse'
import { useAuthStore } from '@/stores/auth-store'
import { useToast } from '@/components/shared/toast'

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
  const [dropdownRect, setDropdownRect] = React.useState<DOMRect | null>(null)
  const wrapperRef = React.useRef<HTMLDivElement>(null)
  const inputRef = React.useRef<HTMLInputElement>(null)

  const user = useAuthStore((s) => s.user)
  const isPlatformAdmin = !!(user?.is_superadmin || user?.is_subadmin)
  const showAutotag = canEdit && isPlatformAdmin
  const toast = useToast()

  React.useEffect(() => {
    setTags(initialTags)
    setInput('')
    setError('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId])

  // AI tags land asynchronously via the worker; merge them into local state when
  // the event arrives so they show without a refresh (local `tags` otherwise only
  // re-syncs on assetId change and would go stale after auto-tagging).
  useSSE(showAutotag ? projectId : null, {
    onAutotagComplete: ({ asset_id, applied }) => {
      if (asset_id !== assetId || applied.length === 0) return
      setTags((prev) => Array.from(new Set([...prev, ...applied])))
      globalMutate(`/assets/${assetId}`)
      globalMutate(`/projects/${projectId}/tags`)
      toast.success(`AI added ${applied.length} tag${applied.length > 1 ? 's' : ''}`)
    },
  })

  const runAutotag = () => {
    api.post(`/assets/${assetId}/autotag`, {})
      .then(() => toast.success('AI tagging queued'))
      .catch((e: unknown) => toast.error(e instanceof Error ? e.message : 'AI tagging failed'))
  }

  const { data: projectTags } = useSWR<{ tag: string; count: number }[]>(
    canEdit ? `/projects/${projectId}/tags` : null,
    (k: string) => api.get<{ tag: string; count: number }[]>(k),
  )
  const { palette } = useTagPalette(canEdit ? projectId : null)

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

  // Track input position for the portal-rendered dropdown (escapes overflow:hidden parents)
  React.useEffect(() => {
    if (!dropdownOpen || !inputRef.current) { setDropdownRect(null); return }
    const update = () => {
      if (inputRef.current) setDropdownRect(inputRef.current.getBoundingClientRect())
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [dropdownOpen])

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
  const sortedProjectTags = [...(projectTags ?? [])].sort((a, b) => b.count - a.count)
  const paletteLabels = palette.map((p) => p.label)
  const pool = Array.from(new Set([
    ...sortedProjectTags.map((t) => t.tag),
    ...paletteLabels,
  ])).filter((t) => !tags.includes(t))
  const suggestions = (q === '' ? pool : pool.filter((t) => t.includes(q))).slice(0, 10)

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide flex items-center gap-1">
          <Tag className="h-3 w-3" />
          Tags
        </label>
        {showAutotag && (
          <button
            type="button"
            onClick={runAutotag}
            title="AI auto-tag this asset from its analysis (palette labels only)"
            className="inline-flex items-center gap-1 rounded-md border border-border bg-bg-secondary px-2 h-6 text-[11px] font-medium text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            <Sparkles className="h-3 w-3" />
            AI tag
          </button>
        )}
      </div>

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
        <div ref={wrapperRef} className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => { setInput(e.target.value); setHighlight(0); setDropdownOpen(true) }}
            onFocus={() => setDropdownOpen(true)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); addTag(suggestions[highlight] ?? undefined) }
              else if (e.key === 'ArrowDown') { e.preventDefault(); setDropdownOpen(true); setHighlight((h) => Math.min(h + 1, suggestions.length - 1)) }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setDropdownOpen(true); setHighlight((h) => Math.max(h - 1, 0)) }
              else if (e.key === 'Escape') { setDropdownOpen(false) }
            }}
            data-field-shortcut="tags"
            placeholder="Add tag..."
            className="flex h-8 flex-1 rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus transition-colors"
          />
          <button
            type="button"
            onClick={() => addTag()}
            className="rounded-md border border-border bg-bg-secondary px-3 h-8 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Add
          </button>
          {/* Portal: escapes overflow:hidden parents in the sidebar */}
          {dropdownOpen && suggestions.length > 0 && dropdownRect && typeof document !== 'undefined' &&
            ReactDOM.createPortal(
              <ul
                style={{ position: 'fixed', top: dropdownRect.bottom + 4, left: dropdownRect.left, width: dropdownRect.width, zIndex: 9999 }}
                className="rounded-md border border-border bg-bg-secondary shadow-lg overflow-hidden"
              >
                {suggestions.map((t, i) => (
                  <li key={t}>
                    <button
                      type="button"
                      onMouseEnter={() => setHighlight(i)}
                      onMouseDown={(e) => { e.preventDefault(); addTag(t) }}
                      className={`w-full text-left px-3 py-1.5 text-sm ${i === highlight ? 'bg-bg-hover text-text-primary' : 'text-text-secondary'}`}
                    >
                      {t}
                    </button>
                  </li>
                ))}
              </ul>,
              document.body,
            )
          }
        </div>
      )}

      {error && <p className="text-xs text-status-error">{error}</p>}
    </div>
  )
}
