'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import useSWR, { mutate } from 'swr'
import useSWRInfinite from 'swr/infinite'
import * as Dialog from '@radix-ui/react-dialog'
import { Library, Film, Search, X, Plus, Trash2, ChevronDown, FolderOpen, Users, Play, Check, Download } from 'lucide-react'
import { ShortcutsHint } from '@/components/ui/shortcuts-hint'
import { api } from '@/lib/api'
import { cn, downloadAsset } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/shared/empty-state'
import { usePageTitle } from '@/hooks/use-page-title'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
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
  frame_labels: string[] | null
  thumbnail_url: string | null
  video_url: string | null
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
interface TagOption { tag: string; count: number }
interface LabelOption { label: string; count: number }

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

// ─── Multi-select dropdown ────────────────────────────────────────────────────

function MultiSelectDropdown({
  label,
  options,
  selected,
  onToggle,
  onClear,
  color = 'default',
}: {
  label: string
  options: { value: string; count: number }[]
  selected: string[]
  onToggle: (v: string) => void
  onClear: () => void
  color?: 'default' | 'purple'
}) {
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState('')
  const ref = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const filtered = options.filter((o) =>
    o.value.toLowerCase().includes(search.toLowerCase()),
  )

  const activeClass = color === 'purple'
    ? 'border-purple-400/60 bg-purple-500/10 text-purple-400'
    : 'border-accent bg-accent-muted text-accent'

  const checkActiveClass = color === 'purple'
    ? 'border-purple-400 bg-purple-400'
    : 'border-accent bg-accent'

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-sm transition-colors select-none',
          selected.length > 0
            ? activeClass
            : 'border-border bg-bg-secondary text-text-secondary hover:text-text-primary hover:border-border-focus',
        )}
      >
        {label}
        {selected.length > 0 && (
          <span className="rounded-full bg-current/20 px-1.5 py-0.5 text-[10px] font-bold leading-none tabular-nums">
            {selected.length}
          </span>
        )}
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-150', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute top-full left-0 z-30 mt-1 w-56 rounded-lg border border-border bg-bg-secondary shadow-xl">
          {options.length > 8 && (
            <div className="border-b border-border p-2">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search…"
                autoFocus
                className="w-full rounded-md bg-bg-primary px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none"
              />
            </div>
          )}
          <div className="max-h-60 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <p className="py-3 text-center text-xs text-text-tertiary">No matches</p>
            ) : (
              filtered.map((o) => (
                <button
                  key={o.value}
                  onClick={() => onToggle(o.value)}
                  className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-text-primary hover:bg-bg-hover transition-colors"
                >
                  <span
                    className={cn(
                      'flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border transition-colors',
                      selected.includes(o.value) ? checkActiveClass : 'border-border',
                    )}
                  >
                    {selected.includes(o.value) && <Check className="h-2.5 w-2.5 text-white stroke-[3]" />}
                  </span>
                  <span className="flex-1 truncate">{o.value}</span>
                  <span className="text-text-tertiary tabular-nums">{o.count}</span>
                </button>
              ))
            )}
          </div>
          {selected.length > 0 && (
            <div className="border-t border-border p-1.5">
              <button
                onClick={() => { onClear(); setOpen(false) }}
                className="w-full rounded py-1 text-center text-[10px] text-text-tertiary hover:text-text-primary transition-colors"
              >
                Clear selection
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
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

const LIBRARY_SHORTCUTS = [
  {
    title: 'Grid navigation',
    items: [
      { keys: ['↑'], label: 'Select previous item' },
      { keys: ['↓'], label: 'Select next item' },
      { keys: ['Enter'], label: 'Open selected asset' },
      { keys: ['Esc'], label: 'Deselect' },
    ],
  },
  {
    title: 'Playback (item selected)',
    items: [
      { keys: ['←'], label: 'Seek back 3 s' },
      { keys: ['→'], label: 'Seek forward 3 s' },
    ],
  },
]

const PER_PAGE = 24

export default function LibraryPage() {
  usePageTitle('Library')
  const router = useRouter()
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)

  const [search, setSearch] = React.useState('')
  const [debouncedSearch, setDebouncedSearch] = React.useState('')
  const [projectFilter, setProjectFilter] = React.useState('')
  const [tagFilter, setTagFilter] = React.useState<string[]>([])
  const [frameLabelFilter, setFrameLabelFilter] = React.useState<string[]>([])
  const [selectedIndex, setSelectedIndex] = React.useState<number | null>(null)
  const videoRef = React.useRef<HTMLVideoElement>(null)
  const searchTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  React.useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setDebouncedSearch(search), 300)
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current) }
  }, [search])

  const tagParams = projectFilter ? `?project_id=${projectFilter}` : ''

  // Infinite scroll: each SWR "page" is one /library request. The key encodes the
  // active filters, so changing a filter swaps the whole key set; we reset back to
  // a single page below. A short last page (< PER_PAGE) means we've hit the end.
  const getKey = React.useCallback(
    (index: number, previous: LibraryPage | null) => {
      if (previous && previous.items.length < PER_PAGE) return null
      const qp = new URLSearchParams({ page: String(index + 1), per_page: String(PER_PAGE) })
      if (debouncedSearch) qp.set('q', debouncedSearch)
      if (projectFilter) qp.set('project_id', projectFilter)
      tagFilter.forEach((t) => qp.append('tag', t))
      frameLabelFilter.forEach((l) => qp.append('frame_label', l))
      return `/library?${qp}`
    },
    [debouncedSearch, projectFilter, tagFilter, frameLabelFilter],
  )

  const { data: pages, isLoading, isValidating, setSize } = useSWRInfinite<LibraryPage>(
    getKey,
    (k: string) => api.get<LibraryPage>(k),
    { revalidateFirstPage: false, keepPreviousData: true },
  )

  // Collapse back to page 1 whenever the filters change.
  React.useEffect(() => { setSize(1) }, [debouncedSearch, projectFilter, tagFilter, frameLabelFilter, setSize])
  const { data: projects } = useSWR<ProjectOption[]>(
    '/library/projects',
    (k: string) => api.get<ProjectOption[]>(k),
  )
  const { data: allTags } = useSWR<TagOption[]>(
    `/library/tags${tagParams}`,
    (k: string) => api.get<TagOption[]>(k),
  )
  const { data: allLabels } = useSWR<LabelOption[]>(
    `/library/frame-labels${tagParams}`,
    (k: string) => api.get<LabelOption[]>(k),
  )

  const items = React.useMemo(() => (pages ?? []).flatMap((p) => p.items), [pages])
  const total = pages?.[0]?.total ?? 0
  const lastPage = pages?.[pages.length - 1]
  const reachedEnd = lastPage ? lastPage.items.length < PER_PAGE : false
  const loadingMore = isValidating && (pages?.length ?? 0) > 0
  const sentinelRef = useInfiniteScroll({
    onLoadMore: () => setSize((s) => s + 1),
    enabled: !reachedEnd && !loadingMore && items.length > 0,
  })

  const toggleTag = (tag: string) =>
    setTagFilter((prev) => prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag])

  const toggleFrameLabel = (label: string) =>
    setFrameLabelFilter((prev) => prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label])

  const hasActiveFilters = tagFilter.length > 0 || frameLabelFilter.length > 0 || projectFilter || debouncedSearch

  // Reset selection when results change
  React.useEffect(() => { setSelectedIndex(null) }, [debouncedSearch, projectFilter, tagFilter, frameLabelFilter])

  // Scroll selected card into view
  React.useEffect(() => {
    if (selectedIndex === null) return
    document.querySelector(`[data-lib-index="${selectedIndex}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedIndex])

  // Keyboard navigation
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev === null ? 0 : Math.min(prev + 1, items.length - 1)))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev === null ? 0 : Math.max(prev - 1, 0)))
      } else if (e.key === 'ArrowLeft') {
        if (selectedIndex !== null && videoRef.current) {
          e.preventDefault()
          videoRef.current.currentTime = Math.max(0, videoRef.current.currentTime - 3)
        }
      } else if (e.key === 'ArrowRight') {
        if (selectedIndex !== null && videoRef.current) {
          e.preventDefault()
          videoRef.current.currentTime = Math.min(videoRef.current.duration || 0, videoRef.current.currentTime + 3)
        }
      } else if (e.key === 'Enter' && selectedIndex !== null) {
        const item = items[selectedIndex]
        if (item) router.push(`/projects/${item.project_id}/assets/${item.id}?from=/library`)
      } else if (e.key === 'Escape') {
        setSelectedIndex(null)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [items, selectedIndex, router])

  const tagOptions = (allTags ?? []).map((t) => ({ value: t.tag, count: t.count }))
  const labelOptions = (allLabels ?? []).map((l) => ({ value: l.label, count: l.count }))

  const selectedItem = selectedIndex !== null ? items[selectedIndex] ?? null : null

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
        <div className="flex items-center gap-2">
          {isPlatformAdmin && <ManageAccessDialog />}
          <ShortcutsHint groups={LIBRARY_SHORTCUTS} />
        </div>
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
              className={cn(
                'h-8 appearance-none rounded-md border bg-bg-secondary pl-2.5 pr-7 text-sm focus:outline-none focus:border-border-focus cursor-pointer',
                projectFilter ? 'border-accent text-accent' : 'border-border text-text-primary',
              )}
            >
              <option value="">All projects</option>
              {(projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary pointer-events-none" />
          </div>
        )}

        {/* Keywords multi-select */}
        {tagOptions.length > 0 && (
          <MultiSelectDropdown
            label="Keywords"
            options={tagOptions}
            selected={tagFilter}
            onToggle={toggleTag}
            onClear={() => setTagFilter([])}
            color="default"
          />
        )}

        {/* Video labels multi-select */}
        {labelOptions.length > 0 && (
          <MultiSelectDropdown
            label="Video Labels"
            options={labelOptions}
            selected={frameLabelFilter}
            onToggle={toggleFrameLabel}
            onClear={() => setFrameLabelFilter([])}
            color="purple"
          />
        )}

        {/* Active filter chips */}
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
            <Play className="h-2.5 w-2.5 fill-current" />{l}<X className="h-3 w-3" />
          </button>
        ))}

        {hasActiveFilters && (
          <button
            onClick={() => { setSearch(''); setProjectFilter(''); setTagFilter([]); setFrameLabelFilter([]) }}
            className="text-xs text-text-tertiary hover:text-text-primary underline"
          >
            Clear all
          </button>
        )}
      </div>

      {/* Asset grid */}
      {isLoading && items.length === 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="aspect-video animate-pulse rounded-lg bg-bg-secondary" />
          ))}
        </div>
      ) : items.length === 0 ? (
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
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {items.map((item, idx) => (
              <AssetCard
                key={item.id}
                item={item}
                index={idx}
                selected={selectedIndex === idx}
                onTagClick={toggleTag}
                onFrameLabelClick={toggleFrameLabel}
                onSelect={() => setSelectedIndex(idx)}
              />
            ))}
          </div>

          {/* Infinite scroll: sentinel auto-loads the next page as it nears view. */}
          {!reachedEnd && (
            <div ref={sentinelRef} className="h-10 flex items-center justify-center">
              {loadingMore && (
                <span className="text-xs text-text-tertiary">Loading more…</span>
              )}
            </div>
          )}
          <p className="text-center text-xs text-text-tertiary pt-1">
            Showing {items.length} of {total} asset{total !== 1 ? 's' : ''}
          </p>
        </>
      )}
      {/* Keyboard shortcut hint — shown until first selection */}
      {items.length > 0 && selectedIndex === null && (
        <p className="text-xs text-text-tertiary text-center py-1">
          Press <kbd className="rounded border border-border px-1 py-0.5 font-mono text-[10px]">↑</kbd>{' '}
          <kbd className="rounded border border-border px-1 py-0.5 font-mono text-[10px]">↓</kbd> to navigate assets
        </p>
      )}

      {/* PIP preview panel */}
      {selectedItem && (
        <div className="fixed bottom-4 right-4 z-50 w-72 rounded-xl border border-border bg-bg-secondary shadow-2xl overflow-hidden">
          <button
            onClick={() => setSelectedIndex(null)}
            className="absolute right-2 top-2 z-10 rounded-full bg-black/60 p-1 text-white hover:bg-black/80 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>

          {selectedItem.video_url ? (
            // eslint-disable-next-line jsx-a11y/media-has-caption
            <video
              ref={videoRef}
              key={selectedItem.id}
              src={selectedItem.video_url}
              className="w-full aspect-video bg-black"
              autoPlay
              playsInline
              controls
            />
          ) : selectedItem.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={selectedItem.thumbnail_url} alt="" className="w-full aspect-video object-cover" />
          ) : (
            <div className="w-full aspect-video bg-bg-tertiary flex items-center justify-center">
              <Film className="h-8 w-8 text-text-tertiary" />
            </div>
          )}

          <div className="p-3">
            <p className="text-sm font-medium text-text-primary truncate">{selectedItem.name}</p>
            <p className="text-[11px] text-text-tertiary truncate mt-0.5">
              {selectedItem.project_name}{selectedItem.folder_name ? ` / ${selectedItem.folder_name}` : ''}
            </p>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-text-tertiary">
              <span><kbd className="font-mono">↑↓</kbd> navigate</span>
              <span><kbd className="font-mono">←→</kbd> ±3s</span>
              <span><kbd className="font-mono">↵</kbd> open</span>
              <span><kbd className="font-mono">Esc</kbd> close</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Asset card ───────────────────────────────────────────────────────────────

function AssetCard({
  item,
  index,
  selected,
  onTagClick,
  onFrameLabelClick,
  onSelect,
}: {
  item: LibraryAssetItem
  index: number
  selected: boolean
  onTagClick: (tag: string) => void
  onFrameLabelClick: (label: string) => void
  onSelect: () => void
}) {
  const keywords = item.keywords ?? []
  const frameLabels = item.frame_labels ?? []
  const extraKeywords = keywords.length > 3 ? keywords.length - 3 : 0

  return (
    <Link
      href={`/projects/${item.project_id}/assets/${item.id}?from=/library`}
      data-lib-index={index}
      onClick={onSelect}
      className={cn(
        'group flex flex-col rounded-lg border bg-bg-secondary overflow-hidden transition-colors',
        selected
          ? 'border-accent ring-1 ring-accent/40'
          : 'border-border hover:border-border-focus',
      )}
    >
      {/* Thumbnail */}
      <div className="relative aspect-video bg-bg-tertiary overflow-hidden">
        {item.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.thumbnail_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-200"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <Film className="h-6 w-6 text-text-tertiary" />
          </div>
        )}

        {/* Download — top-right, appears on hover */}
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); void downloadAsset(item.id) }}
          className="absolute top-1.5 right-1.5 z-10 hidden h-6 w-6 items-center justify-center rounded-md bg-black/70 text-white backdrop-blur-sm transition-colors hover:bg-black/90 group-hover:flex"
          title="Download"
        >
          <Download className="h-3.5 w-3.5" />
        </button>

        {/* Video label count badge — bottom-left of thumbnail */}
        {frameLabels.length > 0 && (
          <div className="group/labels absolute bottom-1.5 left-1.5">
            <div className="flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-purple-300 backdrop-blur-sm">
              <Play className="h-2.5 w-2.5 fill-current" />
              {frameLabels.length} {frameLabels.length === 1 ? 'label' : 'labels'}
            </div>
            {/* Hover popover listing label names */}
            <div className="absolute bottom-full left-0 mb-1.5 hidden group-hover/labels:block z-20 min-w-[120px] max-w-[180px] rounded-md border border-border bg-bg-primary p-1.5 shadow-xl">
              {frameLabels.map((l) => (
                <button
                  key={l}
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); onFrameLabelClick(l) }}
                  className="block w-full truncate rounded px-2 py-1 text-left text-[11px] text-text-secondary hover:bg-bg-hover hover:text-purple-400 transition-colors"
                >
                  {l}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="px-2.5 py-2 space-y-1">
        <p className="text-xs font-medium text-text-primary truncate group-hover:text-accent transition-colors">
          {item.name}
        </p>
        <p className="text-[10px] text-text-tertiary truncate">
          {item.project_name}{item.folder_name ? ` / ${item.folder_name}` : ''}
        </p>

        {/* Keyword chips */}
        {keywords.length > 0 && (
          <div className="flex flex-wrap items-center gap-0.5 pt-0.5">
            {keywords.slice(0, 3).map((t) => (
              <button
                key={t}
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); onTagClick(t) }}
                className="rounded-full border border-border px-1.5 text-[9px] text-text-tertiary hover:text-accent hover:border-accent transition-colors"
              >
                {t}
              </button>
            ))}
            {extraKeywords > 0 && (
              <span className="text-[9px] text-text-tertiary">+{extraKeywords}</span>
            )}
          </div>
        )}
      </div>
    </Link>
  )
}
