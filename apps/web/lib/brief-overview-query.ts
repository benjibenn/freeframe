/**
 * The brief overview's filters, as the server reads them. The list is paged, so
 * every filter must run on the server: filtering what is loaded would hide
 * matches on a later page.
 */

export type OverviewFilters = {
  query: string
  /** Local calendar days from <input type="date">, YYYY-MM-DD. */
  from: string
  to: string
  withFiles: boolean
  userId: string
}

export const NO_FILTERS: OverviewFilters = { query: '', from: '', to: '', withFiles: false, userId: '' }

/** The filters as a query string (no leading '?'). Empty when nothing is set. */
export function overviewQuery(f: OverviewFilters): string {
  const qp = new URLSearchParams()
  const q = f.query.trim()
  if (q) qp.set('q', q)
  if (f.userId) qp.set('editor_id', f.userId)
  if (f.withFiles) qp.set('has_files', 'true')
  // The date inputs are local days; created_at is an instant. Send the instants
  // that bound those days in the viewer's timezone, end exclusive, so a brief
  // created that evening is not dropped.
  if (f.from) qp.set('created_from', new Date(`${f.from}T00:00:00`).toISOString())
  if (f.to) {
    const end = new Date(`${f.to}T00:00:00`)
    end.setDate(end.getDate() + 1)
    qp.set('created_to', end.toISOString())
  }
  return qp.toString()
}

/**
 * Every brief, 100 at a time. The playbook's coverage matrix counts across all
 * briefs, so it cannot work from one page, and the endpoint caps limit at 100.
 * Stops on an empty page so a total that disagrees cannot loop forever.
 */
export async function fetchAllBriefOverview<T>(
  get: (url: string) => Promise<{ items: T[]; total: number }>,
): Promise<T[]> {
  const rows: T[] = []
  for (;;) {
    const page = await get(`/brief-overview?limit=100&offset=${rows.length}`)
    rows.push(...page.items)
    if (page.items.length === 0 || rows.length >= page.total) return rows
  }
}
