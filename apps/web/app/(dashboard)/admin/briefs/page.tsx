'use client'

/**
 * Superadmin brief overview.
 *
 * Deliberately superadmin-only, not sub-admin: the page spans every owner's
 * briefs and every submitter's uploads. The API enforces the same rule; this
 * guard only spares a non-admin the failed request.
 */

import useSWR from 'swr'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth-store'
import {
  BriefOverviewTable,
  type BriefOverviewRow,
} from '@/components/admin/brief-overview-table'

export default function AdminBriefsPage() {
  const { isSuperAdmin, isLoading: authLoading } = useAuthStore()

  const { data, error, isLoading } = useSWR<BriefOverviewRow[]>(
    isSuperAdmin ? '/brief-overview' : null,
    (key: string) => api.get<BriefOverviewRow[]>(key),
  )

  // Wait for the session before judging: rendering "not authorised" while the
  // store is still hydrating would flash a false denial at a real admin.
  if (authLoading) {
    return <p className="p-6 text-sm text-text-tertiary">Loading…</p>
  }

  if (!isSuperAdmin) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold text-text-primary">Brief overview</h1>
        <p className="mt-2 text-sm text-text-secondary">
          This page is available to admins only.
        </p>
      </div>
    )
  }

  const rows = data ?? []
  const totalSubmissions = rows.reduce((n, r) => n + r.submission_count, 0)
  const totalFiles = rows.reduce((n, r) => n + r.asset_count, 0)
  const awaiting = rows.filter((r) => r.submission_count === 0).length

  return (
    <div className="flex flex-col gap-4 p-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Brief overview</h1>
        <p className="mt-1 text-sm text-text-secondary">
          {isLoading
            ? 'Loading…'
            : `${rows.length} brief${rows.length === 1 ? '' : 's'} · ${totalSubmissions} submission${
                totalSubmissions === 1 ? '' : 's'
              } · ${totalFiles} file${totalFiles === 1 ? '' : 's'} · ${awaiting} awaiting work`}
        </p>
      </div>

      {error ? (
        <p className="rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2 text-sm text-status-error">
          Could not load the overview.
        </p>
      ) : (
        <BriefOverviewTable rows={rows} />
      )}
    </div>
  )
}
