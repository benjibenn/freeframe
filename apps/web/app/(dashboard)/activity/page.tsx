'use client'

import * as React from 'react'
import useSWR from 'swr'
import { Activity as ActivityIcon } from 'lucide-react'
import { useActivityStore } from '@/stores/activity-store'
import { useAuthStore } from '@/stores/auth-store'
import { usePageTitle } from '@/hooks/use-page-title'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/shared/empty-state'
import { ActivityRow } from '@/components/shared/activity-row'
import type { User } from '@/types'

const CATEGORIES: { label: string; value: string | null }[] = [
  { label: 'All', value: null },
  { label: 'Uploads', value: 'created' },
  { label: 'Comments', value: 'commented,mentioned' },
  { label: 'Approvals', value: 'approved,rejected' },
  { label: 'Shares', value: 'shared' },
  { label: 'Views/Downloads', value: 'asset_clicked,asset_viewed,asset_downloaded' },
]

export default function ActivityPage() {
  usePageTitle('Activity')
  const { user } = useAuthStore()
  const { items, isLoading, hasMore, filter, userId, fetchFeed, loadMore, setFilter, setUserId, markSeen } =
    useActivityStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)
  const isSuperAdmin = Boolean(user?.is_superadmin)

  const { data: users } = useSWR<User[]>(
    isSuperAdmin ? '/admin/users' : null,
    () => api.get<User[]>('/admin/users'),
  )

  React.useEffect(() => {
    if (!isPlatformAdmin) return
    fetchFeed()
    // Viewing the feed clears the alert badge.
    markSeen()
  }, [isPlatformAdmin, fetchFeed, markSeen])

  if (!isPlatformAdmin) {
    return (
      <div className="p-4 sm:p-6 max-w-3xl">
        <EmptyState
          icon={ActivityIcon}
          title="Admins only"
          description="The activity feed is available to admins and sub-admins."
        />
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 max-w-3xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">Activity</h1>
        <p className="text-sm text-text-secondary mt-0.5">
          Everything happening across all projects — uploads, comments, approvals and shares.
          Click any item to open the latest revision and comment.
        </p>
      </div>

      {/* Category filter */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
        <div className="flex flex-wrap items-center gap-1">
          {CATEGORIES.map((cat) => {
            const isActive = filter === cat.value
            return (
              <button
                key={cat.label}
                onClick={() => setFilter(cat.value)}
                className={cn(
                  'rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
                  isActive
                    ? 'bg-bg-hover text-text-primary'
                    : 'text-text-secondary hover:bg-bg-hover/60 hover:text-text-primary',
                )}
              >
                {cat.label}
              </button>
            )
          })}
        </div>

        {users && users.length > 0 && (
          <select
            value={userId ?? ''}
            onChange={(e) => setUserId(e.target.value === '' ? null : e.target.value)}
            className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-[13px] text-text-primary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus cursor-pointer max-w-[12rem]"
          >
            <option value="">All users</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {isLoading && items.length === 0 ? (
        <div className="space-y-1">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={ActivityIcon}
          title="No activity yet"
          description="New uploads, comments and approvals across every project will show up here."
        />
      ) : (
        <>
          <div className="space-y-0.5">
            {items.map((item) => (
              <ActivityRow key={item.id} item={item} />
            ))}
          </div>
          {hasMore && (
            <div className="flex justify-center pt-2">
              <Button variant="ghost" size="sm" onClick={loadMore} disabled={isLoading}>
                {isLoading ? 'Loading…' : 'Load more'}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
