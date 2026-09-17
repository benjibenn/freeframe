'use client'

/**
 * Master/detail view of every brief on the platform.
 *
 * The point of this component is what it does NOT do: selecting a brief never
 * navigates. The structured brief, the submitter list and thumbnails of what each
 * submitter uploaded all render in the right-hand pane, so an admin can sweep the
 * whole pipeline without opening an edit form or walking into a per-submitter
 * project. Pure props — the page owns fetching, this owns presentation.
 */

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Check, Copy } from 'lucide-react'
import { BriefView } from '@/components/projects/brief-view'

export type BriefOverviewFile = {
  asset_id: string
  name: string
  thumbnail_url: string | null
}

export type BriefOverviewSubmission = {
  id: string
  user_id: string
  user_name: string
  user_email: string
  display_name: string | null
  project_id: string
  paid_at: string | null
  created_at: string
  asset_count: number
  files: BriefOverviewFile[]
}

export type BriefOverviewRow = {
  id: string
  token: string
  title: string
  instructions: string | null
  is_enabled: boolean
  expires_at: string | null
  created_at: string
  home_project_id: string | null
  home_folder_id: string | null
  home_path: string | null
  persona_label: string | null
  angle_label: string | null
  problem: string | null
  has_brief: boolean
  brief_json: Record<string, unknown> | null
  reference_image_count: number
  reference_video_count: number
  submission_count: number
  asset_count: number
  submissions: BriefOverviewSubmission[]
}

const API = process.env.NEXT_PUBLIC_API_URL || ''

/**
 * Reference media is stored as an ordered S3 key list and served by POSITION off
 * the public submit route, so the payload only carries a count. Rebuild the same
 * indexed URLs the submit page uses rather than inventing a second scheme.
 */
function referenceUrls(token: string, kind: 'image' | 'video', count: number): string[] {
  return Array.from({ length: count }, (_, i) => `${API}/submit/${token}/reference-${kind}/${i}`)
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md bg-bg-secondary px-1.5 py-0.5 text-2xs text-text-tertiary">
      {children}
    </span>
  )
}

/**
 * The brief's creation day in the VIEWER's timezone, as YYYY-MM-DD.
 *
 * `<input type="date">` yields a local calendar day, while created_at is a UTC
 * instant. Comparing the two as strings on the same local footing avoids the
 * classic off-by-one where `new Date('2026-09-10')` parses as UTC midnight and
 * silently drops a brief created that evening.
 */
