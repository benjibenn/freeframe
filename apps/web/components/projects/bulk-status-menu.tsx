'use client'

import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import useSWR from 'swr'
import { Tag, ChevronDown, Megaphone } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth-store'
import type { TaskStage } from '@/types'

const itemClass =
  'flex items-center gap-2.5 mx-1 px-2.5 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer outline-none transition-colors'

/**
 * "Set status" dropdown. Status means the admin-configurable pipeline stage —
 * the single status concept in the product — so the whole menu is platform-admin
 * only and renders nothing for other users.
 *
 * Used twice: in the multi-select action bar (bottom of the screen, so it opens
 * upward — the default) and in the project toolbar, where the caller passes
 * side="bottom" and its own label, and the selection applies to the whole folder.
 */
export function BulkStatusMenu({
  onSetStage,
  onSetRunAsAd,
  side = 'top',
  label = 'Set status',
  scopeHint,
  triggerClassName,
}: {
  onSetStage: (stageId: string | null) => void
  onSetRunAsAd?: (runAsAd: boolean) => void
  /** Which way the menu opens. Default "top" for the bottom action bar. */
  side?: 'top' | 'bottom'
  /** Trigger text. Default "Set status". */
  label?: string
  /** Replaces the "Pipeline stage" heading, to spell out what the pick applies to. */
  scopeHint?: string
  /** Extra trigger classes, so the toolbar copy can carry the toolbar's border. */
  triggerClassName?: string
}) {
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)
  const showRunAsAd = isPlatformAdmin && Boolean(onSetRunAsAd)

  const { data: stages } = useSWR<TaskStage[]>(
    isPlatformAdmin ? '/task-stages' : null,
    () => api.get<TaskStage[]>('/task-stages'),
  )

  if (!isPlatformAdmin) return null

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-2.5 h-8 text-sm font-medium text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors outline-none',
            triggerClassName,
          )}
        >
          <Tag className="h-4 w-4" /> {label}
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          side={side}
          align="end"
          sideOffset={6}
          className="z-[100] min-w-[200px] rounded-xl border border-border bg-bg-elevated shadow-2xl py-1.5 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
        >
          <div className="px-3 py-1 text-2xs font-medium uppercase tracking-wider text-text-tertiary">
            {scopeHint ?? 'Pipeline stage'}
          </div>
          <DropdownMenu.Item onSelect={() => onSetStage(null)} className={itemClass}>
            <span className="h-2 w-2 rounded-full border border-border" />
            Unassigned
          </DropdownMenu.Item>
          {stages?.map((stage) => (
            <DropdownMenu.Item
              key={stage.id}
              onSelect={() => onSetStage(stage.id)}
              className={itemClass}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: stage.color ?? 'var(--color-text-tertiary)' }}
              />
              {stage.name}
            </DropdownMenu.Item>
          ))}

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
