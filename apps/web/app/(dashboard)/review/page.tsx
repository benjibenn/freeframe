'use client'

/**
 * Review queue: editors in the Review stage on a brief, decided one at a time with the
 * keyboard. Platform admins only; GET /review-queue enforces the same.
 */

import { useAuthStore } from '@/stores/auth-store'
import { usePageTitle } from '@/hooks/use-page-title'
import { ReviewQueue } from '@/components/review-queue/review-queue'

export default function ReviewPage() {
  usePageTitle('Review')
  const { user, isLoading } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)

  if (isLoading) return <p className="p-6 text-sm text-text-tertiary">Loading…</p>
  if (!isPlatformAdmin) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold text-text-primary">Review</h1>
        <p className="mt-2 text-sm text-text-secondary">This page is available to admins only.</p>
      </div>
    )
  }
  return <ReviewQueue />
}
