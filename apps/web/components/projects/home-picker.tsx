'use client'

import * as React from 'react'
import useSWR from 'swr'
import { FolderPlus } from 'lucide-react'
import { api } from '@/lib/api'
import type { FolderTreeNode, Project } from '@/types'

export interface HomeValue {
  projectId: string | null
  folderId: string | null
}

/** Flatten the tree into indented options. A native <select> keeps the whole
 *  taxonomy legible in one glance and works on touch without a custom popover,
 *  which a nested menu of category > store > product does not. */
function flatten(
  nodes: FolderTreeNode[],
  depth = 0,
): { id: string; label: string; depth: number }[] {
  return nodes.flatMap((n) => [
    { id: n.id, label: n.name, depth },
    ...flatten(n.children, depth + 1),
  ])
}

/** Full slash path of a folder within the tree, for the confirmation line. */
function pathOf(nodes: FolderTreeNode[], folderId: string, trail: string[] = []): string | null {
  for (const n of nodes) {
    const here = [...trail, n.name]
    if (n.id === folderId) return here.join('/')
    const found = pathOf(n.children, folderId, here)
    if (found) return found
  }
  return null
}

/**
 * Where a request is filed: a project, and optionally a folder inside it.
 *
 * Replaces the free-text path box. Typing "Phones/Store 1" by hand silently
 * created a new branch on every typo, which is why six of seven briefs ended up
 * with no usable category. Picking from the real tree makes that impossible.
 */
export function HomePicker({
  value,
  onChange,
  autoSelectSingleProject = true,
}: {
  value: HomeValue
  onChange: (next: HomeValue) => void
  /** Pre-select when only one project exists — the common case, and one less click. */
  autoSelectSingleProject?: boolean
}) {
  const { data: projects } = useSWR<Project[]>('/projects', () => api.get<Project[]>('/projects'))

  // Per-editor submission projects are auto-provisioned per person and have no
  // folder tree, so they are never a valid home for a brief.
  const homeable = React.useMemo(
    () => (projects ?? []).filter((p) => !p.submission_link_id),
    [projects],
  )

  const { data: tree } = useSWR<FolderTreeNode[]>(
    value.projectId ? `/projects/${value.projectId}/folder-tree` : null,
    (key: string) => api.get<FolderTreeNode[]>(key),
  )

  React.useEffect(() => {
    if (autoSelectSingleProject && !value.projectId && homeable.length === 1) {
      onChange({ projectId: homeable[0].id, folderId: null })
    }
    // onChange identity is not stable across renders in the calling dialogs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSelectSingleProject, homeable, value.projectId])

  const options = React.useMemo(() => flatten(tree ?? []), [tree])
  const project = homeable.find((p) => p.id === value.projectId)
  const folderPath =
    value.folderId && tree ? pathOf(tree, value.folderId) : null

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-text-secondary">Project</label>
        <select
          value={value.projectId ?? ''}
          onChange={(e) =>
            // Folders never cross projects, so the old folder cannot survive a
            // project change — clearing it is the only correct move.
            onChange({ projectId: e.target.value || null, folderId: null })
          }
          className="w-full rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-border-focus cursor-pointer"
        >
          <option value="">Choose a project…</option>
          {homeable.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-text-secondary">
          Folder <span className="font-normal text-text-tertiary">(category / store / product)</span>
        </label>
        <select
          value={value.folderId ?? ''}
          disabled={!value.projectId}
          onChange={(e) => onChange({ ...value, folderId: e.target.value || null })}
          className="w-full rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-border-focus disabled:opacity-50 cursor-pointer"
        >
          <option value="">
            {project ? `${project.name} (top level)` : 'Pick a project first'}
          </option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {' '.repeat(o.depth * 4)}
              {o.depth > 0 ? '└ ' : ''}
              {o.label}
            </option>
          ))}
        </select>

        {value.projectId && options.length === 0 && (
          <p className="flex items-start gap-1.5 text-xs text-text-tertiary">
            <FolderPlus className="mt-0.5 h-3 w-3 shrink-0" />
            No folders in this project yet. Open it and add your categories, then come back.
          </p>
        )}
        {project && (
          <p className="text-xs text-text-tertiary">
            Files land under{' '}
            <span className="text-text-secondary">
              {project.name}
              {folderPath ? `/${folderPath}` : ''}
            </span>
          </p>
        )}
      </div>
    </div>
  )
}
