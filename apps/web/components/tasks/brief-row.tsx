'use client'

import * as React from 'react'
import Link from 'next/link'
import { mutate } from 'swr'
import { ChevronDown, ChevronRight, FileText, Film, Image as ImageIcon } from 'lucide-react'
import { api } from '@/lib/api'
import { cn, formatRelativeTime } from '@/lib/utils'
import type { BriefTaskItem, TaskItem, TaskStage, User } from '@/types'

const BOARD_KEY = '/task-board'

/** Path with the active filter's prefix removed — the breadcrumb already shows
 *  that part, so repeating it in every row is noise. */
export function relativePath(path: string, activeFilter: string | null): string {
  if (!activeFilter) return path
  if (path === activeFilter) return ''
  return path.startsWith(activeFilter + '/') ? path.slice(activeFilter.length + 1) : path
}

function AssetIcon({ type }: { type: string }) {
  return type === 'image' ? (
    <ImageIcon className="h-4 w-4 text-text-tertiary" />
  ) : (
    <Film className="h-4 w-4 text-text-tertiary" />
  )
}

/** Stage dropdown shared by both levels — same task_stages either way, so a
 *  stage name means one thing wherever it appears. */
function StagePicker({
  value,
  stages,
  onChange,
}: {
  value: string | null
  stages: TaskStage[]
  onChange: (stageId: string | null) => Promise<void>
}) {
  const [saving, setSaving] = React.useState(false)
  return (
    <select
      value={value ?? ''}
      disabled={saving}
      onChange={async (e) => {
        const next = e.target.value === '' ? null : e.target.value
        setSaving(true)
        try {
          await onChange(next)
        } catch (err) {
          alert(err instanceof Error ? err.message : 'Failed to update status')
        } finally {
          setSaving(false)
        }
      }}
      className="rounded-md border border-border bg-bg-secondary px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-border-focus disabled:opacity-60 cursor-pointer"
    >
      <option value="">Unassigned</option>
      {stages.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  )
}

export function BriefRow({
  brief,
  stages,
  owners,
  folderFilter,
  typeFilter,
  onDrillTo,
}: {
  brief: BriefTaskItem
  stages: TaskStage[]
  owners: User[]
  folderFilter: string | null
  typeFilter: string
  onDrillTo: (path: string) => void
}) {
  const [expanded, setExpanded] = React.useState(false)
  const [savingOwner, setSavingOwner] = React.useState(false)

  const assets = brief.assets.filter((a) => typeFilter === 'all' || a.asset_type === typeFilter)
  const rel = brief.taxonomy_path ? relativePath(brief.taxonomy_path, folderFilter) : ''

  const setStage = async (stageId: string | null) => {
    await api.patch(`/submission-links/${brief.id}/task-stage`, { task_stage_id: stageId })
    mutate(BOARD_KEY)
  }

  const setOwner = async (userId: string | null) => {
    setSavingOwner(true)
    try {
      await api.patch(`/submission-links/${brief.id}/assignee`, { assignee_id: userId })
      mutate(BOARD_KEY)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to set owner')
    } finally {
      setSavingOwner(false)
    }
  }

  return (
    <>
      <tr className="border-t border-border hover:bg-bg-hover/40">
        <td className="px-3 py-2.5">
          <div className="flex items-start gap-2">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              // Always clickable, even at zero files: collapsing/expanding an empty
              // brief still tells you it is empty, which is the point of the row.
              className="mt-0.5 shrink-0 text-text-tertiary hover:text-text-primary"
              aria-label={expanded ? 'Collapse' : 'Expand'}
            >
              {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </button>
            <div className="min-w-0">
              <Link
                href={`/projects/requests/${brief.id}`}
                className="block truncate text-sm font-medium text-text-primary hover:text-accent"
              >
                {brief.title}
              </Link>
              {(brief.has_brief || brief.has_brief_json) && (
                <span className="mt-0.5 inline-flex items-center gap-1 text-xs text-text-tertiary">
                  <FileText className="h-3 w-3" />
                  Brief
                </span>
              )}
            </div>
          </div>
        </td>

        <td className="px-3 py-2.5">
          {brief.taxonomy_path ? (
            <button
              type="button"
              onClick={() => onDrillTo(brief.taxonomy_path!)}
              title={brief.taxonomy_path}
              className="block w-full truncate text-left text-xs text-accent hover:underline"
            >
              {rel || brief.taxonomy_path}
            </button>
          ) : (
            <span className="text-xs text-text-tertiary">Not filed</span>
          )}
        </td>

        <td className="px-3 py-2.5">
          <select
            value={brief.assignee_id ?? ''}
            disabled={savingOwner}
            onChange={(e) => setOwner(e.target.value === '' ? null : e.target.value)}
            className="w-full rounded-md border border-border bg-bg-secondary px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-border-focus disabled:opacity-60 cursor-pointer"
          >
            <option value="">Unowned</option>
            {owners.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name || u.email}
              </option>
            ))}
          </select>
        </td>

        <td className="px-3 py-2.5">
          {brief.editors.length === 0 ? (
            <span className="text-xs text-text-tertiary">Not accepted</span>
          ) : (
            <span className="text-xs text-text-secondary" title={brief.editors.map((e) => e.email).join(', ')}>
              {brief.editors.map((e) => e.name || e.email).join(', ')}
            </span>
          )}
        </td>

        <td className="px-3 py-2.5 text-center">
          <span className={cn('text-xs', assets.length === 0 ? 'text-text-tertiary' : 'text-text-secondary')}>
            {assets.length}
          </span>
        </td>

        <td className="px-3 py-2.5">
          <StagePicker value={brief.task_stage_id} stages={stages} onChange={setStage} />
        </td>
      </tr>

      {expanded &&
        (assets.length === 0 ? (
          <tr className="border-t border-border/50 bg-bg-secondary/30">
            <td colSpan={6} className="px-3 py-2 pl-12 text-xs text-text-tertiary">
              Nothing submitted yet.
            </td>
          </tr>
        ) : (
          assets.map((a) => <AssetSubRow key={a.asset_id} asset={a} stages={stages} />)
        ))}
    </>
  )
}

