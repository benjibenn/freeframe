'use client'

/**
 * Renders a structured JSON brief driven by an admin-configured template (Settings →
 * Brief template). The template is an ordered list of sections; each maps a dot-path in
 * the brief JSON to a render type (text / bullets / table). Deliberately defensive:
 * a section whose path resolves to nothing is skipped, so briefs and templates can
 * evolve independently without breaking the page.
 */

import useSWR from 'swr'

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

// `keys` is an optional ordered fallback list: the cell renders the first of these
// fields present on the row (non-empty), letting one column absorb field-name variants
// (e.g. an AI brief writer emitting `script` on one run, `script_voiceover` the next).
// Falls back to `key` when `keys` is absent, so older templates keep working.
export type BriefColumn = { key: string; header: string; keys?: string[] }
export type BriefSection = {
  id: string
  title: string
  path: string
  as: 'text' | 'bullets' | 'table'
  columns?: BriefColumn[]
}

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/** Walk a dot-path (e.g. "final_deliverable.label") into a value, or undefined. */
function resolvePath(root: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, key) => (isObj(acc) ? acc[key] : undefined), root)
}

// Public fetch (no auth) so the submit page renders briefs for guests too.
const fetchTemplate = (url: string): Promise<{ sections: BriefSection[] }> =>
  fetch(url).then((r) => (r.ok ? r.json() : { sections: [] }))

/** Shared template config, cached across every surface that renders a brief. */
export function useBriefTemplate() {
  const { data } = useSWR(`${API_URL}/brief-template`, fetchTemplate, {
    revalidateOnFocus: false,
  })
  return data?.sections ?? []
}

function Heading({ title }: { title: string }) {
  if (!title) return null
  return <h3 className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">{title}</h3>
}

/** First non-empty value across a column's candidate keys (aliases), as a string. */
function cellValue(row: Record<string, unknown>, col: BriefColumn): string {
  const keys = col.keys && col.keys.length > 0 ? col.keys : [col.key]
  for (const k of keys) {
    const v = row[k]
    if (v != null && String(v).trim() !== '') return String(v)
  }
  return ''
}

function TableBlock({ rows, columns }: { rows: Record<string, unknown>[]; columns: BriefColumn[] }) {
  const cols = columns.length > 0 ? columns : Object.keys(rows[0] ?? {}).map((k) => ({ key: k, header: k }))
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[36rem] border-collapse text-sm">
        <thead>
          <tr className="bg-bg-tertiary text-left text-xs text-text-tertiary">
            {cols.map((c) => (
              <th key={c.key} className="px-3 py-2 font-medium">{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-border align-top">
              {cols.map((c, j) => (
                <td
                  key={c.key}
                  className={j === 0 ? 'px-3 py-2.5 font-medium text-text-primary' : 'px-3 py-2.5 text-text-secondary'}
                >
                  {cellValue(row, c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Render one section; returns null when there's nothing to show (so no empty heading). */
function SectionBlock({ section, data }: { section: BriefSection; data: unknown }) {
  const value = resolvePath(data, section.path)

  if (section.as === 'text') {
    const text = typeof value === 'string' ? value : value == null ? '' : String(value)
    if (!text.trim()) return null
    return (
      <section className="flex flex-col gap-2">
        <Heading title={section.title} />
        <p className="text-sm leading-relaxed text-text-secondary">{text}</p>
      </section>
    )
  }

  if (section.as === 'bullets') {
    const items = Array.isArray(value) ? value.filter((x): x is string => typeof x === 'string' && !!x.trim()) : []
    if (items.length === 0) return null
    return (
      <section className="flex flex-col gap-2">
        <Heading title={section.title} />
        <ul className="flex flex-col gap-1.5">
          {items.map((rule, i) => (
            <li key={i} className="flex gap-2 text-sm text-text-secondary">
              <span className="mt-0.5 shrink-0 text-status-error">•</span>
              <span>{rule}</span>
            </li>
          ))}
        </ul>
      </section>
    )
  }

  // table
  const rows = Array.isArray(value) ? value.filter(isObj) : []
  if (rows.length === 0) return null
  return (
    <section className="flex flex-col gap-2">
      <Heading title={section.title} />
      <TableBlock rows={rows} columns={section.columns ?? []} />
    </section>
  )
}

export function BriefView({
  data,
  sectionsOverride,
}: {
  data: Record<string, unknown>
  /** Used by the admin builder's live preview to render an unsaved template. */
  sectionsOverride?: BriefSection[]
}) {
  const fetched = useBriefTemplate()
  const sections = sectionsOverride ?? fetched

  if (!isObj(data)) return null

  const title = typeof data.title === 'string' ? data.title : null
  const blocks = sections.map((s) => <SectionBlock key={s.id} section={s} data={data} />)

  return (
    <div className="flex flex-col gap-6">
      {title && <h2 className="text-lg font-semibold text-text-primary">{title}</h2>}
      {blocks}
    </div>
  )
}
