/**
 * Pure helpers behind the playbook view: turn brief-overview rows into a
 * persona × angle coverage matrix and a brief table grouped by model or by brief.
 *
 * "Model" is the first folder below the chosen scope (a brand folder holds one
 * subfolder per phone model), so it needs no tenant-specific title codes.
 * "Brief" is the hook in the title convention
 *   date - model - persona - lens - hook - format
 * which is what the same brief shares across every model it was cloned to.
 */

export const NO_MODEL = 'No model'
export const NONE = '—'

export type PlaybookSource = {
  id: string
  token: string
  title: string
  home_path: string | null
  persona_label: string | null
  angle_label: string | null
  submission_count: number
  asset_count: number
}

export type PlaybookBrief = {
  id: string
  title: string
  url: string
  model: string
  name: string
  persona: string
  lens: string
  angle: string
  format: string
  submissions: number
  files: number
}

export type GroupBy = 'model' | 'brief'

/** Title parts; anything the title does not follow the convention for is null. */
export function parseTitle(title: string) {
  const parts = title.split(' - ').map((p) => p.trim())
  if (parts.length < 6) return { persona: null, lens: null, hook: null, format: null }
  return {
    persona: parts[2] || null,
    lens: parts[3] || null,
    // A hook may itself contain " - ": it is everything between lens and format.
    hook: parts.slice(4, -1).join(' - ') || null,
    format: parts[parts.length - 1] || null,
  }
}

function inScope(path: string | null, scope: string): path is string {
  return !!path && (path === scope || path.startsWith(`${scope}/`))
}

/** Every folder path that has at least one brief at or below it, with its count. */
export function scopes(rows: PlaybookSource[]): { path: string; count: number }[] {
  const counts = new Map<string, number>()
  for (const r of rows) {
    const segs = (r.home_path ?? '').split('/').filter(Boolean)
    for (let i = 1; i <= segs.length; i++) {
      const p = segs.slice(0, i).join('/')
      counts.set(p, (counts.get(p) ?? 0) + 1)
    }
  }
  return Array.from(counts).map(([path, count]) => ({ path, count })).sort((a, b) => natural(a.path, b.path))
}

/** The folders one level below `scope` ('' = the top level), each with its brief count. */
export function subfolders(rows: PlaybookSource[], scope: string): { path: string; name: string; count: number }[] {
  const depth = scope ? scope.split('/').length + 1 : 1
  return scopes(rows)
    .filter((f) => f.path.split('/').length === depth && (!scope || f.path.startsWith(`${scope}/`)))
    .map((f) => ({ ...f, name: f.path.split('/').pop()! }))
}

export function toBriefs(rows: PlaybookSource[], scope: string, origin: string): PlaybookBrief[] {
  return rows
    .filter((r) => inScope(r.home_path, scope))
    .map((r) => {
      const t = parseTitle(r.title)
      const below = r.home_path!.slice(scope.length).split('/').filter(Boolean)
      return {
        id: r.id,
        title: r.title,
        url: `${origin}/submit/${r.token}`,
        model: below[0] ?? NO_MODEL,
        name: t.hook ?? r.title,
        // A label set on the brief beats what the title says.
        persona: r.persona_label?.trim() || t.persona || NONE,
        lens: t.lens ?? NONE,
        angle: r.angle_label?.trim() || NONE,
        format: t.format ?? '',
        submissions: r.submission_count,
        files: r.asset_count,
      }
    })
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

/** Natural order, so "iPhone 9" sorts before "iPhone 17" and codes A2 before A10. */
export function natural(a: string, b: string): number {
  return collator.compare(a, b)
}

/** Placeholder buckets (no model, no label) always sort last. */
function headingOrder(a: string, b: string): number {
  const last = (s: string) => s === NO_MODEL || s === NONE
  return Number(last(a)) - Number(last(b)) || natural(a, b)
}

/**
 * Heading → briefs. By brief, names match case-insensitively and the heading
 * keeps the first spelling seen; the briefs inside are ordered by model.
 */
export function group(briefs: PlaybookBrief[], by: GroupBy): [string, PlaybookBrief[]][] {
  const groups = new Map<string, { heading: string; items: PlaybookBrief[] }>()
  for (const b of briefs) {
    const heading = by === 'model' ? b.model : b.name
    const key = heading.toLowerCase()
    const g = groups.get(key) ?? { heading, items: [] }
    g.items.push(b)
    groups.set(key, g)
  }
  return Array.from(groups.values())
    .map((g): [string, PlaybookBrief[]] => [
      g.heading,
      by === 'brief' ? [...g.items].sort((x, y) => natural(x.model, y.model)) : g.items,
    ])
    .sort(([a], [b]) => headingOrder(a, b))
}

/**
 * Clipboard text: one block per group, heading then one "label: link" line per
 * brief. The label is whatever the heading does not already say — the brief
 * name under a model, the model under a brief.
 */
export function copyText(briefs: PlaybookBrief[], by: GroupBy): string {
  return group(briefs, by)
    .map(([heading, items]) =>
      [heading, ...items.map((b) => `${by === 'model' ? b.name : b.model}: ${b.url}`)].join('\n'),
    )
    .join('\n\n')
}

export type Matrix = {
  personas: string[]
  angles: string[]
  cell: (persona: string, angle: string) => { total: number; withFiles: number }
}

export function matrix(briefs: PlaybookBrief[]): Matrix {
  const cells = new Map<string, { total: number; withFiles: number }>()
  for (const b of briefs) {
    const key = `${b.persona}\u0000${b.angle}`
    const c = cells.get(key) ?? { total: 0, withFiles: 0 }
    c.total++
    if (b.files > 0) c.withFiles++
    cells.set(key, c)
  }
  const distinct = (f: (b: PlaybookBrief) => string) => Array.from(new Set(briefs.map(f))).sort(headingOrder)
  return {
    personas: distinct((b) => b.persona),
    angles: distinct((b) => b.angle),
    cell: (p, a) => cells.get(`${p}\u0000${a}`) ?? { total: 0, withFiles: 0 },
  }
}
