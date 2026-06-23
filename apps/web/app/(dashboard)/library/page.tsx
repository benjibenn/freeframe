'use client'

import * as React from 'react'
import Link from 'next/link'
import useSWR, { mutate } from 'swr'
import * as Dialog from '@radix-ui/react-dialog'
import { Library, Film, Search, X, Plus, Trash2, ChevronDown, FolderOpen, Users } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/shared/empty-state'
import { usePageTitle } from '@/hooks/use-page-title'
import { useAuthStore } from '@/stores/auth-store'

// ─── Types ────────────────────────────────────────────────────────────────────

interface LibraryAssetItem {
  id: string
  name: string
  asset_type: string
  project_id: string
  project_name: string
  folder_id: string | null
  folder_name: string | null
  keywords: string[] | null
  thumbnail_url: string | null
  created_by: string
  created_at: string
}

interface LibraryPage {
  items: LibraryAssetItem[]
  total: number
  page: number
  per_page: number
}

interface ProjectOption { id: string; name: string }
interface FolderOption { id: string; name: string }

interface AccessGrant {
  id: string
  user_id: string
  project_id: string
  project_name: string
  folder_id: string | null
  folder_name: string | null
  granted_by: string
  created_at: string
}

interface UserSummary {
  id: string
  name: string | null
  email: string
  grants: AccessGrant[]
}

// ─── Access management dialog (admin only) ───────────────────────────────────