function localDay(iso: string): string {
  const d = new Date(iso)
  const m = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

/**
 * The token-gated page an editor actually submits against. Built from
 * window.location.origin rather than NEXT_PUBLIC_API_URL: this is the web route
 * a human opens, not the API that serves reference media. Mirrors the helper in
 * projects/request-card.tsx, which is where admins copy the same link today.
 */
function submitUrl(token: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}/submit/${token}`
}

function CopyBriefLink({ token }: { token: string }) {
  const [copied, setCopied] = useState(false)

  // Self-clearing rather than a bare setTimeout: the parent remounts this on
  // every brief switch (key={selected.id}), so a dangling timer would outlive
  // the component it was meant to reset.
  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(t)
  }, [copied])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(submitUrl(token))
      setCopied(true)
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title="Copy the submission link to send to an editor"
      className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
    >
      {copied ? (
        <>
          <Check className="h-3.5 w-3.5 text-status-success" />
          Copied
        </>
      ) : (
        <>
          <Copy className="h-3.5 w-3.5" />
          Copy brief link
        </>
      )}
    </button>
  )
}

type Filters = { query: string; from: string; to: string; withFiles: boolean; userId: string }

/**
 * Name search spans the title AND the folder path because both are rendered on
 * the row — an admin searching "Iphone 17" is reading the line they can see, not
 * guessing which of the two fields the string happens to live in.
 */
function matches(r: BriefOverviewRow, f: Filters): boolean {
  if (f.withFiles && r.asset_count === 0) return false
  if (f.userId && !r.submissions.some((s) => s.user_id === f.userId)) return false

  const day = localDay(r.created_at)
  if (f.from && day < f.from) return false
  if (f.to && day > f.to) return false

  const q = f.query.trim().toLowerCase()
  if (!q) return true
  return `${r.title} ${r.home_path ?? ''}`.toLowerCase().includes(q)
}

const NO_FILTERS: Filters = { query: '', from: '', to: '', withFiles: false, userId: '' }

export function BriefOverviewTable({ rows }: { rows: BriefOverviewRow[] }) {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [selectedId, setSelectedId] = useState<string | null>(rows[0]?.id ?? null)

  const visible = useMemo(() => rows.filter((r) => matches(r, filters)), [rows, filters])

  // Every distinct submitter across all briefs, sorted for a stable dropdown.
  const submitters = useMemo(() => {
    const byId = new Map<string, string>()
    for (const r of rows) {
      for (const s of r.submissions) byId.set(s.user_id, s.user_name || s.user_email)
    }
    return Array.from(byId, ([id, label]) => ({ id, label })).sort((a, b) =>
      a.label.localeCompare(b.label),
    )
  }, [rows])

  // Selection is DERIVED, not stored-and-corrected. Narrowing the filters can
  // hide whatever was selected; falling through to the first visible brief keeps
  // the detail pane populated without an effect that would flash the old brief
  // for a frame before resetting it.
  const selected = visible.find((r) => r.id === selectedId) ?? visible[0] ?? null
  // When a submitter filter is active, the detail pane shows only THEIR
  // submissions — that's what "view submissions by user" means once a brief
  // is open, not every submitter's work on that brief.
  const selectedSubmissions = selected
    ? filters.userId
      ? selected.submissions.filter((s) => s.user_id === filters.userId)
      : selected.submissions
    : []
  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }))
  // Judged on whether a control is SET, not on whether the count changed: a
  // date bound that happens to admit every brief is still an active filter, and
  // the admin needs the Clear affordance to see that.
  const isFiltered =
    filters.query.trim() !== '' ||
    filters.from !== '' ||
    filters.to !== '' ||
    filters.withFiles ||
    filters.userId !== ''

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      {/* ── Master ─────────────────────────────────────────────── */}
      <div className="flex flex-col gap-1 overflow-y-auto lg:max-h-[calc(100vh-12rem)]">
        <div className="sticky top-0 z-10 flex flex-col gap-2 bg-bg-primary pb-2">
          <input
            type="search"
            value={filters.query}
            onChange={(e) => set({ query: e.target.value })}
            placeholder="Search name or path…"
            aria-label="Search briefs by name"
            className="w-full rounded-md border border-border bg-bg-secondary px-2 py-1.5 text-sm text-text-primary placeholder:text-text-tertiary"
          />
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1 text-xs text-text-tertiary">
              From
              <input
                type="date"
                value={filters.from}
                onChange={(e) => set({ from: e.target.value })}
                aria-label="Created from"
                className="rounded-md border border-border bg-bg-secondary px-1.5 py-1 text-xs text-text-primary"
              />
            </label>
            <label className="flex items-center gap-1 text-xs text-text-tertiary">
              To
              <input
                type="date"
                value={filters.to}
                onChange={(e) => set({ to: e.target.value })}
                aria-label="Created to"
                className="rounded-md border border-border bg-bg-secondary px-1.5 py-1 text-xs text-text-primary"
              />
            </label>
            <label className="flex items-center gap-1.5 text-xs text-text-secondary">
              <input
                type="checkbox"
                checked={filters.withFiles}
                onChange={(e) => set({ withFiles: e.target.checked })}
                className="h-3.5 w-3.5 accent-accent"
              />
              Has files
            </label>
            {submitters.length > 0 && (
              <select
                value={filters.userId}
                onChange={(e) => set({ userId: e.target.value })}
                aria-label="Filter by submitter"
                className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-[13px] text-text-primary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus cursor-pointer max-w-[12rem]"
              >
                <option value="">All submitters</option>
                {submitters.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.label}
                  </option>
                ))}
              </select>
            )}
            {isFiltered && (
              <button
                type="button"
                onClick={() => setFilters(NO_FILTERS)}
                className="text-xs text-text-tertiary underline hover:text-text-secondary"
              >
                Clear
              </button>
            )}
          </div>
          {isFiltered && (
            <p className="text-2xs text-text-tertiary">
              Showing {visible.length} of {rows.length}
            </p>
          )}
        </div>

        {rows.length === 0 && (
          <p className="px-2 py-4 text-sm text-text-tertiary">No briefs yet.</p>
        )}
        {rows.length > 0 && visible.length === 0 && (
          <p className="px-2 py-4 text-sm text-text-tertiary">No briefs match these filters.</p>
        )}
        {visible.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setSelectedId(r.id)}
            aria-current={r.id === selected?.id}
            className={`rounded-md border px-3 py-2 text-left transition-colors ${
              r.id === selected?.id
                ? 'border-accent bg-bg-secondary'
                : 'border-border hover:bg-bg-hover'
            }`}
          >
            <span className="block truncate text-sm font-medium text-text-primary">
              {r.title}
            </span>
            {r.home_path && (
              <span className="mt-0.5 block truncate text-xs text-text-tertiary">
                {r.home_path}
              </span>
            )}
            <span className="mt-1 flex flex-wrap items-center gap-1">
              {r.persona_label && <Chip>{r.persona_label}</Chip>}
              {r.angle_label && <Chip>{r.angle_label}</Chip>}
              {r.problem && <Chip>{r.problem}</Chip>}
              {!r.is_enabled && <Chip>disabled</Chip>}
            </span>
            <span className="mt-1 block text-xs text-text-secondary">
              {r.submission_count} submission{r.submission_count === 1 ? '' : 's'} ·{' '}
              {r.asset_count} file{r.asset_count === 1 ? '' : 's'}
            </span>
          </button>
        ))}
      </div>

      {/* ── Detail ─────────────────────────────────────────────── */}
      <div className="overflow-y-auto rounded-md border border-border p-4 lg:max-h-[calc(100vh-12rem)]">
        {!selected ? (
          <p className="text-sm text-text-tertiary">Select a brief.</p>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-text-primary">{selected.title}</h2>
                {selected.home_path && (
                  <p className="mt-0.5 text-xs text-text-tertiary">{selected.home_path}</p>
                )}
              </div>
              <CopyBriefLink key={selected.id} token={selected.token} />
            </div>

            {selected.brief_json ? (
              <div className="mt-4 border-t border-border pt-4">
                <BriefView data={selected.brief_json} />
              </div>
            ) : (
              <p className="mt-4 border-t border-border pt-4 text-sm text-text-tertiary">
                No structured brief attached.
              </p>
            )}

            {(selected.reference_image_count > 0 || selected.reference_video_count > 0) && (
              <div className="mt-5 border-t border-border pt-4">
                <h3 className="text-sm font-medium text-text-secondary">References</h3>
                {selected.reference_image_count > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {referenceUrls(selected.token, 'image', selected.reference_image_count).map(
                      (url, i) => (
                        <li key={url}>
                          <a href={url} target="_blank" rel="noreferrer">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={url}
                              alt={`Reference ${i + 1}`}
                              className="h-28 w-28 rounded border border-border object-cover transition-opacity hover:opacity-80"
                            />
                          </a>
                        </li>
                      ),
                    )}
                  </ul>
                )}
                {selected.reference_video_count > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {referenceUrls(selected.token, 'video', selected.reference_video_count).map(
                      (url) => (
                        <li key={url}>
                          <video
                            src={url}
                            controls
                            preload="metadata"
                            className="h-40 w-64 rounded border border-border bg-black object-contain"
                          />
                        </li>
                      ),
                    )}
                  </ul>
                )}
              </div>
            )}

            <div className="mt-5 border-t border-border pt-4">
              <h3 className="text-sm font-medium text-text-secondary">
                Submissions ({selectedSubmissions.length}
                {filters.userId ? ` of ${selected.submission_count}` : ''})
              </h3>
              {selectedSubmissions.length === 0 ? (
                <p className="mt-2 text-sm text-text-tertiary">
                  {filters.userId ? 'No submissions from this user on this brief.' : 'No submissions yet.'}
                </p>
              ) : (
                <ul className="mt-2 flex flex-col gap-3">
                  {selectedSubmissions.map((s) => (
                    <li key={s.id} className="rounded-md border border-border p-3">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm text-text-primary">
                            {s.display_name || s.user_name}
                          </p>
                          <p className="truncate text-xs text-text-tertiary">{s.user_email}</p>
                        </div>
                        <p className="text-xs text-text-tertiary">
                          {new Date(s.created_at).toLocaleDateString()}
                          {s.paid_at ? ' · paid' : ''}
                        </p>
                      </div>

                      {s.files.length === 0 ? (
                        <p className="mt-2 text-xs text-text-tertiary">Nothing uploaded yet.</p>
                      ) : (
                        <ul className="mt-2 flex flex-wrap gap-2">
                          {s.files.map((f) => (
                            <li key={f.asset_id} className="w-24">
                              {/* The upload's own review screen — comments, annotations,
                                  versions. ?from returns the back arrow here rather than
                                  stranding the admin in a submitter's project folder. */}
                              {/* New tab on purpose: the overview is a sweeping
                                  view, and an admin opening six uploads in a row
                                  should not lose their filters and scroll each
                                  time. ?from still gives the new tab a sane back
                                  target if they navigate on from there. */}
                              <Link
                                href={`/projects/${s.project_id}/assets/${f.asset_id}?from=/admin/briefs`}
                                target="_blank"
                                rel="noreferrer"
                                className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                                title={`Open ${f.name} in a new tab`}
                              >
                                {f.thumbnail_url ? (
                                  <img
                                    src={f.thumbnail_url}
                                    alt={f.name}
                                    className="h-16 w-24 rounded border border-border object-cover transition-opacity hover:opacity-80"
                                  />
                                ) : (
                                  <div className="flex h-16 w-24 items-center justify-center rounded border border-border bg-bg-secondary text-2xs text-text-tertiary transition-colors hover:bg-bg-hover">
                                    no preview
                                  </div>
                                )}
                                <span className="mt-1 block truncate text-2xs text-text-tertiary">
                                  {f.name}
                                </span>
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
