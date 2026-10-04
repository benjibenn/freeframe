'use client'

import * as React from 'react'
import useSWR from 'swr'
import useSWRInfinite from 'swr/infinite'
import { Columns3, List, ListChecks } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { EmptyState } from '@/components/shared/empty-state'
import { usePageTitle } from '@/hooks/use-page-title'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { useAuthStore } from '@/stores/auth-store'
import { ManageStagesDialog } from '@/components/tasks/manage-stages-dialog'
import { BriefRow } from '@/components/tasks/brief-row'
import { PipelineBoard } from '@/components/tasks/pipeline-board'
import { TaskBoardRefreshProvider } from '@/lib/task-board-refresh'
import type { TaskStage, TaskBoardPage, User } from '@/types'

const STAGES_KEY = '/task-stages'
const BOARD_PATH = '/task-board'
const OWNERS_KEY = '/users/assignable'
const PAGE_SIZE = 25

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
  // whose", 'pipeline' answers "where is everything in review".
  const [view, setView] = React.useState<'list' | 'pipeline'>('list')
  const [stageFilter, setStageFilter] = React.useState<string | null>(null)
  const [folderFilter, setFolderFilter] = React.useState<string | null>(null)
  const [typeFilter, setTypeFilter] = React.useState<string>('all')

  const { data: stages } = useSWR<TaskStage[]>(STAGES_KEY, () =>
    api.get<TaskStage[]>(STAGES_KEY),
  )

  // Filters run on the server. The board is paged, so a filter applied here
  // would only ever see the briefs loaded so far. The stage filter belongs to
  // the list view; the pipeline shows every stage as a column.
  const boardQuery = React.useMemo(() => {
    const qp = new URLSearchParams()
    if (view === 'list' && stageFilter) qp.set('stage_id', stageFilter)
    if (folderFilter) qp.set('folder_path', folderFilter)
    return qp.toString()
  }, [view, stageFilter, folderFilter])

  const getBoardKey = React.useCallback(
    (index: number, previous: TaskBoardPage | null) => {
      if (previous && index * PAGE_SIZE >= previous.total) return null
      const qp = new URLSearchParams(boardQuery)
      qp.set('limit', String(PAGE_SIZE))
      qp.set('offset', String(index * PAGE_SIZE))
      return `${BOARD_PATH}?${qp}`
    },
    [boardQuery],
  )

  // Scoped server-side to the briefs this reader owns OR is assigned to make,
  // and already stripped of what they may not see.
  const {
    data: pages,
    size,
    isLoading,
    isValidating,
    setSize,
    mutate: mutateBoard,
  } = useSWRInfinite<TaskBoardPage>(getBoardKey, (key: string) => api.get<TaskBoardPage>(key), {
    // false: a scroll-triggered setSize must not also refetch every earlier
    // page (SWR's default). true: a remount (e.g. navigating back from
    // /review after approving files) must still see fresh stages/counts
    // instead of serving a warm-but-stale cache forever.
    revalidateFirstPage: false,
    revalidateOnMount: true,
  })

  // Back to one page whenever the filters change.
  React.useEffect(() => {
    setSize(1)
  }, [boardQuery, setSize])

  const briefs = React.useMemo(() => (pages ?? []).flatMap((p) => p.items), [pages])
  const total = pages?.[0]?.total ?? 0
  const stageCounts = pages?.[0]?.stage_counts ?? {}
  const reachedEnd = briefs.length >= total
  // isValidating alone also fires on a plain refresh (e.g. refreshBoard() after
  // an edit), which would flash this banner even though no new page is coming.
  // size > pages.length is specifically "a page beyond those already loaded is
  // being fetched" — but pages is undefined on the very first load, where
  // size (1) > 0 would otherwise also be true and show this next to the
  // initial skeleton.
  const loadingMore = isValidating && pages !== undefined && size > pages.length
  const sentinelRef = useInfiniteScroll({
    onLoadMore: () => setSize((s) => s + 1),
    enabled: !reachedEnd && !loadingMore && briefs.length > 0,
  })
  const refreshBoard = React.useCallback(() => {
    void mutateBoard()
  }, [mutateBoard])

  const { data: owners } = useSWR<User[]>(
    isPlatformAdmin ? OWNERS_KEY : null,
    () => api.get<User[]>(OWNERS_KEY),
  )

  const stageList = stages ?? []

  // Counted by the server over the whole filtered set, by the rule the pipeline
  // columns use (an editor's own status, an admin's the brief's). See
  // reader_stage in apps/api/services/board_paging.py.
  const countByStage = (id: string | null) => stageCounts[id ?? 'unassigned'] ?? 0
  const countAll = Object.values(stageCounts).reduce((n, c) => n + c, 0)

  const crumbs = folderFilter
    ? folderFilter.split('/').map((seg, i, all) => ({ label: seg, path: all.slice(0, i + 1).join('/') }))
    : []

  return (
    <TaskBoardRefreshProvider value={refreshBoard}>
    <div className="p-4 sm:p-6 max-w-6xl space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Tasks</h1>
          <p className="mt-1 text-sm text-text-secondary">
            {isPlatformAdmin
              ? 'Every brief and what has been delivered against it. A brief appears here from the moment you create it, so an empty one is visible rather than forgotten.'
              : 'The briefs assigned to you. Move your own status as you work — the brief’s overall status stays with whoever owns it.'}
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
            count={countAll}
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
      ) : briefs.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="Nothing here"
          description={
            folderFilter
              ? `No briefs under ${folderFilter}.`
              : isPlatformAdmin
                ? 'Create a request to start tracking work.'
                : 'Nothing is assigned to you yet.'
          }
        />
      ) : view === 'pipeline' ? (
        <PipelineBoard
          briefs={briefs}
          stages={stageList}
          folderFilter={folderFilter}
          canManage={isPlatformAdmin}
          viewerId={user?.id}
          stageCounts={stageCounts}
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[52rem] table-fixed">
            <thead className="bg-bg-secondary">
              <tr className="text-left text-xs font-medium text-text-tertiary">
                <th className="w-[30%] px-3 py-2.5">Brief</th>
                <th className="w-[22%] px-3 py-2.5">Category</th>
                <th className="w-[20%] px-3 py-2.5">Assigned to</th>
                <th className="w-[8%] px-3 py-2.5 text-center">Files</th>
                <th className="w-[20%] px-3 py-2.5">Status</th>
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
                  viewerId={user?.id}
                  folderFilter={folderFilter}
                  typeFilter={typeFilter}
                  onDrillTo={setFolderFilter}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Infinite scroll: fires when this scrolls into view. */}
      <div ref={sentinelRef} aria-hidden className="h-6" />
      {loadingMore && <p className="text-center text-xs text-text-tertiary">Loading more…</p>}
    </div>
    </TaskBoardRefreshProvider>
  )
}
