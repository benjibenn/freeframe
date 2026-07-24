'use client'

import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import useSWR from 'swr'
import { Tag, ChevronDown, Megaphone } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth-store'
import type { AssetStatus, TaskStage } from '@/types'

const REVIEW_STATUSES: { value: AssetStatus; label: string; dot: string }[] = [
  { value: 'draft', label: 'Draft', dot: 'bg-text-tertiary' },
  { value: 'in_review', label: 'In Review', dot: 'bg-status-warning' },
  { value: 'approved', label: 'Approved', dot: 'bg-status-success' },
  { value: 'rejected', label: 'Rejected', dot: 'bg-status-error' },
  { value: 'archived', label: 'Archived', dot: 'bg-text-tertiary' },
]

const itemClass =
  'flex items-center gap-2.5 mx-1 px-2.5 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer outline-none transition-colors'

/**
 * "Set status" dropdown for the multi-select action bar. Always offers the
 * review-status options (draft…archived). Platform admins additionally get the
 * pipeline-stage options, mirroring the two "status" concepts that exist on the
 * single-asset review page. Opens upward since it lives in the bottom bar.
 */
export function BulkStatusMenu({
  onSetStatus,
  onSetStage,
  onSetRunAsAd,
}: {
  onSetStatus: (status: AssetStatus) => void
  onSetStage?: (stageId: string | null) => void
  onSetRunAsAd?: (runAsAd: boolean) => void
}) {
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)
  const showStages = isPlatformAdmin && Boolean(onSetStage)
  const showRunAsAd = isPlatformAdmin && Boolean(onSetRunAsAd)

  const { data: stages } = useSWR<TaskStage[]>(
    showStages ? '/task-stages' : null,
    () => api.get<TaskStage[]>('/task-stages'),
  )

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button className="inline-flex items-center gap-1.5 rounded-md px-2.5 h-8 text-sm font-medium text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors outline-none">
          <Tag className="h-4 w-4" /> Set status
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          side="top"
          align="end"
          sideOffset={6}
          className="z-[100] min-w-[200px] rounded-xl border border-border bg-bg-elevated shadow-2xl py-1.5 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
        >
          <div className="px-3 py-1 text-2xs font-medium uppercase tracking-wider text-text-tertiary">
            Review status
          </div>
          {REVIEW_STATUSES.map((s) => (
            <DropdownMenu.Item
              key={s.value}
              onSelect={() => onSetStatus(s.value)}
              className={itemClass}
            >
              <span className={cn('h-2 w-2 rounded-full', s.dot)} />
              {s.label}
            </DropdownMenu.Item>
          ))}

          {showStages && (
            <>
              <DropdownMenu.Separator className="my-1 h-px bg-border mx-1" />
              <div className="px-3 py-1 text-2xs font-medium uppercase tracking-wider text-text-tertiary">
                Pipeline stage
              </div>
              <DropdownMenu.Item
                onSelect={() => onSetStage?.(null)}
                className={itemClass}
              >
                <span className="h-2 w-2 rounded-full border border-border" />
                Unassigned
              </DropdownMenu.Item>
              {stages?.map((stage) => (
                <DropdownMenu.Item
                  key={stage.id}
                  onSelect={() => onSetStage?.(stage.id)}
                  className={itemClass}
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: stage.color ?? 'var(--color-text-tertiary)' }}
                  />
                  {stage.name}
                </DropdownMenu.Item>
              ))}
            </>
          )}

          {showRunAsAd && (
            <>
              <DropdownMenu.Separator className="my-1 h-px bg-border mx-1" />
              <div className="px-3 py-1 text-2xs font-medium uppercase tracking-wider text-text-tertiary">
                Ad
              </div>
              <DropdownMenu.Item onSelect={() => onSetRunAsAd?.(true)} className={itemClass}>
                <Megaphone className="h-3.5 w-3.5" />
                Mark as ad
              </DropdownMenu.Item>
              <DropdownMenu.Item onSelect={() => onSetRunAsAd?.(false)} className={itemClass}>
                <Megaphone className="h-3.5 w-3.5 opacity-40" />
                Unmark as ad
              </DropdownMenu.Item>
            </>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
