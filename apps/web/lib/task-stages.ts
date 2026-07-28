'use client'

import * as React from 'react'
import useSWR from 'swr'
import { api } from './api'
import { useAuthStore } from '@/stores/auth-store'
import type { TaskStage } from '@/types'

/** Sort position given to assets with no pipeline stage ("Unassigned").
 *  They sort after every real stage, so untriaged work sits at the end of an
 *  ascending sort rather than leading it. */
const UNASSIGNED_POSITION = Number.MAX_SAFE_INTEGER

/**
 * Pipeline-stage ordering for sorting assets by stage.
 *
 * /task-stages is platform-admin only, so this fetches nothing for other users
 * and reports `available: false` — callers should hide stage sorting entirely
 * rather than render a sort that silently does nothing. The SWR key is shared
 * with BulkStatusMenu, so mounting both costs one request.
 */
export function useTaskStageOrder() {
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)

  const { data: stages } = useSWR<TaskStage[]>(
    isPlatformAdmin ? '/task-stages' : null,
    () => api.get<TaskStage[]>('/task-stages'),
  )

  // Memoised on `stages` so callers can safely list it in a useMemo dependency
  // array without recomputing their sort on every render.
  const positionOf = React.useCallback(
    (stageId: string | null | undefined) => {
      if (!stageId) return UNASSIGNED_POSITION
      const stage = stages?.find((s) => s.id === stageId)
      return stage ? stage.position : UNASSIGNED_POSITION
    },
    [stages],
  )

  return { available: isPlatformAdmin, positionOf }
}