function ManageAccessDialog() {
  const [open, setOpen] = React.useState(false)
  const [selectedUserId, setSelectedUserId] = React.useState('')
  const [selectedProjectId, setSelectedProjectId] = React.useState('')
  const [selectedFolderId, setSelectedFolderId] = React.useState<string>('__project__')
  const [saving, setSaving] = React.useState(false)

  const { data: users } = useSWR<UserSummary[]>(
    open ? '/library/users' : null,
    (k: string) => api.get<UserSummary[]>(k),
  )
  const { data: projects } = useSWR<ProjectOption[]>(
    open ? '/library/projects' : null,
    (k: string) => api.get<ProjectOption[]>(k),
  )
  const { data: folders } = useSWR<FolderOption[]>(
    open && selectedProjectId ? `/library/folders/${selectedProjectId}` : null,
    (k: string) => api.get<FolderOption[]>(k),
  )

  const refresh = () => { void mutate('/library/users'); void mutate('/library/grants') }

  const handleGrant = async () => {
    if (!selectedUserId || !selectedProjectId) return
    setSaving(true)
    try {
      await api.post('/library/grants', {
        user_id: selectedUserId,
        project_id: selectedProjectId,
        folder_id: selectedFolderId === '__project__' ? null : selectedFolderId,
      })
      refresh()
      setSelectedUserId('')
      setSelectedProjectId('')
      setSelectedFolderId('__project__')
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to grant access')
    } finally {
      setSaving(false)
    }
  }

  const handleRevoke = async (grantId: string) => {
    try {
      await api.delete(`/library/grants/${grantId}`)
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to revoke access')
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="secondary" size="sm">
          <Users className="h-4 w-4" />
          Manage Access
        </Button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-xl max-h-[85vh] overflow-y-auto -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-bg-secondary p-6 shadow-xl">
          <Dialog.Close className="absolute right-4 top-4 text-text-tertiary hover:text-text-primary transition-colors">
            <X className="h-4 w-4" />
          </Dialog.Close>
          <Dialog.Title className="text-base font-semibold text-text-primary">Manage Library Access</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-text-secondary">
            Grant editors access to specific projects or folders. Editors always see assets they uploaded themselves.
          </Dialog.Description>

          {/* Grant form */}
          <div className="mt-4 rounded-lg border border-border bg-bg-primary p-4 space-y-3">
            <p className="text-xs font-medium text-text-tertiary uppercase tracking-wide">Add access</p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <select
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-border-focus"
              >
                <option value="">Select user…</option>
                {(users ?? []).map((u) => (
                  <option key={u.id} value={u.id}>{u.name || u.email}</option>
                ))}
              </select>
              <select
                value={selectedProjectId}
                onChange={(e) => { setSelectedProjectId(e.target.value); setSelectedFolderId('__project__') }}
                className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-border-focus"
              >
                <option value="">Select project…</option>
                {(projects ?? []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <select
                value={selectedFolderId}
                onChange={(e) => setSelectedFolderId(e.target.value)}
                disabled={!selectedProjectId}
                className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-border-focus disabled:opacity-50"
              >
                <option value="__project__">Entire project</option>
                {(folders ?? []).map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end">
              <Button
                size="sm"
                loading={saving}
                disabled={!selectedUserId || !selectedProjectId}
                onClick={handleGrant}
              >
                <Plus className="h-4 w-4" />
                Grant Access
              </Button>
            </div>
          </div>

          {/* Current grants list */}
          <div className="mt-4 space-y-3">
            {(users ?? []).filter((u) => u.grants.length > 0).map((u) => (
              <div key={u.id} className="rounded-lg border border-border bg-bg-primary p-3 space-y-2">
                <p className="text-sm font-medium text-text-primary">{u.name || u.email}</p>
                {u.grants.map((g) => (
                  <div key={g.id} className="flex items-center justify-between gap-2 text-xs text-text-secondary">
                    <span className="flex items-center gap-1.5">
                      {g.folder_id ? <FolderOpen className="h-3 w-3 shrink-0" /> : <Library className="h-3 w-3 shrink-0" />}
                      <span className="font-medium text-text-primary">{g.project_name}</span>
                      {g.folder_name && <span className="text-text-tertiary">/ {g.folder_name}</span>}
                    </span>
                    <button
                      onClick={() => void handleRevoke(g.id)}
                      className="text-text-tertiary hover:text-status-error transition-colors"
                      title="Revoke access"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            ))}
            {(users ?? []).every((u) => u.grants.length === 0) && (
              <p className="text-sm text-text-tertiary py-2">No grants yet.</p>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

const PER_PAGE = 24

export default function LibraryPage() {
  usePageTitle('Library')
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)

  const [page, setPage] = React.useState(1)
  const [search, setSearch] = React.useState('')
  const [debouncedSearch, setDebouncedSearch] = React.useState('')
  const [projectFilter, setProjectFilter] = React.useState('')
  const [tagFilter, setTagFilter] = React.useState<string[]>([])
  const [frameLabelFilter, setFrameLabelFilter] = React.useState<string[]>([])
  const searchTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  React.useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setDebouncedSearch(search), 300)
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current) }
  }, [search])

  // Reset page on filter change
  React.useEffect(() => { setPage(1) }, [debouncedSearch, projectFilter, tagFilter, frameLabelFilter])

  const queryParams = new URLSearchParams({ page: String(page), per_page: String(PER_PAGE) })
  if (debouncedSearch) queryParams.set('q', debouncedSearch)
  if (projectFilter) queryParams.set('project_id', projectFilter)
  tagFilter.forEach((t) => queryParams.append('tag', t))
  frameLabelFilter.forEach((l) => queryParams.append('frame_label', l))

  const { data, isLoading } = useSWR<LibraryPage>(
    `/library?${queryParams}`,
    (k: string) => api.get<LibraryPage>(k),
    { keepPreviousData: true },
  )
  const { data: projects } = useSWR<ProjectOption[]>(
    '/library/projects',
    (k: string) => api.get<ProjectOption[]>(k),
  )

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  const toggleTag = (tag: string) =>
    setTagFilter((prev) => prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag])

  const toggleFrameLabel = (label: string) =>
    setFrameLabelFilter((prev) => prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label])

  // Collect unique tags and frame labels from current results for filter chips
  const allTags = React.useMemo(() => {
    const s = new Set<string>()
    for (const item of data?.items ?? []) {
      for (const t of item.keywords ?? []) s.add(t)
    }
    return Array.from(s).sort()
  }, [data])

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Library</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            {isPlatformAdmin ? 'All assets across all projects.' : 'Assets you have access to.'}
          </p>
        </div>
        {isPlatformAdmin && <ManageAccessDialog />}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name…"
            className="h-8 rounded-md border border-border bg-bg-secondary pl-8 pr-3 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-border-focus w-52"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-primary">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Project filter */}
        {(projects ?? []).length > 0 && (
          <div className="relative">
            <select
              value={projectFilter}
              onChange={(e) => setProjectFilter(e.target.value)}
              className="h-8 appearance-none rounded-md border border-border bg-bg-secondary pl-2.5 pr-7 text-sm text-text-primary focus:outline-none focus:border-border-focus cursor-pointer"
            >
              <option value="">All projects</option>
              {(projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary pointer-events-none" />
          </div>
        )}

        {/* Active tag chips */}
        {tagFilter.map((t) => (
          <button
            key={t}
            onClick={() => toggleTag(t)}
            className="inline-flex items-center gap-1 h-7 rounded-full bg-accent-muted border border-accent text-accent px-2.5 text-xs font-medium"
          >
            {t}<X className="h-3 w-3" />
          </button>
        ))}
        {frameLabelFilter.map((l) => (
          <button
            key={l}
            onClick={() => toggleFrameLabel(l)}
            className="inline-flex items-center gap-1 h-7 rounded-full bg-purple-500/10 border border-purple-400/40 text-purple-400 px-2.5 text-xs font-medium"
          >
            ▶ {l}<X className="h-3 w-3" />
          </button>
        ))}

        {(tagFilter.length > 0 || frameLabelFilter.length > 0 || projectFilter || debouncedSearch) && (
          <button
            onClick={() => { setSearch(''); setProjectFilter(''); setTagFilter([]); setFrameLabelFilter([]) }}
            className="text-xs text-text-tertiary hover:text-text-primary underline"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Tag filter chips (from results) */}
      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <span className="text-xs text-text-tertiary self-center mr-1">Tags:</span>
          {allTags.map((t) => (
            <button
              key={t}
              onClick={() => toggleTag(t)}
              className={cn(
                'h-6 rounded-full border px-2.5 text-xs font-medium transition-colors',
                tagFilter.includes(t)
                  ? 'bg-accent-muted border-accent text-accent'
                  : 'border-border text-text-secondary hover:border-text-secondary',
              )}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {/* Asset grid */}
      {isLoading && (data?.items ?? []).length === 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="aspect-video animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : (data?.items ?? []).length === 0 ? (
        <EmptyState
          icon={Library}
          title="No assets found"
          description={
            isPlatformAdmin
              ? 'No assets match your current filters.'
              : 'No assets have been shared with you yet. Ask an admin to grant you access.'
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {(data?.items ?? []).map((item) => (
              <AssetCard key={item.id} item={item} onTagClick={toggleTag} onFrameLabelClick={toggleFrameLabel} />
            ))}
          </div>

          {/* Pagination */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between pt-2 border-t border-border">
            <p className="text-xs text-text-tertiary">
              {total === 0 ? '0' : `${(page - 1) * PER_PAGE + 1}–${Math.min(page * PER_PAGE, total)}`} of {total} assets
            </p>
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
              <span className="text-xs text-text-tertiary whitespace-nowrap">Page {page} / {totalPages}</span>
              <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Asset card ───────────────────────────────────────────────────────────────

function AssetCard({
  item,
  onTagClick,
  onFrameLabelClick,
}: {
  item: LibraryAssetItem
  onTagClick: (tag: string) => void
  onFrameLabelClick: (label: string) => void
}) {
  return (
    <Link
      href={`/projects/${item.project_id}/assets/${item.id}`}
      className="group flex flex-col gap-1.5 rounded-lg border border-border bg-bg-secondary overflow-hidden hover:border-border-focus transition-colors"
    >
      {/* Thumbnail */}
      <div className="relative aspect-video bg-bg-tertiary overflow-hidden">
        {item.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.thumbnail_url}
            alt=""
            className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-200"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <Film className="h-6 w-6 text-text-tertiary" />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="px-2 pb-2 space-y-0.5">
        <p className="text-xs font-medium text-text-primary truncate group-hover:text-accent transition-colors">
          {item.name}
        </p>
        <p className="text-[10px] text-text-tertiary truncate">
          {item.project_name}{item.folder_name ? ` / ${item.folder_name}` : ''}
        </p>

        {/* Tags */}
        {(item.keywords ?? []).length > 0 && (
          <div className="flex flex-wrap gap-0.5 pt-0.5">
            {(item.keywords ?? []).slice(0, 3).map((t) => (
              <button
                key={t}
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); onTagClick(t) }}
                className="rounded-full border border-border px-1.5 text-[9px] text-text-tertiary hover:text-text-primary hover:border-text-secondary transition-colors"
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>
    </Link>
  )
}
