'use client'

/**
 * Superadmin reports.
 *
 * Superadmin-only, not sub-admin: the page spans every owner's briefs and every
 * submitter's uploads. The API enforces the same rule; this guard only spares a
 * non-admin the failed request.
 */

import useSWR from 'swr'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth-store'
import { ReportsView, type ReportPayload } from '@/components/admin/reports-view'

export default function AdminReportsPage() {
  const { isSuperAdmin, isLoading: authLoading } = useAuthStore()

  const { data, error, isLoading } = useSWR<ReportPayload>(
    isSuperAdmin ? '/reports' : null,
    (key: string) => api.get<ReportPayload>(key),
  )

  // Wait for the session before judging: rendering "not authorised" while the
  // store is still hydrating would flash a false denial at a real admin.
  if (authLoading) {
    return <p className="p-6 text-sm text-text-tertiary">Loading…</p>
  }

  if (!isSuperAdmin) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-semibold text-text-primary">Reports</h1>
        <p className="mt-2 text-sm text-text-secondary">
          This page is available to admins only.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">Reports</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Submissions and files across every brief and every submitter.
        </p>
      </div>

      {error ? (
        <p className="rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2 text-sm text-status-error">
          Could not load the reports.
        </p>
      ) : isLoading || !data ? (
        <p className="text-sm text-text-tertiary">Loading…</p>
      ) : (
        <ReportsView data={data} />
      )}
    </div>
  )
}
