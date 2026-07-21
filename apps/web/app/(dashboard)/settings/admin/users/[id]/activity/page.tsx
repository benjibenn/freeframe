'use client'

import * as React from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import useSWR from 'swr'
import { Activity as ActivityIcon, ArrowLeft } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { usePageTitle } from '@/hooks/use-page-title'
import { api } from '@/lib/api'
import { Avatar } from '@/components/shared/avatar'
import { EmptyState } from '@/components/shared/empty-state'
import { ActivityRow } from '@/components/shared/activity-row'
import type { ActivityFeedItem, User } from '@/types'

export default function UserActivityPage() {
  const params = useParams<{ id: string }>()
  const userId = params.id
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)
  const isSuperAdmin = Boolean(user?.is_superadmin)

  usePageTitle('User Activity')

  // /admin/users is superadmin-only server-side; sub-admins skip this fetch
  // and fall back to the plain "User Activity" header below.
  const { data: users } = useSWR<User[]>(
    isSuperAdmin ? '/admin/users' : null,
    () => api.get<User[]>('/admin/users'),
  )
  const targetUser = users?.find((u) => u.id === userId)

  const { data: items, isLoading } = useSWR<ActivityFeedItem[]>(
    isPlatformAdmin && userId ? `/activity?user_id=${userId}` : null,
    () => api.get<ActivityFeedItem[]>(`/activity?user_id=${userId}`),
  )

  if (!isPlatformAdmin) {
    return (
      <div className="p-4 sm:p-6 max-w-3xl">
        <EmptyState
          icon={ActivityIcon}
          title="Admins only"
          description="This page is available to admins and sub-admins."
        />
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 max-w-3xl space-y-6">
      <div>
        <Link
          href="/settings/admin"
          className="inline-flex items-center gap-1 text-xs text-text-tertiary hover:text-text-primary transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to admin
        </Link>
        <div className="mt-2 flex items-center gap-3">
          <Avatar src={targetUser?.avatar_url} name={targetUser?.name} size="sm" />
          <div>
            <h1 className="text-lg font-semibold text-text-primary">
              {targetUser ? `${targetUser.name}'s Activity` : 'User Activity'}
            </h1>
            {targetUser && (
              <p className="text-sm text-text-secondary mt-0.5">{targetUser.email}</p>
            )}
          </div>
        </div>
      </div>

      {isLoading && !items ? (
        <div className="space-y-1">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : !items || items.length === 0 ? (
        <EmptyState
          icon={ActivityIcon}
          title="No activity yet"
          description="This user's uploads, comments, approvals and asset views will show up here."
        />
      ) : (
        <div className="space-y-0.5">
          {items.map((item) => (
            <ActivityRow key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  )
}
