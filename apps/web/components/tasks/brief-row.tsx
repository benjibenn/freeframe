'use client'

import * as React from 'react'
import Link from 'next/link'
import { mutate } from 'swr'
import { Banknote, ChevronDown, ChevronRight, FileText, Film, Image as ImageIcon, UserRound } from 'lucide-react'
import { api } from '@/lib/api'
import { stageOf } from '@/lib/brief-stage'
import { cn, formatRelativeTime } from '@/lib/utils'
import type { BriefEditor, BriefTaskItem, TaskItem, TaskStage, User } from '@/types'

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
  canAssign = true,
  viewerId,
  onDrillTo,
}: {
  brief: BriefTaskItem
  stages: TaskStage[]
  owners: User[]
  folderFilter: string | null
  typeFilter: string
  /** Only admins hand a brief to someone. An editor sees who owns it, read-only. */
  canAssign?: boolean
  /** Which editor row belongs to the reader. */
  viewerId?: string
  onDrillTo: (path: string) => void
}) {
  const [expanded, setExpanded] = React.useState(false)
  const [savingOwner, setSavingOwner] = React.useState(false)
  const [assigning, setAssigning] = React.useState(false)

  const assets = brief.assets.filter((a) => typeFilter === 'all' || a.asset_type === typeFilter)
  const rel = brief.taxonomy_path ? relativePath(brief.taxonomy_path, folderFilter) : ''

  // The brief's own status, and the stage of the files under it, belong to whoever
  // the brief sits with: both endpoints 404 for anyone else. Rendering the pickers
  // anyway gives an editor two controls that reject every change they make.
  // Composes with the server blanking the owner for a non-owner — assignee_id is
  // null for exactly the people who would be refused, and their own id for the
  // owner, who keeps both controls.
  const canMoveBrief = canAssign || (!!brief.assignee_id && brief.assignee_id === viewerId)
  // Read-only text must agree with the chip that selected this row, which counts
  // and filters by stageOf (the viewer's own status when they're an editor on the
  // brief) — not brief.task_stage_id. Recomputing that split here is how it drifted
  // before; the live picker below stays on brief.task_stage_id on purpose (see there).
  const readOnlyStageName = stages.find((s) => s.id === stageOf(brief, viewerId, canAssign))?.name
  // An editor's own row is the only one they receive, so the count is always "1"
  // for them — a constant dressed as data. It only carries information on the
  // admin board, where it is the whole roll-up.
  const showEditorCount = canAssign && brief.editors.length > 0

  // Admins land on the brief's settings page; editors land on the submit flow,
  // where their private folder is created. The settings page is admin-only.
  const briefHref = canAssign ? `/projects/requests/${brief.id}` : (brief.submit_url ?? '/tasks')

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

  const assignEditor = async (userId: string) => {
    const who = owners.find((u) => u.id === userId)
    // One-way: the editor's upload folder is created here and there is no
    // unassign, so this asks rather than silently doing it.
    if (!confirm(`Put ${who?.name || who?.email || 'this editor'} on “${brief.title}”?\n\nThis creates their upload folder and cannot be undone.`))
      return
    setAssigning(true)
    try {
      await api.post(`/submission-links/${brief.id}/editors`, { user_id: userId })
      mutate(BOARD_KEY)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to assign that editor')
    } finally {
      setAssigning(false)
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
                href={briefHref}
                className="block truncate text-sm font-medium text-text-primary hover:text-accent"
              >
                {brief.title}
              </Link>
              {(brief.has_brief || brief.has_brief_json || brief.paid_count > 0 || showEditorCount) && (
                <span className="mt-0.5 inline-flex items-center gap-2">
                  {(brief.has_brief || brief.has_brief_json) && (
                    <span className="inline-flex items-center gap-1 text-xs text-text-tertiary">
                      <FileText className="h-3 w-3" />
                      Brief
                    </span>
                  )}
                  {showEditorCount && (
                    <span className="inline-flex items-center gap-1 text-xs text-text-tertiary">
                      <UserRound className="h-3 w-3" />
                      {brief.editors.length}
                    </span>
                  )}
                  {/* Owner bookkeeping: all editors paid, or how many of them are. */}
                  {brief.paid_count > 0 && (
                    <span
                      className={cn(
                        'inline-flex items-center gap-1 text-xs',
                        brief.paid_count === brief.submission_count
                          ? 'text-status-success'
                          : 'text-status-warning',
                      )}
                    >
                      <Banknote className="h-3 w-3" />
                      {brief.paid_count === brief.submission_count
                        ? 'Paid'
                        : `${brief.paid_count}/${brief.submission_count} paid`}
                    </span>
                  )}
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
          {!canAssign ? (
            /* Blank means "not yours to see", not "nobody": the server withholds
               the owner from an editor who is not the owner, so "Unassigned" here
               would be a lie about a brief that does have one. */
            <span className="text-xs text-text-secondary">
              {brief.assignee_name || '—'}
            </span>
          ) : (
          <select
            value={brief.assignee_id ?? ''}
            disabled={savingOwner}
            onChange={(e) => setOwner(e.target.value === '' ? null : e.target.value)}
            className="w-full rounded-md border border-border bg-bg-secondary px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-border-focus disabled:opacity-60 cursor-pointer"
          >
            <option value="">Unassigned</option>
            {owners.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name || u.email}
              </option>
            ))}
          </select>
          )}
        </td>

        <td className="px-3 py-2.5 text-center">
          <span className={cn('text-xs', assets.length === 0 ? 'text-text-tertiary' : 'text-text-secondary')}>
            {assets.length}
          </span>
        </td>

        <td className="px-3 py-2.5">
          {canMoveBrief ? (
            <StagePicker value={brief.task_stage_id} stages={stages} onChange={setStage} />
          ) : (
            <span className="text-xs text-text-tertiary">{readOnlyStageName || 'Not started'}</span>
          )}
        </td>
      </tr>

      {expanded && (
        <>
          {brief.editors.map((e) => (
            <EditorSubRow
              key={e.id}
              briefId={brief.id}
              editor={e}
              stages={stages}
              canMove={canAssign || e.id === viewerId}
            />
          ))}

          {canAssign && (
            <tr className="border-t border-border/50 bg-bg-secondary/20">
              <td colSpan={5} className="px-3 py-2 pl-12">
                <select
                  value=""
                  disabled={assigning}
                  onChange={(e) => {
                    if (e.target.value) assignEditor(e.target.value)
                    e.target.value = ''
                  }}
                  className="rounded-md border border-border bg-bg-secondary px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-border-focus disabled:opacity-60 cursor-pointer"
                >
                  <option value="">Assign an editor…</option>
                  {owners
                    .filter((u) => !brief.editors.some((e) => e.id === u.id))
                    .map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name || u.email}
                      </option>
                    ))}
                </select>
              </td>
            </tr>
          )}

          {assets.length === 0 ? (
            <tr className="border-t border-border/50 bg-bg-secondary/30">
              <td colSpan={5} className="px-3 py-2 pl-12 text-xs text-text-tertiary">
                Nothing submitted yet.
              </td>
            </tr>
          ) : (
            assets.map((a) => (
              <AssetSubRow key={a.asset_id} asset={a} stages={stages} canStage={canMoveBrief} />
            ))
          )}
        </>
      )}
    </>
  )
}

