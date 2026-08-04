'use client'

import * as React from 'react'
import Link from 'next/link'
import { mutate } from 'swr'
import { FileText, FolderOpen, Users } from 'lucide-react'
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
  dragging,
  onDragStart,
  onDragEnd,
}: {
  brief: BriefTaskItem
  folderFilter: string | null
  dragging: boolean
  onDragStart: () => void
  onDragEnd: () => void
}) {
  const rel = brief.taxonomy_path ? relativePath(brief.taxonomy_path, folderFilter) : ''
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
        href={`/projects/requests/${brief.id}`}
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
          {brief.assignee_name || 'Unowned'}
        </span>
        {brief.editors.length > 0 && (
          <span className="flex items-center gap-1">
            <Users className="h-3 w-3" />
            {brief.editors.map((e) => e.name || e.email).join(', ')}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1.5">
          {(brief.has_brief || brief.has_brief_json) && <FileText className="h-3 w-3" />}
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
}: {
  briefs: BriefTaskItem[]
  stages: TaskStage[]
  folderFilter: string | null
}) {
  const [draggingId, setDraggingId] = React.useState<string | null>(null)
  const [overColumn, setOverColumn] = React.useState<string | null>(null)

  // Unassigned leads: a brief nobody has triaged is the one most needing a look,
  // so it belongs at the start of the pipeline rather than hidden at the end.
  const columns = [
    { id: UNASSIGNED, name: 'Unassigned', color: null as string | null },
    ...stages.map((s) => ({ id: s.id, name: s.name, color: s.color })),
  ]

  const inColumn = (columnId: string) =>
    briefs.filter((b) =>
      columnId === UNASSIGNED ? b.task_stage_id === null : b.task_stage_id === columnId,
    )

  const drop = async (columnId: string) => {
    const id = draggingId
    setDraggingId(null)
    setOverColumn(null)
    if (!id) return
    const target = columnId === UNASSIGNED ? null : columnId
    const current = briefs.find((b) => b.id === id)
    if (!current || current.task_stage_id === target) return
    try {
      await api.patch(`/submission-links/${id}/task-stage`, { task_stage_id: target })
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
