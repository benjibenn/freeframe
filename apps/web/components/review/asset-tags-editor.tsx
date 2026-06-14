'use client'

import * as React from 'react'
import useSWR, { mutate as globalMutate } from 'swr'
import { Tag, X } from 'lucide-react'
import { api } from '@/lib/api'

/**
 * Tag editor for the asset review "Fields" tab. Tags are stored in Asset.keywords;
 * each add/remove persists immediately via PUT /assets/{id}/tags. Read-only (chips
 * only, no input) when the viewer can't edit.
 */
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

  // Reset local state when navigating to a different asset.
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

  const persist = async (next: string[]) => {
    const prev = tags
    setTags(next)
    setError('')
    try {
      await api.put(`/assets/${assetId}/tags`, { tags: next })
      globalMutate(`/assets/${assetId}`)
      globalMutate(`/projects/${projectId}/tags`)
    } catch (e: unknown) {
      setTags(prev) // revert on failure
      setError(e instanceof Error ? e.message : 'Failed to save tags')
    }
  }

  const addTag = () => {
    const t = input.trim().toLowerCase().replace(/\s+/g, ' ')
    setInput('')
    if (t && !tags.includes(t)) persist([...tags, t])
  }

  const removeTag = (t: string) => persist(tags.filter((x) => x !== t))

  const suggestions = (projectTags ?? [])
    .map((t) => t.tag)
    .filter((t) => !tags.includes(t))

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
        <>
          <div className="flex gap-2">
            <input
              type="text"
              list={`asset-tag-suggestions-${assetId}`}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addTag()
                }
              }}
              placeholder="Add tag..."
              className="flex h-8 flex-1 rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus transition-colors"
            />
            <button
              type="button"
              onClick={addTag}
              className="rounded-md border border-border bg-bg-secondary px-3 h-8 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
            >
              Add
            </button>
          </div>
          <datalist id={`asset-tag-suggestions-${assetId}`}>
            {suggestions.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </>
      )}

      {error && <p className="text-xs text-status-error">{error}</p>}
    </div>
  )
}