/** A delivered file under its brief. Keeps its own stage: a brief can be "In
 *  Progress" while one of its files is already "Done". */
export function AssetSubRow({
  asset,
  stages,
  canStage,
}: {
  asset: TaskItem
  stages: TaskStage[]
  /** PATCH /assets/{id}/task-stage admits admins and the brief's owner only, so
   *  anyone else gets the stage as text. A boolean rather than the brief itself:
   *  a file sub-row has no other use for one. */
  canStage: boolean
}) {
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
        <span className="text-text-tertiary/70"> · {formatRelativeTime(asset.created_at)}</span>
      </td>
      <td className="px-3 py-2 text-center text-xs text-text-tertiary">
        {asset.run_as_ad ? 'Ad' : ''}
      </td>
      <td className="px-3 py-2">
        {canStage ? (
          <StagePicker value={asset.task_stage_id} stages={stages} onChange={setStage} />
        ) : (
          <span className="text-xs text-text-tertiary">
            {stages.find((s) => s.id === asset.task_stage_id)?.name || 'Not started'}
          </span>
        )}
      </td>
    </tr>
  )
}

/** An editor working this brief, with the status only they (and admins) can
 *  move. Sits above the delivered files because who is on it comes before what
 *  has arrived. */
export function EditorSubRow({
  briefId,
  editor,
  stages,
  canMove,
}: {
  briefId: string
  editor: BriefEditor
  stages: TaskStage[]
  /** Admins move anyone; everyone else only their own row. */
  canMove: boolean
}) {
  const setStage = async (stageId: string | null) => {
    await api.patch(`/submission-links/${briefId}/editors/${editor.id}/task-stage`, {
      task_stage_id: stageId,
    })
    mutate(BOARD_KEY)
  }
  const stageName = stages.find((s) => s.id === editor.task_stage_id)?.name

  return (
    <tr className="border-t border-border/50 bg-bg-secondary/20">
      <td className="px-3 py-2 pl-12">
        <span className="flex items-center gap-2 text-xs text-text-secondary">
          <UserRound className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
          <span className="truncate">{editor.name || editor.email || 'Editor'}</span>
        </span>
      </td>
      <td className="px-3 py-2 text-xs text-text-tertiary">—</td>
      <td className="px-3 py-2 text-xs text-text-tertiary">Editor</td>
      <td className="px-3 py-2 text-center text-xs text-text-tertiary"></td>
      <td className="px-3 py-2">
        {canMove ? (
          <StagePicker value={editor.task_stage_id} stages={stages} onChange={setStage} />
        ) : (
          <span className="text-xs text-text-tertiary">{stageName || 'Not started'}</span>
        )}
      </td>
    </tr>
  )
}
