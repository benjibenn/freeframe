'use client'

/**
 * Playbook view of one folder (a brand): persona × angle coverage, and the
 * brief table grouped by model or by brief with batch copy of submit links.
 *
 * Coverage counts briefs with at least one delivered file, not submissions:
 * an empty submission is not coverage. Pure props — the page owns fetching.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  copyText,
  group,
  matrix,
  NONE,
  subfolders,
  toBriefs,
  type GroupBy,
  type PlaybookBrief,
  type PlaybookSource,
} from '@/lib/playbook'

type Filters = { persona: string; angle: string; files: '' | 'yes' | 'no' }

const select =
  'h-8 rounded-md border border-border bg-bg-primary px-2 text-sm text-text-primary'
const button =
  'h-8 rounded-md border border-border px-2.5 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50'

export function PlaybookView({ rows, origin }: { rows: PlaybookSource[]; origin: string }) {
  const [scope, setScopeState] = useState('')
  const children = useMemo(() => subfolders(rows, scope), [rows, scope])
  const [filters, setFilters] = useState<Filters>({ persona: '', angle: '', files: '' })
  const [groupBy, setGroupBy] = useState<GroupBy | ''>('')
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [note, setNote] = useState('')

  const all = useMemo(() => (scope ? toBriefs(rows, scope, origin) : []), [rows, scope, origin])
  const grid = useMemo(() => matrix(all), [all])
  const shown = all.filter(
    (b) =>
      (!filters.persona || b.persona === filters.persona) &&
      (!filters.angle || b.angle === filters.angle) &&
      (!filters.files || (filters.files === 'yes' ? b.files > 0 : b.files === 0)),
  )
  const groups = groupBy ? group(shown, groupBy) : [['', shown] as [string, PlaybookBrief[]]]

  // The folder lives in ?folder= so a brand's view can be bookmarked and shared.
  useEffect(() => {
    setScopeState(new URLSearchParams(window.location.search).get('folder') ?? '')
  }, [])

  function setScope(path: string) {
    setScopeState(path)
    setFilters({ persona: '', angle: '', files: '' })
    setPicked(new Set())
    setNote('')
    const url = new URL(window.location.href)
    if (path) url.searchParams.set('folder', path)
    else url.searchParams.delete('folder')
    window.history.replaceState(null, '', url)
  }

  const crumbs = scope ? scope.split('/') : []

  const toggle = (ids: string[], on: boolean) =>
    setPicked((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => (on ? next.add(id) : next.delete(id)))
      return next
    })

  async function copy(briefs: PlaybookBrief[]) {
    const by = groupBy || 'model'
    await navigator.clipboard.writeText(copyText(briefs, by))
    const n = group(briefs, by).length
    setNote(`Copied ${briefs.length} link${briefs.length === 1 ? '' : 's'} across ${n} ${by}${n === 1 ? '' : 's'}.`)
  }

  const pickedBriefs = shown.filter((b) => picked.has(b.id))

  return (
    <div className="flex flex-col gap-5">
      <nav aria-label="Folder" className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1 text-sm">
          <button type="button" onClick={() => setScope('')}
            className={scope ? 'text-accent hover:underline' : 'font-medium text-text-primary'}>
            All folders
          </button>
          {crumbs.map((c, i) => {
            const path = crumbs.slice(0, i + 1).join('/')
            return (
              <span key={path} className="flex items-center gap-1">
                <span className="text-text-tertiary">/</span>
                <button type="button" onClick={() => setScope(path)}
                  className={path === scope ? 'font-medium text-text-primary' : 'text-accent hover:underline'}>
                  {c}
                </button>
              </span>
            )
          })}
        </div>
        {children.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {children.map((f) => (
              <button key={f.path} type="button" onClick={() => setScope(f.path)}
                className="rounded-full border border-border px-3 py-1 text-sm text-text-primary hover:bg-bg-hover">
                {f.name} <span className="text-xs text-text-tertiary">{f.count}</span>
              </button>
            ))}
          </div>
        )}
        {!scope && <p className="text-sm text-text-tertiary">Open a folder to see its playbook.</p>}
      </nav>

      {scope && (
        <>
          <p className="text-sm text-text-secondary">
            {all.length} briefs · {all.filter((b) => b.files > 0).length} with files ·{' '}
            {all.reduce((n, b) => n + b.files, 0)} files
          </p>

          {/* ── Coverage ──────────────────────────────────────────── */}
          <section>
            <h2 className="mb-2 text-sm font-semibold text-text-primary">
              Coverage — briefs with files / briefs
            </h2>
            <div className="overflow-x-auto">
              <table className="text-xs">
                <thead>
                  <tr>
                    <th className="px-2 py-1 text-left text-text-tertiary">Persona \ Angle</th>
                    {grid.angles.map((a) => (
                      <th key={a} className="px-2 py-1 text-text-tertiary">{a}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.personas.map((p) => (
                    <tr key={p}>
                      <th className="whitespace-nowrap px-2 py-1 text-left font-medium text-text-primary">{p}</th>
                      {grid.angles.map((a) => {
                        const c = grid.cell(p, a)
                        return (
                          <td key={a} className="px-0.5 py-0.5 text-center">
                            {c.total > 0 && (
                              <button
                                type="button"
                                onClick={() => setFilters((f) => ({ ...f, persona: p, angle: a }))}
                                title={`${p} × ${a}`}
                                className={`w-12 rounded px-1 py-0.5 ${
                                  c.withFiles > 0
                                    ? 'bg-status-success/15 text-status-success'
                                    : 'bg-status-error/10 text-status-error'
                                }`}
                              >
                                {c.withFiles}/{c.total}
                              </button>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* ── Briefs ────────────────────────────────────────────── */}
          <section className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <select aria-label="Persona" className={select} value={filters.persona}
                onChange={(e) => setFilters((f) => ({ ...f, persona: e.target.value }))}>
                <option value="">All personas</option>
                {grid.personas.map((p) => <option key={p}>{p}</option>)}
              </select>
              <select aria-label="Angle" className={select} value={filters.angle}
                onChange={(e) => setFilters((f) => ({ ...f, angle: e.target.value }))}>
                <option value="">All angles</option>
                {grid.angles.map((a) => <option key={a}>{a}</option>)}
              </select>
              <select aria-label="Files" className={select} value={filters.files}
                onChange={(e) => setFilters((f) => ({ ...f, files: e.target.value as Filters['files'] }))}>
                <option value="">Any files</option>
                <option value="yes">With files</option>
                <option value="no">No files</option>
              </select>
              <select aria-label="Group" className={select} value={groupBy}
                onChange={(e) => setGroupBy(e.target.value as GroupBy | '')}>
                <option value="">No grouping</option>
                <option value="model">Group by model</option>
                <option value="brief">Group by brief</option>
              </select>
              <button type="button" className={button} disabled={pickedBriefs.length === 0}
                onClick={() => copy(pickedBriefs)}>
                Copy {pickedBriefs.length || ''} selected by {groupBy || 'model'}
              </button>
              {note && <span role="status" className="text-xs text-text-tertiary">{note}</span>}
            </div>

            <table className="w-full text-sm">
              <thead className="text-left text-xs text-text-tertiary">
                <tr>
                  <th className="w-8 px-2 py-1">
                    <input type="checkbox" aria-label="Select all shown"
                      checked={shown.length > 0 && shown.every((b) => picked.has(b.id))}
                      onChange={(e) => toggle(shown.map((b) => b.id), e.target.checked)} />
                  </th>
                  <th className="px-2 py-1">Brief</th>
                  <th className="px-2 py-1">Persona</th>
                  <th className="px-2 py-1">Lens</th>
                  <th className="px-2 py-1">Angle</th>
                  <th className="px-2 py-1 text-right">Files</th>
                  <th className="px-2 py-1 text-right">Subs</th>
                  <th className="px-2 py-1">Model</th>
                </tr>
              </thead>
              {groups.map(([heading, items]) => (
                <tbody key={heading || 'all'} className="border-t border-border">
                  {heading && (
                    <tr className="bg-bg-secondary">
                      <td className="px-2 py-1">
                        <input type="checkbox" aria-label={`Select ${heading}`}
                          checked={items.every((b) => picked.has(b.id))}
                          onChange={(e) => toggle(items.map((b) => b.id), e.target.checked)} />
                      </td>
                      <td colSpan={7} className="px-2 py-1 font-medium text-text-primary">
                        {heading} <span className="text-xs text-text-tertiary">({items.length})</span>
                        <button type="button" className="ml-3 text-xs text-accent hover:underline"
                          onClick={() => copy(items)}>
                          Copy links
                        </button>
                      </td>
                    </tr>
                  )}
                  {items.map((b) => (
                    <tr key={b.id} className="border-t border-border/50">
                      <td className="px-2 py-1">
                        <input type="checkbox" aria-label={`Select ${b.title}`} checked={picked.has(b.id)}
                          onChange={(e) => toggle([b.id], e.target.checked)} />
                      </td>
                      <td className="px-2 py-1">
                        <a href={b.url} target="_blank" rel="noopener noreferrer" className="text-text-primary hover:underline">
                          {b.name}
                        </a>
                        {b.format && <span className="block text-xs text-text-tertiary">{b.format}</span>}
                      </td>
                      <td className="px-2 py-1 text-text-secondary">{b.persona}</td>
                      <td className="px-2 py-1 text-text-secondary">{b.lens}</td>
                      <td className={`px-2 py-1 ${b.angle === NONE ? 'text-text-tertiary' : 'text-text-secondary'}`}>{b.angle}</td>
                      <td className={`px-2 py-1 text-right ${b.files > 0 ? 'text-status-success' : 'text-status-error'}`}>{b.files}</td>
                      <td className="px-2 py-1 text-right text-text-tertiary">{b.submissions}</td>
                      <td className="px-2 py-1 text-xs text-text-tertiary">{b.model}</td>
                    </tr>
                  ))}
                </tbody>
              ))}
            </table>
            {shown.length === 0 && <p className="px-2 py-4 text-sm text-text-tertiary">No briefs match.</p>}
          </section>
        </>
      )}
    </div>
  )
}
