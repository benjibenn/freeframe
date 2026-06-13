'use client'

import * as React from 'react'
import Link from 'next/link'
import {
  Activity as ActivityIcon,
  Upload,
  MessageSquare,
  CheckCircle,
  XCircle,
  Share2,
  UserCheck,
  AtSign,
  ChevronRight,
} from 'lucide-react'
import { useActivityStore } from '@/stores/activity-store'
import { useAuthStore } from '@/stores/auth-store'
import { usePageTitle } from '@/hooks/use-page-title'
import { formatRelativeTime, cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Avatar } from '@/components/shared/avatar'
import { EmptyState } from '@/components/shared/empty-state'
import type { ActivityFeedItem } from '@/types'

const actionIcons: Record<string, React.ElementType> = {
  created: Upload,
  commented: MessageSquare,
  mentioned: AtSign,
  shared: Share2,
  assigned: UserCheck,
  approved: CheckCircle,
  rejected: XCircle,
}

function actionPhrase(item: ActivityFeedItem): string {
  switch (item.action) {
    case 'created':
      return item.payload?.is_new_asset === false ? 'uploaded a new version of' : 'uploaded'
    case 'commented':
      return 'commented on'
    case 'mentioned':
      return 'mentioned someone on'
    case 'shared':
      return 'shared'
    case 'assigned':
      return 'assigned'
    case 'approved':
      return 'approved'
    case 'rejected':
      return 'requested changes on'
    default:
      return item.action
  }
}

function ActivityRow({ item }: { item: ActivityFeedItem }) {
  const Icon = actionIcons[item.action] ?? ActivityIcon
  const actor = item.actor?.name ?? 'Someone'
  const asset = item.asset_name ?? 'an asset'
  const href = item.deep_link ?? '#'
  const version =
    item.latest_version_number && item.latest_version_number > 1
      ? `v${item.latest_version_number}`
      : null

  return (
    <Link
      href={href}
      className={cn(
        'group flex items-start gap-3 rounded-lg px-4 py-3 transition-colors hover:bg-bg-hover',
      )}
    >
      <div className="relative shrink-0">
        <Avatar src={item.actor?.avatar_url ?? undefined} name={item.actor?.name} size="sm" />
        <span
          className={cn(
            'absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full ring-2 ring-bg-primary',
            item.action === 'approved' && 'bg-status-success/20 text-status-success',
            item.action === 'rejected' && 'bg-status-error/20 text-status-error',
            item.action === 'commented' && 'bg-accent-muted text-accent',
            item.action === 'created' && 'bg-bg-tertiary text-text-secondary',
            !['approved', 'rejected', 'commented', 'created'].includes(item.action) &&
              'bg-bg-tertiary text-text-secondary',
          )}
        >
          <Icon className="h-2.5 w-2.5" />
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-0.5 min-w-0">
        <p className="text-sm text-text-primary">
          <span className="font-medium">{actor}</span>{' '}
          <span className="text-text-secondary">{actionPhrase(item)}</span>{' '}
          <span className="font-medium">{asset}</span>
          {version && <span className="text-text-tertiary"> · {version}</span>}
        </p>
        {item.comment_preview && (
          <p className="truncate text-xs text-text-secondary italic">
            “{item.comment_preview}”
          </p>
        )}
        <p className="text-xs text-text-tertiary">
          {item.project_name ? `${item.project_name} · ` : ''}
          {formatRelativeTime(item.created_at)}
        </p>
      </div>

      <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-text-tertiary opacity-0 transition-opacity group-hover:opacity-100" />
    </Link>
  )
}

const CATEGORIES: { label: string; value: string | null }[] = [
  { label: 'All', value: null },
  { label: 'Uploads', value: 'created' },
  { label: 'Comments', value: 'commented,mentioned' },
  { label: 'Approvals', value: 'approved,rejected' },
  { label: 'Shares', value: 'shared' },
]

export default function ActivityPage() {
  usePageTitle('Activity')
  const { user } = useAuthStore()
  const { items, isLoading, hasMore, filter, fetchFeed, loadMore, setFilter, markSeen } =
    useActivityStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)

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
      <div className="flex flex-wrap items-center gap-1 border-b border-border pb-3">
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
