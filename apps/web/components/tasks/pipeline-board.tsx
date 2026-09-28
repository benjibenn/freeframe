'use client'

import * as React from 'react'
import Link from 'next/link'
import { mutate } from 'swr'
import { FileText, FolderOpen } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { relativePath } from './brief-row'
import type { BriefTaskItem, TaskStage } from '@/types'

const BOARD_KEY = '/task-board'
const UNASSIGNED = '__unassigned__'

/** One brief as a card. Deliberately the same unit as a to-do row: the two views
 *  are the same work seen two ways, so a brief must not mean something different
 *  depending on which one you are looking at. */
function BriefCard({
  brief,
  folderFilter,
  canManage,
  dragging,
  onDragStart,
  onDragEnd,
}: {
  brief: BriefTaskItem
  folderFilter: string | null
  /** Admins open the brief's settings page; editors open the submit flow. */
  canManage: boolean
  dragging: boolean
  onDragStart: () => void
  onDragEnd: () => void
}) {
  const rel = brief.taxonomy_path ? relativePath(brief.taxonomy_path, folderFilter) : ''
  const briefHref = canManage ? `/projects/requests/${brief.id}` : (brief.submit_url ?? '/tasks')
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', brief.id)
        onDragStart()
      }}
      onDragEnd={onDragEnd}
      className={cn(
        'cursor-grab rounded-lg border border-border bg-bg-secondary p-2.5 transition-colors hover:border-border-focus active:cursor-grabbing',
        dragging && 'opacity-40',
      )}
    >
      <Link
        href={briefHref}
        className="block truncate text-sm font-medium text-text-primary hover:text-accent"
      >
        {brief.title}
      </Link>

      {rel && (
        <p className="mt-1 flex items-center gap-1 truncate text-xs text-text-tertiary">
          <FolderOpen className="h-3 w-3 shrink-0" />
          {rel}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-tertiary">
        <span
          className={cn(
            'rounded px-1.5 py-0.5',
            brief.assignee_name
              ? 'bg-accent/10 text-accent'
              : 'bg-bg-tertiary text-text-tertiary',
          )}
        >
          {brief.assignee_name || 'Unassigned'}
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          {(brief.has_brief || brief.has_brief_json) && <FileText className="h-3 w-3" />}
          {brief.editors.length > 1 && <span>{brief.editors.length} editors</span>}
          {brief.assets.length > 0 && <span>{brief.assets.length} file{brief.assets.length === 1 ? '' : 's'}</span>}
        </span>
      </div>
    </div>
  )
}

/**
 * The review pipeline: every brief as a card in the stage it is sitting in.
 *
 * Drag moves a brief between stages. It writes through the same
 * PATCH /submission-links/{id}/task-stage the list view uses, against the same
 * task_stages rows the assets use — one pipeline, so "Review" means one thing
 * wherever you read it.
 */
export function PipelineBoard({
  briefs,
  stages,
  folderFilter,
  canManage = true,
  viewerId,
}: {
  briefs: BriefTaskItem[]
  stages: TaskStage[]
  folderFilter: string | null
  /** Admins open the brief's settings page; editors open the submit flow. */
  canManage?: boolean
  /** Which editor row belongs to the reader. */
  viewerId?: string
}) {
  const [draggingId, setDraggingId] = React.useState<string | null>(null)
  const [overColumn, setOverColumn] = React.useState<string | null>(null)

  // Unassigned leads: a brief nobody has triaged is the one most needing a look,
  // so it belongs at the start of the pipeline rather than hidden at the end.
  const columns = [
    { id: UNASSIGNED, name: 'Unassigned', color: null as string | null },
    ...stages.map((s) => ({ id: s.id, name: s.name, color: s.color })),
  ]

  // Which status a card sits in, and which one a drag writes. Admins work the
  // brief's overall status. An editor works their own — a board grouped by a
  // status they cannot move tells them nothing and lets them change nothing.
  // A non-admin who owns the brief but has no editor row of their own falls
  // back to the brief's status: they own it, so it is theirs to move.
  const ownRow = (b: BriefTaskItem) =>
    canManage ? undefined : b.editors.find((e) => e.id === viewerId)

  const stageOf = (b: BriefTaskItem) => {
    const own = ownRow(b)
    return own ? own.task_stage_id : b.task_stage_id
  }

  const inColumn = (columnId: string) =>
    briefs.filter((b) =>
      columnId === UNASSIGNED ? stageOf(b) === null : stageOf(b) === columnId,
    )

  const drop = async (columnId: string) => {
    const id = draggingId
    setDraggingId(null)
    setOverColumn(null)
    if (!id) return
    const target = columnId === UNASSIGNED ? null : columnId
    const current = briefs.find((b) => b.id === id)
    if (!current || stageOf(current) === target) return
    const own = ownRow(current)
    const url = own
      ? `/submission-links/${id}/editors/${own.id}/task-stage`
      : `/submission-links/${id}/task-stage`
    try {
      await api.patch(url, { task_stage_id: target })
      mutate(BOARD_KEY)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Could not move that brief')
    }
  }

  return (
    <div className="overflow-x-auto pb-2">
      <div className="flex gap-3" style={{ minWidth: `${columns.length * 15}rem` }}>
        {columns.map((col) => {
          const items = inColumn(col.id)
          return (
            <div
              key={col.id}
              onDragOver={(e) => {
                e.preventDefault()
                e.dataTransfer.dropEffect = 'move'
                setOverColumn(col.id)
              }}
              onDragLeave={() => setOverColumn((c) => (c === col.id ? null : c))}
              onDrop={(e) => {
                e.preventDefault()
                drop(col.id)
              }}
              className={cn(
                'flex min-w-[14rem] flex-1 flex-col rounded-xl border p-2 transition-colors',
                overColumn === col.id
                  ? 'border-accent bg-accent/5'
                  : 'border-border bg-bg-primary',
              )}
            >
              <div className="mb-2 flex items-center gap-2 px-1">
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: col.color || 'var(--text-tertiary, #6b7280)' }}
                />
                <span className="truncate text-xs font-medium text-text-secondary">{col.name}</span>
                <span className="ml-auto text-xs text-text-tertiary">{items.length}</span>
              </div>

              <div className="flex flex-col gap-2">
                {items.map((b) => (
                  <BriefCard
                    key={b.id}
                    brief={b}
                    folderFilter={folderFilter}
                    canManage={canManage}
                    dragging={draggingId === b.id}
                    onDragStart={() => setDraggingId(b.id)}
                    onDragEnd={() => setDraggingId(null)}
                  />
                ))}
                {items.length === 0 && (
                  <p className="px-1 py-3 text-xs text-text-tertiary">Nothing here.</p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
