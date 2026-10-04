'use client'

/**
 * Superadmin brief overview.
 *
 * Deliberately superadmin-only, not sub-admin: the page spans every owner's
 * briefs and every submitter's uploads. The API enforces the same rule; this
 * guard only spares a non-admin the failed request.
 *
 * Paged: 25 briefs at a time, filtered on the server, more on scroll.
 */

import { useEffect, useMemo, useState } from 'react'
import useSWR from 'swr'
import useSWRInfinite from 'swr/infinite'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth-store'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import {
  BriefOverviewTable,
  type BriefOverviewRow,
} from '@/components/admin/brief-overview-table'
import { NO_FILTERS, overviewQuery, type OverviewFilters } from '@/lib/brief-overview-query'
import type { User } from '@/types'

const PAGE_SIZE = 25

type OverviewPage = { items: BriefOverviewRow[]; total: number }

export default function AdminBriefsPage() {
  const { isSuperAdmin, isLoading: authLoading } = useAuthStore()
  const [filters, setFilters] = useState<OverviewFilters>(NO_FILTERS)

  // One request when typing stops, not one per keystroke.
  const [debouncedQuery, setDebouncedQuery] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(filters.query), 300)
    return () => clearTimeout(t)
  }, [filters.query])
  const query = useMemo(() => overviewQuery({ ...filters, query: debouncedQuery }), [filters, debouncedQuery])

  const getKey = (index: number, previous: OverviewPage | null) => {
    if (!isSuperAdmin) return null
    if (previous && index * PAGE_SIZE >= previous.total) return null
    const qp = new URLSearchParams(query)
    qp.set('limit', String(PAGE_SIZE))
    qp.set('offset', String(index * PAGE_SIZE))
    return `/brief-overview?${qp}`
  }
  const { data: pages, error, isLoading, isValidating, setSize } = useSWRInfinite<OverviewPage>(
    getKey,
    (k: string) => api.get<OverviewPage>(k),
    { revalidateFirstPage: false, keepPreviousData: true },
  )
  useEffect(() => {
    setSize(1)
  }, [query, setSize])

  const rows = useMemo(() => (pages ?? []).flatMap((p) => p.items), [pages])
  const total = pages?.[0]?.total ?? 0
  const reachedEnd = rows.length >= total
  const loadingMore = isValidating && (pages?.length ?? 0) > 0
  const loadMoreRef = useInfiniteScroll({
    onLoadMore: () => setSize((s) => s + 1),
    enabled: !reachedEnd && !loadingMore && rows.length > 0,
  })

  // The submitter filter used to list whoever appeared in the loaded rows,
  // which on a paged list is only some of them.
  const { data: people } = useSWR<User[]>(
    isSuperAdmin ? '/users/assignable' : null,
    (k: string) => api.get<User[]>(k),
  )
  const submitters = useMemo(
    () =>
      (people ?? [])
        .map((u) => ({ id: u.id, label: u.name || u.email }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [people],
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

  return (
    <div className="flex flex-col gap-4 p-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Brief overview</h1>
        <p className="mt-1 text-sm text-text-secondary">
          {isLoading ? 'Loading…' : `${total} brief${total === 1 ? '' : 's'}`}
        </p>
      </div>

      {error ? (
        <p className="rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2 text-sm text-status-error">
          Could not load the overview.
        </p>
      ) : (
        <BriefOverviewTable
          rows={rows}
          total={total}
          filters={filters}
          onFiltersChange={setFilters}
          submitters={submitters}
          loadMoreRef={loadMoreRef}
          loadingMore={loadingMore}
        />
      )}
    </div>
  )
}
