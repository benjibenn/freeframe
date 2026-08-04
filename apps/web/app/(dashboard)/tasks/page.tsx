'use client'

import * as React from 'react'
import useSWR from 'swr'
import { Columns3, List, ListChecks } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { EmptyState } from '@/components/shared/empty-state'
import { usePageTitle } from '@/hooks/use-page-title'
import { useAuthStore } from '@/stores/auth-store'
import { ManageStagesDialog } from '@/components/tasks/manage-stages-dialog'
import { BriefRow, AssetSubRow, relativePath } from '@/components/tasks/brief-row'
import { PipelineBoard } from '@/components/tasks/pipeline-board'
import type { TaskStage, TaskBoardResponse, User } from '@/types'

const STAGES_KEY = '/task-stages'
const BOARD_KEY = '/task-board'
const OWNERS_KEY = '/users/assignable'

function StageChip({
  label,
  count,
  active,
  color,
  onClick,
}: {
  label: string
  count: number
  active: boolean
  color?: string | null
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors',
        active
          ? 'border-border-focus bg-bg-secondary text-text-primary'
          : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-bg-hover',
      )}
    >
      {color !== undefined && (
        <span
          className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ backgroundColor: color || 'var(--text-tertiary, #6b7280)' }}
        />
      )}
      {label}
      <span className="text-text-tertiary">{count}</span>
    </button>
  )
}

