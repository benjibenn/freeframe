'use client'

/**
 * Four readings of one pipeline: totals, per brief, per person, per file.
 *
 * THE RULE THIS FILE EXISTS TO ENFORCE: every number on screen is derived from
 * the same scoped file list that decides which rows are on screen. The first
 * version filtered rows by date but rendered counts straight off the API, so a
 * two-day range kept a person whose last upload fell inside it and printed their
 * lifetime totals beside the filter. Never read a count that was computed
 * somewhere the filter is not.
 *
 * Two kinds of filter, deliberately not the same thing:
 *   SCOPE  (date range, submitter) — re-scopes every count. A number always
 *          means "in this window, for this person".
 *   SEARCH (the text box) — hides rows. It never changes what a number means,
 *          because searching "Ali" should not silently redefine a file count.
 *
 * A brief appears on the By brief tab when it received files in the window —
 * briefs created in the window with nothing uploaded are empty folders, not
 * work. The one number that ignores the window is "awaiting work": "has never
 * received a file" is not a question a date range can ask.
 *
 * Pure props. The page owns fetching, this owns presentation.
 */

import { useMemo, useState } from 'react'

export type ReportSubmitter = {
  user_id: string
  name: string
  submitted_at: string
}

export type ReportBriefRow = {
  id: string
  title: string
  home_path: string | null
  created_at: string
  is_enabled: boolean
  persona_label: string | null
  angle_label: string | null
  submitters: ReportSubmitter[]
}

export type ReportUserRow = {
  user_id: string
  name: string
  email: string
}

export type ReportFileRow = {
  asset_id: string
  name: string
  created_at: string
  project_id: string
  brief_id: string
  brief_title: string
  user_id: string
  user_name: string
}

export type ReportPayload = {
  briefs: ReportBriefRow[]
  users: ReportUserRow[]
  files: ReportFileRow[]
}

export type Filters = { query: string; from: string; to: string; userId: string }

export const NO_FILTERS: Filters = { query: '', from: '', to: '', userId: '' }

type Tab = 'summary' | 'briefs' | 'users' | 'files'

/** What a row shows once the window has been applied to it. */
export type ScopedBrief = ReportBriefRow & {
  file_count: number
  submitter_count: number
  uploader_names: string[]
  last_upload_at: string | null
}

export type ScopedUser = ReportUserRow & {
  brief_count: number
  file_count: number
  last_upload_at: string | null
}

export type Totals = {
  brief_count: number
  submission_count: number
  file_count: number
  submitter_count: number
  briefs_awaiting_work: number
}

/**
 * A timestamp's calendar day in the VIEWER's timezone, as YYYY-MM-DD.
 *
 * `<input type="date">` produces a local calendar day while the API returns UTC
 * instants. Comparing both as local-day strings avoids the off-by-one where
 * `new Date('2026-09-10')` parses as UTC midnight and drops work done that
 * evening from the range.
 */
