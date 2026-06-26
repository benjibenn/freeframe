'use client'

import * as React from 'react'
import Link from 'next/link'
import useSWR, { mutate } from 'swr'
import * as Dialog from '@radix-ui/react-dialog'
import {
  ListChecks,
  Settings2,
  Plus,
  X,
  Trash2,
  ArrowUp,
  ArrowDown,
  Film,
  Star,
} from 'lucide-react'
import { api } from '@/lib/api'
import { cn, formatRelativeTime } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState } from '@/components/shared/empty-state'
import { usePageTitle } from '@/hooks/use-page-title'
import { useAuthStore } from '@/stores/auth-store'
import type { TaskStage, TaskItem } from '@/types'

const STAGES_KEY = '/task-stages'
const TASKS_KEY = '/tasks'

function StageDot({ color }: { color: string | null }) {
  return (
    <span
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ backgroundColor: color || 'var(--text-tertiary, #6b7280)' }}
    />
  )
}

/** Per-row status dropdown. Optimistically updates the cached task list. */
function StageSelect({
  task,
  stages,
}: {
  task: TaskItem
  stages: TaskStage[]
}) {
  const [saving, setSaving] = React.useState(false)

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value
    const task_stage_id = value === '' ? null : value
    setSaving(true)
    // Optimistic update
    mutate(
      TASKS_KEY,
      (current: TaskItem[] | undefined) =>
        current?.map((t) =>
          t.asset_id === task.asset_id ? { ...t, task_stage_id } : t,
        ),
      false,
    )
    try {
      await api.patch(`/assets/${task.asset_id}/task-stage`, { task_stage_id })
    } catch (err) {
      // Roll back on failure
      mutate(TASKS_KEY)
      alert(err instanceof Error ? err.message : 'Failed to update status')
    } finally {
      setSaving(false)
    }
  }

  return (
    <select
      value={task.task_stage_id ?? ''}
      onChange={handleChange}
      disabled={saving}
      className={cn(
        'rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-[13px] text-text-primary',
        'transition-colors focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus',
        'disabled:opacity-60 cursor-pointer',
      )}
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

/** Add / rename / recolour / reorder / remove stages. */
function ManageStagesDialog({ stages }: { stages: TaskStage[] }) {
  const [open, setOpen] = React.useState(false)
  const [newName, setNewName] = React.useState('')
  const [newColor, setNewColor] = React.useState('#3b82f6')
  const [busy, setBusy] = React.useState(false)

  const refresh = () => {
    mutate(STAGES_KEY)
    mutate(TASKS_KEY)
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    setBusy(true)
    try {
      await api.post('/task-stages', { name, color: newColor })
      setNewName('')
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to add stage')
    } finally {
      setBusy(false)
    }
  }

  const handleRename = async (stage: TaskStage, name: string) => {
    if (name.trim() === stage.name || !name.trim()) return
    try {
      await api.patch(`/task-stages/${stage.id}`, { name: name.trim() })
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to rename stage')
    }
  }

  const handleRecolor = async (stage: TaskStage, color: string) => {
    try {
      await api.patch(`/task-stages/${stage.id}`, { color })
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update colour')
    }
  }

  const handleSetDefault = async (stage: TaskStage) => {
    if (stage.is_default) return
    try {
      await api.patch(`/task-stages/${stage.id}`, { is_default: true })
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to set default stage')
    }
  }

  const handleDelete = async (stage: TaskStage) => {
    if (
      !window.confirm(
        `Delete the "${stage.name}" stage? Videos in this stage become Unassigned.`,
      )
    )
      return
    try {
      await api.delete(`/task-stages/${stage.id}`)
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete stage')
    }
  }

  const handleMove = async (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= stages.length) return
    const reordered = [...stages]
    const [moved] = reordered.splice(index, 1)
    reordered.splice(target, 0, moved)
    const ordered_ids = reordered.map((s) => s.id)
    // Optimistic
    mutate(
      STAGES_KEY,
      reordered.map((s, i) => ({ ...s, position: i + 1 })),
      false,
    )
    try {
      await api.post('/task-stages/reorder', { ordered_ids })
      refresh()
    } catch (err) {
      mutate(STAGES_KEY)
      alert(err instanceof Error ? err.message : 'Failed to reorder stages')
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="secondary" size="sm">
          <Settings2 className="h-4 w-4" />
          Manage stages
        </Button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-lg max-h-[85vh] overflow-y-auto -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-bg-secondary p-6 shadow-xl data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95">
          <Dialog.Close className="absolute right-4 top-4 text-text-tertiary hover:text-text-primary transition-colors">
            <X className="h-4 w-4" />
          </Dialog.Close>

          <Dialog.Title className="text-base font-semibold text-text-primary">
            Pipeline stages
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-text-secondary">
            Define the flow each video moves through. Reorder with the arrows. The
            starred stage is where newly uploaded videos start.
          </Dialog.Description>

          <div className="mt-4 space-y-2">
            {stages.map((stage, index) => (
              <div
                key={stage.id}
                className="flex items-center gap-2 rounded-md border border-border bg-bg-primary px-2.5 py-2"
              >
                <div className="flex flex-col">
                  <button
                    onClick={() => handleMove(index, -1)}
                    disabled={index === 0}
                    className="text-text-tertiary hover:text-text-primary disabled:opacity-30"
                    title="Move up"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handleMove(index, 1)}
                    disabled={index === stages.length - 1}
                    className="text-text-tertiary hover:text-text-primary disabled:opacity-30"
                    title="Move down"
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                </div>
                <input
                  type="color"
                  value={stage.color || '#6b7280'}
                  onChange={(e) => handleRecolor(stage, e.target.value)}
                  className="h-7 w-7 shrink-0 cursor-pointer rounded border border-border bg-transparent"
                  title="Stage colour"
                />
                <input
                  defaultValue={stage.name}
                  onBlur={(e) => handleRename(stage, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                  }}
                  className="flex-1 rounded-md border border-transparent bg-transparent px-2 py-1 text-sm text-text-primary hover:border-border focus:border-border-focus focus:outline-none"
                />
                <button
                  onClick={() => handleSetDefault(stage)}
                  className={cn(
                    'transition-colors',
                    stage.is_default
                      ? 'text-amber-400'
                      : 'text-text-tertiary hover:text-amber-400',
                  )}
                  title={stage.is_default ? 'Default stage for new uploads' : 'Make default for new uploads'}
                >
                  <Star className={cn('h-4 w-4', stage.is_default && 'fill-amber-400')} />
                </button>
                <button
                  onClick={() => handleDelete(stage)}
                  className="text-text-tertiary hover:text-status-error transition-colors"
                  title="Delete stage"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            {stages.length === 0 && (
              <p className="text-sm text-text-tertiary py-2">
                No stages yet — add the first one below.
              </p>
            )}
          </div>

          <form onSubmit={handleAdd} className="mt-4 flex items-center gap-2 border-t border-border pt-4">
            <input
              type="color"
              value={newColor}
              onChange={(e) => setNewColor(e.target.value)}
              className="h-9 w-9 shrink-0 cursor-pointer rounded border border-border bg-transparent"
              title="New stage colour"
            />
            <div className="flex-1">
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="New stage name…"
              />
            </div>
            <Button type="submit" size="sm" loading={busy} disabled={!newName.trim()}>
              <Plus className="h-4 w-4" />
              Add
            </Button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export default function TasksPage() {
  usePageTitle('Tasks')
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)
  const [filter, setFilter] = React.useState<string | null>(null)
  const [requestFilter, setRequestFilter] = React.useState<string | null>(null)
  const [pageSize, setPageSize] = React.useState<number>(25)
  const [page, setPage] = React.useState<number>(1)

  const { data: stages } = useSWR<TaskStage[]>(
    isPlatformAdmin ? STAGES_KEY : null,
    () => api.get<TaskStage[]>(STAGES_KEY),
  )
  const { data: tasks, isLoading } = useSWR<TaskItem[]>(
    isPlatformAdmin ? TASKS_KEY : null,
    () => api.get<TaskItem[]>(TASKS_KEY),
  )

  // Remember the chosen page size across visits.
  React.useEffect(() => {
    const saved =
      typeof window !== 'undefined' ? window.localStorage.getItem('tasksPageSize') : null
    if (saved) setPageSize(Number(saved) || 25)
  }, [])
  React.useEffect(() => {
    if (typeof window !== 'undefined')
      window.localStorage.setItem('tasksPageSize', String(pageSize))
  }, [pageSize])
  // Back to page 1 whenever the filters or page size change.
  React.useEffect(() => {
    setPage(1)
  }, [filter, requestFilter, pageSize])

  // Distinct request groupings present in the task list (for the filter dropdown).
  const requestOptions = React.useMemo(() => {
    const m = new Map<string, string>()
    for (const t of tasks ?? []) {
      if (t.request_id) m.set(t.request_id, t.request_title || 'Untitled request')
    }
    return Array.from(m, ([id, title]) => ({ id, title })).sort((a, b) =>
      a.title.localeCompare(b.title),
    )
  }, [tasks])

  if (!isPlatformAdmin) {
    return (
      <div className="p-4 sm:p-6 max-w-3xl">
        <EmptyState
          icon={ListChecks}
          title="Admins only"
          description="The task list is available to admins and sub-admins."
        />
      </div>
    )
  }

  const stageList = stages ?? []

  // Tasks within the chosen request grouping — also drives the stage chip counts.
  const requestScoped = (tasks ?? []).filter((t) =>
    requestFilter === null
      ? true
      : requestFilter === 'none'
        ? !t.request_id
        : t.request_id === requestFilter,
  )
  const countByStage = (id: string | null) =>
    requestScoped.filter((t) => (t.task_stage_id ?? null) === id).length

  const filtered = requestScoped.filter((t) => {
    if (filter === null) return true
    if (filter === 'unassigned') return t.task_stage_id === null
    return t.task_stage_id === filter
  })

  const total = filtered.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const currentPage = Math.min(page, totalPages)
  const startIndex = (currentPage - 1) * pageSize
  const paginated = filtered.slice(startIndex, startIndex + pageSize)

  return (
    <div className="p-4 sm:p-6 max-w-5xl space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Tasks</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            Every submitted video and where it sits in the review pipeline. Change a
            video&rsquo;s status with the dropdown on its row.
          </p>
        </div>
        <ManageStagesDialog stages={stageList} />
      </div>

      {/* Filters: stage chips + request grouping */}
      <div className="flex flex-col gap-3 border-b border-border pb-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-1">
          <FilterChip
            label="All"
            count={requestScoped.length}
            active={filter === null}
            onClick={() => setFilter(null)}
          />
          {stageList.map((s) => (
            <FilterChip
              key={s.id}
              label={s.name}
              color={s.color}
              count={countByStage(s.id)}
              active={filter === s.id}
              onClick={() => setFilter(s.id)}
            />
          ))}
          <FilterChip
            label="Unassigned"
            count={countByStage(null)}
            active={filter === 'unassigned'}
            onClick={() => setFilter('unassigned')}
          />
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <label className="text-xs text-text-tertiary whitespace-nowrap">Request</label>
          <select
            value={requestFilter ?? ''}
            onChange={(e) =>
              setRequestFilter(e.target.value === '' ? null : e.target.value)
            }
            className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-[13px] text-text-primary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus cursor-pointer max-w-[16rem]"
          >
            <option value="">All requests</option>
            {requestOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.title}
              </option>
            ))}
            <option value="none">No request</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No videos here"
          description="Submitted videos will appear here so you can move them through the pipeline."
        />
      ) : (
        <div className="space-y-3">
        <div className="rounded-lg border border-border bg-bg-secondary overflow-hidden">
          <table className="w-full table-fixed text-sm">
            <thead>
              <tr className="border-b border-border bg-bg-tertiary">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">Video</th>
                <th className="w-40 px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">Submitter</th>
                <th className="w-28 px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">Submitted</th>
                <th className="w-40 px-4 py-2.5 text-left text-xs font-medium text-text-tertiary">Status</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((t) => (
                <tr
                  key={t.asset_id}
                  className="border-b border-border last:border-0 hover:bg-bg-tertiary transition-colors"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/projects/${t.project_id}/assets/${t.asset_id}?from=/tasks`}
                      className="flex items-center gap-3 group"
                    >
                      <div className="flex h-10 w-16 shrink-0 items-center justify-center overflow-hidden rounded bg-bg-tertiary">
                        {t.thumbnail_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={t.thumbnail_url} alt="" className="h-full w-full object-cover" />
                        ) : (
                          <Film className="h-4 w-4 text-text-tertiary" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-text-primary truncate group-hover:text-accent">
                          {t.name}
                          {t.latest_version_number && t.latest_version_number > 1 && (
                            <span className="text-text-tertiary font-normal"> · v{t.latest_version_number}</span>
                          )}
                        </p>
                        {t.project_name && (
                          <p className="text-xs text-text-tertiary truncate">{t.project_name}</p>
                        )}
                      </div>
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <p className="text-sm text-text-primary truncate">{t.submitter_name || '—'}</p>
                    {t.submitter_email && (
                      <p className="text-xs text-text-tertiary truncate">{t.submitter_email}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-text-tertiary whitespace-nowrap">
                    {formatRelativeTime(t.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <StageSelect task={t} stages={stageList} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-text-tertiary">
            Showing {total === 0 ? 0 : startIndex + 1}–{Math.min(startIndex + pageSize, total)} of {total}
          </p>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs text-text-tertiary whitespace-nowrap">Per page</label>
              <select
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                className="rounded-md border border-border bg-bg-secondary px-2 py-1.5 text-[13px] text-text-primary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus cursor-pointer"
              >
                {[10, 25, 50, 100].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="secondary"
                size="sm"
                disabled={currentPage <= 1}
                onClick={() => setPage(currentPage - 1)}
              >
                Prev
              </Button>
              <span className="px-1 text-xs text-text-tertiary whitespace-nowrap">
                Page {currentPage} / {totalPages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={currentPage >= totalPages}
                onClick={() => setPage(currentPage + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
        </div>
      )}
    </div>
  )
}

function FilterChip({
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
        'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
        active
          ? 'bg-bg-hover text-text-primary'
          : 'text-text-secondary hover:bg-bg-hover/60 hover:text-text-primary',
      )}
    >
      {color !== undefined && <StageDot color={color ?? null} />}
      {label}
      <span className="text-text-tertiary">{count}</span>
    </button>
  )
}