export default function TasksPage() {
  usePageTitle('Tasks')
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)

  // Two readings of the same briefs: 'list' answers "what is on my plate and
  // whose", 'pipeline' answers "where is everything in review". Neither is a
  // subset of the other, so both stay.
  const [view, setView] = React.useState<'list' | 'pipeline'>('list')
  const [stageFilter, setStageFilter] = React.useState<string | null>(null)
  const [folderFilter, setFolderFilter] = React.useState<string | null>(null)
  const [typeFilter, setTypeFilter] = React.useState<string>('all')

  const { data: stages } = useSWR<TaskStage[]>(STAGES_KEY, () =>
    api.get<TaskStage[]>(STAGES_KEY),
  )
  // The board is scoped server-side: an editor's response contains only the
  // briefs they own, so there is nothing here to filter or hide client-side.
  const { data: board, isLoading } = useSWR<TaskBoardResponse>(BOARD_KEY, () =>
    api.get<TaskBoardResponse>(BOARD_KEY),
  )
  const { data: owners } = useSWR<User[]>(
    isPlatformAdmin ? OWNERS_KEY : null,
    () => api.get<User[]>(OWNERS_KEY),
  )

  const stageList = stages ?? []
  const allBriefs = board?.briefs ?? []
  const allUnbriefed = board?.unbriefed ?? []

  // Folder filter applies to a brief's own path — an un-started brief has no
  // assets to match through, and it is the row most worth keeping visible.
  const inFolder = (path: string | null) =>
    folderFilter === null ||
    (path !== null && (path === folderFilter || path.startsWith(folderFilter + '/')))

  const folderBriefs = allBriefs.filter((b) => inFolder(b.taxonomy_path))
  const countByStage = (id: string | null) =>
    folderBriefs.filter((b) => (b.task_stage_id ?? null) === id).length

  const briefs = folderBriefs.filter((b) => {
    if (view === 'pipeline') return true
    if (stageFilter === null) return true
    if (stageFilter === 'unassigned') return b.task_stage_id === null
    return b.task_stage_id === stageFilter
  })

  const unbriefed = allUnbriefed
    .filter((a) => inFolder(a.folder_path))
    .filter((a) => typeFilter === 'all' || a.asset_type === typeFilter)

  const crumbs = folderFilter
    ? folderFilter.split('/').map((seg, i, all) => ({ label: seg, path: all.slice(0, i + 1).join('/') }))
    : []

  return (
    <div className="p-4 sm:p-6 max-w-6xl space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Tasks</h1>
          <p className="mt-1 text-sm text-text-secondary">
            {isPlatformAdmin
              ? 'Every brief and what has been delivered against it. A brief appears here from the moment you create it, so an empty one is visible rather than forgotten.'
              : 'The briefs assigned to you. Move one along as you work on it.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-border p-0.5">
            <button
              onClick={() => setView('list')}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors',
                view === 'list'
                  ? 'bg-bg-secondary text-text-primary'
                  : 'text-text-tertiary hover:text-text-primary',
              )}
            >
              <List className="h-3.5 w-3.5" />
              To-do
            </button>
            <button
              onClick={() => setView('pipeline')}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors',
                view === 'pipeline'
                  ? 'bg-bg-secondary text-text-primary'
                  : 'text-text-tertiary hover:text-text-primary',
              )}
            >
              <Columns3 className="h-3.5 w-3.5" />
              Pipeline
            </button>
          </div>
          {isPlatformAdmin && <ManageStagesDialog stages={stageList} />}
        </div>
      </div>

      {view === 'list' && (
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-1">
          <StageChip
            label="All"
            count={folderBriefs.length}
            active={stageFilter === null}
            onClick={() => setStageFilter(null)}
          />
          {stageList.map((s) => (
            <StageChip
              key={s.id}
              label={s.name}
              color={s.color}
              count={countByStage(s.id)}
              active={stageFilter === s.id}
              onClick={() => setStageFilter(s.id)}
            />
          ))}
          <StageChip
            label="Unassigned"
            count={countByStage(null)}
            active={stageFilter === 'unassigned'}
            onClick={() => setStageFilter('unassigned')}
          />
        </div>

        <div className="ml-auto flex items-center gap-2 shrink-0">
          <label className="text-xs text-text-tertiary whitespace-nowrap">Files</label>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-[13px] text-text-primary focus:outline-none focus:border-border-focus cursor-pointer"
          >
            <option value="all">All types</option>
            <option value="video">Video</option>
            <option value="image">Image</option>
          </select>
        </div>
      </div>
      )}

      {crumbs.length > 0 && (
        <nav className="flex items-center flex-wrap gap-1 text-xs" aria-label="Taxonomy filter">
          <button onClick={() => setFolderFilter(null)} className="text-accent hover:underline">
            All folders
          </button>
          {crumbs.map((c, i) => (
            <span key={c.path} className="flex items-center gap-1">
              <span className="text-text-tertiary">/</span>
              <button
                onClick={() => setFolderFilter(c.path)}
                className={
                  i === crumbs.length - 1
                    ? 'text-text-primary font-medium'
                    : 'text-accent hover:underline'
                }
              >
                {c.label}
              </button>
            </span>
          ))}
        </nav>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : briefs.length === 0 && unbriefed.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="Nothing here"
          description={
            folderFilter
              ? `No briefs or files under ${folderFilter}.`
              : isPlatformAdmin
                ? 'Create a request to start tracking work.'
                : 'Nothing is assigned to you yet. An admin puts a brief on your desk by setting you as its owner.'
          }
        />
      ) : view === 'pipeline' ? (
        <PipelineBoard briefs={briefs} stages={stageList} folderFilter={folderFilter} />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[52rem]">
            <thead className="bg-bg-secondary">
              <tr className="text-left text-xs font-medium text-text-tertiary">
                <th className="w-[26%] px-3 py-2.5">Brief</th>
                <th className="w-[18%] px-3 py-2.5">Category</th>
                <th className="w-[15%] px-3 py-2.5">Owner</th>
                <th className="w-[18%] px-3 py-2.5">Editor</th>
                <th className="w-[8%] px-3 py-2.5 text-center">Files</th>
                <th className="w-[15%] px-3 py-2.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {briefs.map((b) => (
                <BriefRow
                  key={b.id}
                  brief={b}
                  stages={stageList}
                  owners={owners ?? []}
                  canAssign={isPlatformAdmin}
                  folderFilter={folderFilter}
                  typeFilter={typeFilter}
                  onDrillTo={setFolderFilter}
                />
              ))}

              {unbriefed.length > 0 && (
                <>
                  <tr className="border-t border-border bg-bg-secondary/60">
                    <td colSpan={6} className="px-3 py-2 text-xs font-medium text-text-tertiary">
                      Uploaded directly — no brief ({unbriefed.length})
                    </td>
                  </tr>
                  {unbriefed.map((a) => (
                    <AssetSubRow key={a.asset_id} asset={a} stages={stageList} />
                  ))}
                </>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
