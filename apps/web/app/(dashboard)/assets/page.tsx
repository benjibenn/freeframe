'use client'

import * as React from 'react'
import useSWRInfinite from 'swr/infinite'
import { FolderOpen, Film, Image as ImageIcon, Music, Clock, Users, AtSign, UserCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { AssetGrid } from '@/components/projects/asset-grid'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import type { Asset } from '@/types'

const PAGE_SIZE = 24

type AssetFilter = 'all' | 'owned' | 'shared' | 'mentioned' | 'assigned' | 'due_soon'

interface FilterOption {
  value: AssetFilter
  label: string
  icon: React.ElementType
  apiParam: string | null
}

const FILTERS: FilterOption[] = [
  { value: 'all', label: 'All Assets', icon: FolderOpen, apiParam: null },
  { value: 'owned', label: 'Owned', icon: UserCheck, apiParam: 'owned' },
  { value: 'shared', label: 'Shared with me', icon: Users, apiParam: 'shared' },
  { value: 'mentioned', label: 'Mentioned', icon: AtSign, apiParam: 'mentioned' },
  { value: 'assigned', label: 'Assigned', icon: UserCheck, apiParam: 'assigned' },
  { value: 'due_soon', label: 'Due soon', icon: Clock, apiParam: 'due_soon' },
]

function buildKey(filter: AssetFilter): string {
  const opt = FILTERS.find((f) => f.value === filter)!
  return opt.apiParam ? `/me/assets?filter=${opt.apiParam}` : '/me/assets'
}

export default function AssetsPage() {
  const [activeFilter, setActiveFilter] = React.useState<AssetFilter>('all')

  // Infinite scroll: each SWR "page" is one paginated /me/assets request. The key
  // carries the active filter, so switching filters resets to a single page below.
  const getKey = React.useCallback(
    (index: number, previous: Asset[] | null) => {
      if (previous && previous.length < PAGE_SIZE) return null
      const base = buildKey(activeFilter)
      const sep = base.includes('?') ? '&' : '?'
      return `${base}${sep}skip=${index * PAGE_SIZE}&limit=${PAGE_SIZE}`
    },
    [activeFilter],
  )

  const { data: pages, isLoading, isValidating, setSize, mutate } = useSWRInfinite<Asset[]>(
    getKey,
    (key: string) => api.get<Asset[]>(key),
    { revalidateFirstPage: false, keepPreviousData: true },
  )

  const assets = React.useMemo(() => pages?.flat() ?? [], [pages])
  const lastPage = pages?.[pages.length - 1]
  const reachedEnd = lastPage ? lastPage.length < PAGE_SIZE : false
  const loadingMore = isValidating && (pages?.length ?? 0) > 0

  React.useEffect(() => { setSize(1) }, [activeFilter, setSize])

  const sentinelRef = useInfiniteScroll({
    onLoadMore: () => setSize((s) => s + 1),
    enabled: !reachedEnd && !loadingMore && assets.length > 0,
  })

  return (
    <div className="flex h-full">
      {/* Left filter sidebar */}
      <div className="w-[140px] sm:w-[200px] shrink-0 border-r border-border p-3 space-y-1">
        <p className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-text-tertiary">
          Filters
        </p>
        {FILTERS.map((f) => {
          const Icon = f.icon
          const isActive = activeFilter === f.value
          return (
            <button
              key={f.value}
              onClick={() => setActiveFilter(f.value)}
              className={cn(
                'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors',
                isActive
                  ? 'bg-bg-hover text-text-primary font-medium'
                  : 'text-text-secondary hover:bg-bg-hover/50 hover:text-text-primary',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
              <span className="truncate">{f.label}</span>
            </button>
          )
        })}
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-5">
        {/* Header row */}
        <div className="mb-5">
          <h1 className="text-base font-semibold text-text-primary">
            {FILTERS.find((f) => f.value === activeFilter)?.label ?? 'My Assets'}
          </h1>
          <p className="mt-0.5 text-[13px] text-text-tertiary">
            {activeFilter === 'all'
              ? 'All assets accessible to you across projects.'
              : activeFilter === 'owned'
                ? 'Assets you created.'
                : activeFilter === 'shared'
                  ? 'Assets shared with you by others.'
                  : activeFilter === 'due_soon'
                    ? 'Assets due within the next 7 days.'
                    : 'Filtered assets.'}
          </p>
        </div>

        {/* Asset grid */}
        <AssetGrid
          assets={assets ?? []}
          projectId=""
          isLoading={isLoading}
          onBulkStatus={async (assetIds, status) => {
            await api.patch(`/assets/bulk/status`, { asset_ids: assetIds, status })
            mutate()
          }}
          onBulkStage={async (assetIds, stageId) => {
            await api.patch(`/assets/bulk/stage`, { asset_ids: assetIds, task_stage_id: stageId })
            mutate()
          }}
          onBulkRunAsAd={async (assetIds, runAsAd) => {
            await api.patch(`/assets/bulk/run-as-ad`, { asset_ids: assetIds, run_as_ad: runAsAd })
            mutate()
          }}
        />

        {/* Empty state */}
        {!isLoading && assets?.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-bg-tertiary">
              <FolderOpen className="h-7 w-7 text-text-tertiary" strokeWidth={1.5} />
            </div>
            <div className="text-center space-y-1">
              <p className="text-sm font-medium text-text-primary">No assets found</p>
              <p className="text-[13px] text-text-tertiary max-w-[280px]">
                {activeFilter === 'all'
                  ? 'Assets from your projects will appear here once uploaded.'
                  : 'No assets match the current filter.'}
              </p>
            </div>
          </div>
        )}

        {/* Infinite scroll: auto-loads the next page of assets as it nears view. */}
        {!reachedEnd && assets.length > 0 && (
          <div ref={sentinelRef} className="h-10 flex items-center justify-center">
            {loadingMore && (
              <span className="text-xs text-text-tertiary">Loading more…</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