export function localDay(iso: string): string {
  const d = new Date(iso)
  const m = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function inWindow(iso: string, f: Filters): boolean {
  if (f.from && localDay(iso) < f.from) return false
  if (f.to && localDay(iso) > f.to) return false
  return true
}

function hits(haystack: string, query: string): boolean {
  const q = query.trim().toLowerCase()
  return !q || haystack.toLowerCase().includes(q)
}

function newer(a: string | null, b: string): string {
  return a === null || b > a ? b : a
}

/**
 * The files the window is asking about. Everything else is counted from this.
 *
 * Search is excluded on purpose: it decides what is worth LOOKING at, not what
 * counts as work done.
 */
export function scopeFiles(files: ReportFileRow[], f: Filters): ReportFileRow[] {
  return files.filter((r) => {
    if (f.userId && r.user_id !== f.userId) return false
    return inWindow(r.created_at, f)
  })
}

export function scopeBriefs(
  briefs: ReportBriefRow[],
  scoped: ReportFileRow[],
  f: Filters,
): ScopedBrief[] {
  const byBrief = new Map<string, { files: number; last: string | null; names: Set<string> }>()
  for (const file of scoped) {
    const acc = byBrief.get(file.brief_id) ?? { files: 0, last: null, names: new Set<string>() }
    acc.files += 1
    acc.last = newer(acc.last, file.created_at)
    acc.names.add(file.user_name)
    byBrief.set(file.brief_id, acc)
  }

  const out: ScopedBrief[] = []
  for (const b of briefs) {
    const acc = byBrief.get(b.id)
    // Received nothing in the window: an empty folder, not work.
    if (!acc) continue
    out.push({
      ...b,
      file_count: acc.files,
      // People who ACCEPTED this brief inside the window. Distinct from the
      // uploaders beside it: accepting in March and delivering in September is
      // one submission and one upload, in different windows.
      submitter_count: b.submitters.filter(
        (s) => (!f.userId || s.user_id === f.userId) && inWindow(s.submitted_at, f),
      ).length,
      uploader_names: Array.from(acc.names).filter(Boolean).sort(),
      last_upload_at: acc.last,
    })
  }
  out.sort((a, z) => z.file_count - a.file_count)
  return out
}

export function scopeUsers(
  users: ReportUserRow[],
  scoped: ReportFileRow[],
  f: Filters,
): ScopedUser[] {
  const byUser = new Map<string, { files: number; briefs: Set<string>; last: string | null }>()
  for (const file of scoped) {
    const acc = byUser.get(file.user_id) ?? { files: 0, briefs: new Set<string>(), last: null }
    acc.files += 1
    acc.briefs.add(file.brief_id)
    acc.last = newer(acc.last, file.created_at)
    byUser.set(file.user_id, acc)
  }

  const out: ScopedUser[] = []
  for (const u of users) {
    if (f.userId && u.user_id !== f.userId) continue
    const acc = byUser.get(u.user_id)
    if (!acc) continue
    out.push({
      ...u,
      // Briefs they actually uploaded into — not briefs they merely accepted.
      brief_count: acc.briefs.size,
      file_count: acc.files,
      last_upload_at: acc.last,
    })
  }
  // Busiest first: the reason to open this tab is to see who is carrying the
  // work, so the answer should not need a click to sort.
  out.sort((a, z) => z.file_count - a.file_count || a.name.localeCompare(z.name))
  return out
}

/**
 * Briefs that have never received a single file, ever.
 *
 * Deliberately NOT windowed. A date range narrows to briefs that DID get work,
 * so counting "no work" inside one always yields zero. The submitter filter does
 * apply: "briefs this person accepted and never delivered on" is a real question.
 */
export function awaitingWork(
  briefs: ReportBriefRow[],
  allFiles: ReportFileRow[],
  f: Filters,
): number {
  const withFiles = new Set(
    allFiles.filter((x) => !f.userId || x.user_id === f.userId).map((x) => x.brief_id),
  )
  return briefs.filter((b) => {
    if (f.userId && !b.submitters.some((s) => s.user_id === f.userId)) return false
    return !withFiles.has(b.id)
  }).length
}

export function totalsFor(
  briefs: ScopedBrief[],
  users: ScopedUser[],
  files: ReportFileRow[],
  awaiting: number,
): Totals {
  return {
    brief_count: briefs.length,
    submission_count: briefs.reduce((n, b) => n + b.submitter_count, 0),
    file_count: files.length,
    submitter_count: users.length,
    briefs_awaiting_work: awaiting,
  }
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function Tile({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: number
  hint?: string
  tone?: 'warn'
}) {
  return (
    <div className="rounded-lg border border-border bg-bg-secondary px-4 py-3">
      <div
        className={
          tone === 'warn'
            ? 'text-2xl font-semibold text-status-warning'
            : 'text-2xl font-semibold text-text-primary'
        }
      >
        {value}
      </div>
      <div className="mt-0.5 text-xs text-text-tertiary">{label}</div>
      {hint && <div className="mt-0.5 text-[11px] text-text-tertiary/70">{hint}</div>}
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium text-text-tertiary">
      {children}
    </th>
  )
}

function Td({ children }: { children: React.ReactNode }) {
  return <td className="px-3 py-2 align-top text-text-secondary">{children}</td>
}

function Table({ head, children }: { head: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[640px] border-collapse text-[13px]">
        <thead className="border-b border-border bg-bg-secondary">
          <tr>{head}</tr>
        </thead>
        <tbody className="divide-y divide-border">{children}</tbody>
      </table>
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <tr>
      <td colSpan={99} className="px-3 py-8 text-center text-text-tertiary">
        {children}
      </td>
    </tr>
  )
}

const TABS: { key: Tab; label: string }[] = [
  { key: 'summary', label: 'Summary' },
  { key: 'briefs', label: 'By brief' },
  { key: 'users', label: 'By user' },
  { key: 'files', label: 'Files' },
]

export function ReportsView({ data }: { data: ReportPayload }) {
  const [tab, setTab] = useState<Tab>('summary')
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)

  const scoped = useMemo(() => scopeFiles(data.files, filters), [data.files, filters])
  const briefs = useMemo(() => scopeBriefs(data.briefs, scoped, filters), [data.briefs, scoped, filters])
  const users = useMemo(() => scopeUsers(data.users, scoped, filters), [data.users, scoped, filters])
  const awaiting = useMemo(
    () => awaitingWork(data.briefs, data.files, filters),
    [data.briefs, data.files, filters],
  )
  const totals = useMemo(
    () => totalsFor(briefs, users, scoped, awaiting),
    [briefs, users, scoped, awaiting],
  )

  // Search hides rows; it is applied here, after every count is settled.
  const q = filters.query
  const shownBriefs = briefs.filter((b) =>
    hits(`${b.title} ${b.home_path ?? ''} ${b.uploader_names.join(' ')}`, q),
  )
  const shownUsers = users.filter((u) => hits(`${u.name} ${u.email}`, q))
  const shownFiles = scoped.filter((f) => hits(`${f.name} ${f.brief_title} ${f.user_name}`, q))

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }))
  const dirty = JSON.stringify(filters) !== JSON.stringify(NO_FILTERS)
  const windowed = Boolean(filters.from || filters.to)

  const field =
    'rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-[13px] text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-border-focus'

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={filters.query}
          onChange={(e) => set({ query: e.target.value })}
          placeholder="Search briefs, people, files…"
          aria-label="Search"
          className={`${field} min-w-[220px] flex-1`}
        />
        <label className="text-xs text-text-tertiary">From</label>
        <input
          type="date"
          value={filters.from}
          onChange={(e) => set({ from: e.target.value })}
          aria-label="From date"
          className={field}
        />
        <label className="text-xs text-text-tertiary">To</label>
        <input
          type="date"
          value={filters.to}
          onChange={(e) => set({ to: e.target.value })}
          aria-label="To date"
          className={field}
        />
        <select
          value={filters.userId}
          onChange={(e) => set({ userId: e.target.value })}
          aria-label="Submitter"
          className={`${field} cursor-pointer`}
        >
          <option value="">Everyone</option>
          {data.users.map((u) => (
            <option key={u.user_id} value={u.user_id}>
              {u.name || u.email}
            </option>
          ))}
        </select>
        {dirty && (
          <button
            type="button"
            onClick={() => setFilters(NO_FILTERS)}
            className="rounded-md px-2 py-1.5 text-[13px] text-text-tertiary hover:text-text-primary"
          >
            Clear
          </button>
        )}
      </div>

      {windowed && (
        <p className="text-xs text-text-tertiary">
          Counting uploads between {filters.from || 'the beginning'} and {filters.to || 'today'}.
          Briefs with no uploads in that window are not listed.
        </p>
      )}

      <div className="flex items-center gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            aria-current={tab === t.key ? 'page' : undefined}
            className={
              tab === t.key
                ? '-mb-px border-b-2 border-text-primary px-3 py-2 text-[13px] font-medium text-text-primary'
                : '-mb-px border-b-2 border-transparent px-3 py-2 text-[13px] text-text-secondary hover:text-text-primary'
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'summary' && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Tile label="Briefs worked on" value={totals.brief_count} />
          <Tile label="New submissions" value={totals.submission_count} />
          <Tile label="Files" value={totals.file_count} />
          <Tile label="Submitters" value={totals.submitter_count} />
          <Tile
            label="Awaiting work"
            value={totals.briefs_awaiting_work}
            hint="all time"
            tone="warn"
          />
        </div>
      )}

      {tab === 'briefs' && (
        <Table
          head={
            <>
              <Th>Brief</Th>
              <Th>Folder</Th>
              <Th>Uploaded by</Th>
              <Th>Files</Th>
              <Th>Created</Th>
              <Th>Last upload</Th>
            </>
          }
        >
          {shownBriefs.length === 0 ? (
            <Empty>No briefs received files in this window.</Empty>
          ) : (
            shownBriefs.map((b) => (
              <tr key={b.id} className="hover:bg-bg-hover/40">
                <Td>
                  <span className="text-text-primary">{b.title}</span>
                  {!b.is_enabled && (
                    <span className="ml-2 rounded bg-bg-secondary px-1.5 py-0.5 text-[11px] text-text-tertiary">
                      disabled
                    </span>
                  )}
                </Td>
                <Td>{b.home_path || '—'}</Td>
                <Td>{b.uploader_names.join(', ') || '—'}</Td>
                <Td>{b.file_count}</Td>
                <Td>{fmtDate(b.created_at)}</Td>
                <Td>{fmtDate(b.last_upload_at)}</Td>
              </tr>
            ))
          )}
        </Table>
      )}

      {tab === 'users' && (
        <Table
          head={
            <>
              <Th>Person</Th>
              <Th>Email</Th>
              <Th>Briefs uploaded into</Th>
              <Th>Files</Th>
              <Th>Last upload</Th>
            </>
          }
        >
          {shownUsers.length === 0 ? (
            <Empty>Nobody uploaded anything in this window.</Empty>
          ) : (
            shownUsers.map((u) => (
              <tr key={u.user_id} className="hover:bg-bg-hover/40">
                <Td>
                  <span className="text-text-primary">{u.name || '—'}</span>
                </Td>
                <Td>{u.email}</Td>
                <Td>{u.brief_count}</Td>
                <Td>{u.file_count}</Td>
                <Td>{fmtDate(u.last_upload_at)}</Td>
              </tr>
            ))
          )}
        </Table>
      )}

      {tab === 'files' && (
        <Table
          head={
            <>
              <Th>File</Th>
              <Th>Brief</Th>
              <Th>Submitter</Th>
              <Th>Uploaded</Th>
            </>
          }
        >
          {shownFiles.length === 0 ? (
            <Empty>No files match these filters.</Empty>
          ) : (
            shownFiles.map((f) => (
              <tr key={f.asset_id} className="hover:bg-bg-hover/40">
                <Td>
                  <a
                    href={`/projects/${f.project_id}/assets/${f.asset_id}?from=/admin/reports`}
                    className="text-text-primary hover:underline"
                  >
                    {f.name}
                  </a>
                </Td>
                <Td>{f.brief_title}</Td>
                <Td>{f.user_name || '—'}</Td>
                <Td>{fmtDate(f.created_at)}</Td>
              </tr>
            ))
          )}
        </Table>
      )}
    </div>
  )
}