/** A delivered file under its brief. Keeps its own stage: a brief can be "In
 *  Progress" while one of its files is already "Done". */
export function AssetSubRow({ asset, stages }: { asset: TaskItem; stages: TaskStage[] }) {
  const setStage = async (stageId: string | null) => {
    await api.patch(`/assets/${asset.asset_id}/task-stage`, { task_stage_id: stageId })
    mutate(BOARD_KEY)
  }

  return (
    <tr className="border-t border-border/50 bg-bg-secondary/30">
      <td className="px-3 py-2 pl-12">
        <Link
          href={`/projects/${asset.project_id}/assets/${asset.asset_id}?from=/tasks`}
          className="flex items-center gap-2 group min-w-0"
        >
          <div className="flex h-7 w-11 shrink-0 items-center justify-center overflow-hidden rounded bg-bg-tertiary">
            {asset.thumbnail_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={asset.thumbnail_url} alt="" className="h-full w-full object-cover" />
            ) : (
              <AssetIcon type={asset.asset_type} />
            )}
          </div>
          <span className="truncate text-xs text-text-secondary group-hover:text-accent">
            {asset.name}
            {asset.latest_version_number && asset.latest_version_number > 1 && (
              <span className="text-text-tertiary"> · v{asset.latest_version_number}</span>
            )}
          </span>
        </Link>
      </td>
      <td className="px-3 py-2 text-xs text-text-tertiary">—</td>
      <td className="px-3 py-2 text-xs text-text-tertiary">
        {asset.submitter_name || asset.submitter_email || '—'}
      </td>
      <td className="px-3 py-2 text-xs text-text-tertiary">
        {formatRelativeTime(asset.created_at)}
      </td>
      <td className="px-3 py-2 text-center text-xs text-text-tertiary">
        {asset.run_as_ad ? 'Ad' : ''}
      </td>
      <td className="px-3 py-2">
        <StagePicker value={asset.task_stage_id} stages={stages} onChange={setStage} />
      </td>
    </tr>
  )
}
