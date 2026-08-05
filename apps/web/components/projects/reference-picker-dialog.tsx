'use client'

import * as React from 'react'
import useSWR from 'swr'
import { Film, Image as ImageIcon, Loader2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import type { AssetResponse, FolderTreeNode, Project } from '@/types'

export interface ReferenceLibrary {
  project_id: string
  name: string
}

/** An asset chosen in the picker but not yet attached — what a create form holds
 *  until the request exists and can be attached to. */
export interface PickedReference {
  id: string
  name: string
  kind: 'video' | 'image'
}

/** Flatten the tree into indented options — same rationale as HomePicker: one
 *  native <select> keeps the whole taxonomy legible and works on touch. */
function flatten(nodes: FolderTreeNode[], depth = 0): { id: string; label: string }[] {
  return nodes.flatMap((n) => [
    { id: n.id, label: `${'  '.repeat(depth)}${n.name}`, },
    ...flatten(n.children, depth + 1),
  ])
}

/**
 * Pick existing Freeframe media to use as a brief reference.
 *
 * Browses any project the user can read, not one designated library: the server
 * permission-checks each attach, and a user could download and re-upload
 * anything they can see anyway. The configured References project, when there
 * is one, is only used to preselect the most likely project.
 */
export function ReferencePickerDialog({
  library,
  kind,
  onClose,
  onPick,
}: {
  /** Preselects this project when set. Purely a convenience. */
  library?: ReferenceLibrary | null
  kind: 'video' | 'image'
  onClose: () => void
  /** Return true to close the dialog. Existing requests attach immediately;
   *  create forms stash the pick until the request exists. */
  onPick: (asset: AssetResponse) => Promise<void> | void
}) {
  const wantVideo = kind === 'video'

  const { data: projects } = useSWR<Project[]>('/projects', () => api.get<Project[]>('/projects'))

  const [projectId, setProjectId] = React.useState<string>(library?.project_id ?? '')
  const [folderId, setFolderId] = React.useState<string>('root')
  const [busyId, setBusyId] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  // Per-editor submission projects hold submitted work, not reusable reference
  // material, and have no folder tree — the same exclusion HomePicker makes.
  const browsable = React.useMemo(
    () => (projects ?? []).filter((p) => !p.submission_link_id),
    [projects],
  )

  React.useEffect(() => {
    if (!projectId && browsable.length) setProjectId(library?.project_id ?? browsable[0].id)
  }, [browsable, library?.project_id, projectId])

  const { data: tree } = useSWR<FolderTreeNode[]>(
    projectId ? `/projects/${projectId}/folder-tree` : null,
    (key: string) => api.get<FolderTreeNode[]>(key),
  )

  const { data: assets, isLoading } = useSWR<AssetResponse[]>(
    projectId ? `/projects/${projectId}/assets?folder_id=${folderId}` : null,
    (key: string) => api.get<AssetResponse[]>(key),
  )

  // A video brief wants clips and a static brief wants stills; offering both and
  // letting the server sort it out would waste a round trip and a click.
  const visible = (assets ?? []).filter((a) =>
    wantVideo ? a.asset_type === 'video' : a.asset_type === 'image' || a.asset_type === 'image_carousel',
  )

  const choose = async (asset: AssetResponse) => {
    setBusyId(asset.id)
    setError(null)
    try {
      await onPick(asset)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not use that reference')
    } finally {
      setBusyId(null)
    }
  }

  const folders = React.useMemo(() => flatten(tree ?? []), [tree])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-xl border border-border bg-bg-secondary shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <p className="text-sm font-medium text-text-primary">
              Use an existing {wantVideo ? 'video' : 'image'}
            </p>
            <p className="text-xs text-text-tertiary">Pick from any project you can access.</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-text-tertiary hover:text-text-primary">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid gap-2 border-b border-border px-5 py-3 sm:grid-cols-2">
          <select
            value={projectId}
            onChange={(e) => {
              setProjectId(e.target.value)
              setFolderId('root') // folders belong to a project; keeping one would 404
            }}
            className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
          >
            {browsable.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select
            value={folderId}
            onChange={(e) => setFolderId(e.target.value)}
            className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
          >
            <option value="root">All / root</option>
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
                onClick={() => choose(asset)}
                disabled={busyId !== null}
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
                  {busyId === asset.id && <Loader2 className="h-3 w-3 shrink-0 animate-spin" />}
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
