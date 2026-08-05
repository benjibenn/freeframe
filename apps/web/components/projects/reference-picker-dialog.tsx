'use client'

import * as React from 'react'
import useSWR from 'swr'
import { Film, Image as ImageIcon, Loader2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import type { AssetResponse, FolderTreeNode } from '@/types'

export interface ReferenceLibrary {
  project_id: string
  name: string
}

/** Flatten the tree into indented options — same rationale as HomePicker: one
 *  native <select> keeps the whole taxonomy legible and works on touch. */
function flatten(nodes: FolderTreeNode[], depth = 0): { id: string; label: string }[] {
  return nodes.flatMap((n) => [
    { id: n.id, label: `${'  '.repeat(depth)}${n.name}` },
    ...flatten(n.children, depth + 1),
  ])
}

/**
 * Pick media out of the shared References library and attach it to a brief.
 *
 * The server copies the chosen object into the request's own reference prefix
 * rather than pointing at the library's key, so detaching it later (which
 * deletes the underlying object) can never destroy the library asset.
 */
export function ReferencePickerDialog({
  library,
  requestId,
  kind,
  onClose,
  onAttached,
}: {
  library: ReferenceLibrary
  requestId: string
  /** Which array the picked asset lands in — the server decides by asset type,
   *  so this only filters what is offered. */
  kind: 'video' | 'image'
  onClose: () => void
  onAttached: () => void
}) {
  const [folderId, setFolderId] = React.useState<string>('root')
  const [attaching, setAttaching] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const { data: tree } = useSWR<FolderTreeNode[]>(
    `/projects/${library.project_id}/folder-tree`,
    (key: string) => api.get<FolderTreeNode[]>(key),
  )

  const { data: assets, isLoading } = useSWR<AssetResponse[]>(
    `/projects/${library.project_id}/assets?folder_id=${folderId}`,
    (key: string) => api.get<AssetResponse[]>(key),
  )

  // A video brief wants clips and a static brief wants stills; showing both and
  // letting the server reject the wrong one would waste a round trip and a click.
  const wantVideo = kind === 'video'
  const visible = (assets ?? []).filter((a) =>
    wantVideo ? a.asset_type === 'video' : a.asset_type === 'image' || a.asset_type === 'image_carousel',
  )

  const attach = async (assetId: string) => {
    setAttaching(assetId)
    setError(null)
    try {
      await api.post(`/submission-links/${requestId}/reference-from-asset`, { asset_id: assetId })
      onAttached()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not attach that reference')
    } finally {
      setAttaching(null)
    }
  }

  const folders = React.useMemo(() => flatten(tree ?? []), [tree])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-xl border border-border bg-bg-secondary shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <p className="text-sm font-medium text-text-primary">
              {wantVideo ? 'Reference videos' : 'Reference images'} from {library.name}
            </p>
            <p className="text-xs text-text-tertiary">Pick one to attach to this brief.</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-text-tertiary hover:text-text-primary">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="border-b border-border px-5 py-3">
          <select
            value={folderId}
            onChange={(e) => setFolderId(e.target.value)}
            className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
          >
            <option value="root">{library.name} (root)</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {isLoading && (
            <div className="flex justify-center py-10 text-text-tertiary">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          )}

          {!isLoading && visible.length === 0 && (
            <p className="py-10 text-center text-sm text-text-tertiary">
              No {wantVideo ? 'videos' : 'images'} in this folder.
            </p>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {visible.map((asset) => (
              <button
                key={asset.id}
                onClick={() => attach(asset.id)}
                disabled={attaching !== null}
                className="group overflow-hidden rounded-lg border border-border bg-bg-tertiary text-left transition hover:border-accent disabled:opacity-50"
              >
                <div className="flex aspect-video items-center justify-center bg-bg-primary">
                  {asset.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={asset.thumbnail_url} alt="" className="h-full w-full object-cover" />
                  ) : wantVideo ? (
                    <Film className="h-5 w-5 text-text-tertiary" />
                  ) : (
                    <ImageIcon className="h-5 w-5 text-text-tertiary" />
                  )}
                </div>
                <div className="flex items-center gap-1.5 px-2 py-1.5">
                  {attaching === asset.id && <Loader2 className="h-3 w-3 shrink-0 animate-spin" />}
                  <span className="truncate text-xs text-text-secondary">{asset.name}</span>
                </div>
              </button>
            ))}
          </div>

          {error && <p className="mt-4 text-sm text-status-error">{error}</p>}
        </div>

        <div className="flex justify-end border-t border-border px-5 py-3">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  )
}
