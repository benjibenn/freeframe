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
  MousePointerClick,
  Eye,
  Download,
} from 'lucide-react'
import { formatRelativeTime, cn } from '@/lib/utils'
import { Avatar } from '@/components/shared/avatar'
import type { ActivityFeedItem } from '@/types'

export const actionIcons: Record<string, React.ElementType> = {
  created: Upload,
  commented: MessageSquare,
  mentioned: AtSign,
  shared: Share2,
  assigned: UserCheck,
  approved: CheckCircle,
  rejected: XCircle,
  asset_clicked: MousePointerClick,
  asset_viewed: Eye,
  asset_downloaded: Download,
}

export function actionPhrase(item: ActivityFeedItem): string {
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
    case 'asset_clicked':
      return 'opened'
    case 'asset_viewed':
      return 'viewed'
    case 'asset_downloaded':
      return 'downloaded'
    default:
      return item.action
  }
}

export function ActivityRow({ item }: { item: ActivityFeedItem }) {
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
