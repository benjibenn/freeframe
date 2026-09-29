'use client'

/**
 * Superadmin playbook: coverage and brief grouping for one brand folder.
 *
 * Reads the same /brief-overview payload as the brief overview page, so file
 * counts are live — nothing to sync. Superadmin-only for the same reason: it
 * spans every owner's briefs. The API enforces it; this guard only spares a
 * non-admin the failed request.
 */

import useSWR from 'swr'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth-store'
import { PlaybookView } from '@/components/admin/playbook-view'
import type { PlaybookSource } from '@/lib/playbook'

export default function AdminPlaybookPage() {
  const { isSuperAdmin, isLoading: authLoading } = useAuthStore()

  const { data, error, isLoading } = useSWR<PlaybookSource[]>(
    isSuperAdmin ? '/brief-overview' : null,
    (key: string) => api.get<PlaybookSource[]>(key),
  )

  if (authLoading) {
    return <p className="p-6 text-sm text-text-tertiary">Loading…</p>
  }

  if (!isSuperAdmin) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold text-text-primary">Playbook</h1>
        <p className="mt-2 text-sm text-text-secondary">This page is available to admins only.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold text-text-primary">Playbook</h1>
      {error ? (
        <p className="rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2 text-sm text-status-error">
          Could not load briefs.
        </p>
      ) : isLoading ? (
        <p className="text-sm text-text-tertiary">Loading…</p>
      ) : (
        <PlaybookView rows={data ?? []} origin={typeof window !== 'undefined' ? window.location.origin : ''} />
      )}
    </div>
  )
}
