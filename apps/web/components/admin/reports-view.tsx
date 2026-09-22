'use client'

/**
 * Four readings of one pipeline: totals, per brief, per person, per file.
 *
 * The filter bar sits ABOVE the tabs and applies to all of them, so switching tab
 * re-cuts the same question rather than starting a new one. Each tab filters its
 * own rows against its own natural date field — a brief by when it was created, a
 * file by when it was uploaded — instead of deriving every tab from the filtered
 * file list. That matters for one number in particular: "awaiting work" counts
 * briefs with no files, and briefs with no files vanish from a file-derived view.
 *
 * Pure props. The page owns fetching; this owns presentation.
 */

import { useMemo, useState } from 'react'

export type ReportTotals = {
  brief_count: number
  submission_count: number
  file_count: number
  submitter_count: number
  briefs_awaiting_work: number
}

export type ReportBriefRow = {
  id: string
  title: string
  home_path: string | null
  created_at: string
  is_enabled: boolean
  persona_label: string | null
  angle_label: string | null
  submission_count: number
  file_count: number
  submitter_ids: string[]
  submitter_names: string[]
  last_upload_at: string | null
}

export type ReportUserRow = {
  user_id: string
  name: string
  email: string
  brief_count: number
  file_count: number
  last_upload_at: string | null
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
  totals: ReportTotals
  briefs: ReportBriefRow[]
  users: ReportUserRow[]
  files: ReportFileRow[]
}

export type Filters = { query: string; from: string; to: string; userId: string }

export const NO_FILTERS: Filters = { query: '', from: '', to: '', userId: '' }

type Tab = 'summary' | 'briefs' | 'users' | 'files'

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

function inRange(iso: string | null, f: Filters): boolean {
  // A row with no date (nothing uploaded yet) survives an unset range and is
  // excluded by any set one — it cannot be claimed to fall inside a window.
  if (!f.from && !f.to) return true
  if (!iso) return false
  const day = localDay(iso)
  if (f.from && day < f.from) return false
  if (f.to && day > f.to) return false
  return true
}

function hits(haystack: string, query: string): boolean {
  const q = query.trim().toLowerCase()
  return !q || haystack.toLowerCase().includes(q)
}

export function filterBriefs(rows: ReportBriefRow[], f: Filters): ReportBriefRow[] {
  return rows.filter((r) => {
    if (f.userId && !r.submitter_ids.includes(f.userId)) return false
    if (!inRange(r.created_at, f)) return false
    // Search the line the admin can actually read: title, folder path, and who
    // is on it — not a single field they have to guess.
    return hits(`${r.title} ${r.home_path ?? ''} ${r.submitter_names.join(' ')}`, f.query)
  })
}

export function filterUsers(rows: ReportUserRow[], f: Filters): ReportUserRow[] {
  return rows.filter((r) => {
    if (f.userId && r.user_id !== f.userId) return false
    if (!inRange(r.last_upload_at, f)) return false
    return hits(`${r.name} ${r.email}`, f.query)
  })
}

export function filterFiles(rows: ReportFileRow[], f: Filters): ReportFileRow[] {
  return rows.filter((r) => {
    if (f.userId && r.user_id !== f.userId) return false
    if (!inRange(r.created_at, f)) return false
    return hits(`${r.name} ${r.brief_title} ${r.user_name}`, f.query)
  })
}

/**
 * Totals for what is currently on screen.
 *
 * Recomputed from the filtered rows rather than read off the payload: tiles that
 * kept showing platform-wide numbers while the tables below them were narrowed
 * would be actively misleading.
 */
export function visibleTotals(
  briefs: ReportBriefRow[],
  users: ReportUserRow[],
  files: ReportFileRow[],
): ReportTotals {
  return {
    brief_count: briefs.length,
    submission_count: briefs.reduce((n, b) => n + b.submission_count, 0),
    file_count: files.length,
    submitter_count: users.length,
    briefs_awaiting_work: briefs.filter((b) => b.file_count === 0).length,
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

function Tile({ label, value, tone }: { label: string; value: number; tone?: 'warn' }) {
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

  const briefs = useMemo(() => filterBriefs(data.briefs, filters), [data.briefs, filters])
  const users = useMemo(() => filterUsers(data.users, filters), [data.users, filters])
  const files = useMemo(() => filterFiles(data.files, filters), [data.files, filters])
  const totals = useMemo(() => visibleTotals(briefs, users, files), [briefs, users, files])

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }))
  const dirty = JSON.stringify(filters) !== JSON.stringify(NO_FILTERS)

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
          <Tile label="Briefs" value={totals.brief_count} />
          <Tile label="Submissions" value={totals.submission_count} />
          <Tile label="Files" value={totals.file_count} />
          <Tile label="Submitters" value={totals.submitter_count} />
          <Tile label="Awaiting work" value={totals.briefs_awaiting_work} tone="warn" />
        </div>
      )}

      {tab === 'briefs' && (
        <Table
          head={
            <>
              <Th>Brief</Th>
              <Th>Folder</Th>
              <Th>Submitters</Th>
              <Th>Files</Th>
              <Th>Created</Th>
              <Th>Last upload</Th>
            </>
          }
        >
          {briefs.length === 0 ? (
            <Empty>No briefs match these filters.</Empty>
          ) : (
            briefs.map((b) => (
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
                <Td>
                  {b.submission_count === 0 ? '—' : b.submitter_names.join(', ')}
                </Td>
                <Td>
                  <span className={b.file_count === 0 ? 'text-status-warning' : undefined}>
                    {b.file_count}
                  </span>
                </Td>
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
              <Th>Briefs</Th>
              <Th>Files</Th>
              <Th>Last upload</Th>
            </>
          }
        >
          {users.length === 0 ? (
            <Empty>No submitters match these filters.</Empty>
          ) : (
            users.map((u) => (
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
          {files.length === 0 ? (
            <Empty>No files match these filters.</Empty>
          ) : (
            files.map((f) => (
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
