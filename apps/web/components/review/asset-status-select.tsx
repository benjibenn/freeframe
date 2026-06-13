'use client'

import * as React from 'react'
import useSWR from 'swr'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import type { TaskStage } from '@/types'

/**
 * Status dropdown for the review/view page. Platform admins (superadmin /
 * sub-admin) can move a video through the task pipeline straight from the
 * asset's Fields panel. Renders nothing for non-admins.
 */
export function AssetStatusSelect({
  assetId,
  taskStageId,
  label = true,
}: {
  assetId: string
  taskStageId: string | null
  label?: boolean
}) {
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)
  const [current, setCurrent] = React.useState<string | null>(taskStageId ?? null)
  const [saving, setSaving] = React.useState(false)

  React.useEffect(() => {
    setCurrent(taskStageId ?? null)
  }, [taskStageId])

  const { data: stages } = useSWR<TaskStage[]>(
    isPlatformAdmin ? '/task-stages' : null,
    () => api.get<TaskStage[]>('/task-stages'),
  )

  if (!isPlatformAdmin) return null

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value
    const id = value === '' ? null : value
    const prev = current
    setCurrent(id)
    setSaving(true)
    try {
      await api.patch(`/assets/${assetId}/task-stage`, { task_stage_id: id })
    } catch (err) {
      setCurrent(prev ?? null)
      alert(err instanceof Error ? err.message : 'Failed to update status')
    } finally {
      setSaving(false)
    }
  }

  const select = (
    <select
      value={current ?? ''}
      onChange={handleChange}
      disabled={saving}
      className={cn(
        'rounded-md border border-border bg-bg-secondary px-2 py-1 text-xs text-text-primary',
        'transition-colors focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus',
        'disabled:opacity-60 cursor-pointer',
      )}
    >
      <option value="">Unassigned</option>
      {stages?.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  )

  if (!label) return select

  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-text-tertiary">Status</span>
      {select}
    </div>
  )
}
