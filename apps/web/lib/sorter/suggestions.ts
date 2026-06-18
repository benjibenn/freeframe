export interface TagCount {
  tag: string
  count: number
}

const MAX_SUGGESTIONS = 8

export function mergeSuggestions(
  projectTags: TagCount[],
  recent: string[],
  query: string,
  applied: string[],
): string[] {
  const q = query.trim().toLowerCase()
  const appliedSet = new Set(applied)
  const recentIndex = new Map(recent.map((t, i) => [t, i]))

  const byFreq = [...projectTags].sort((a, b) => b.count - a.count).map((t) => t.tag)
  // Union of recent + project tags, recent taking precedence, de-duplicated.
  const universe: string[] = []
  const seen = new Set<string>()
  for (const t of [...recent, ...byFreq]) {
    if (!seen.has(t)) { seen.add(t); universe.push(t) }
  }

  return universe
    .filter((t) => !appliedSet.has(t))
    .filter((t) => (q ? t.toLowerCase().includes(q) : true))
    .sort((a, b) => {
      const ra = recentIndex.has(a) ? recentIndex.get(a)! : Infinity
      const rb = recentIndex.has(b) ? recentIndex.get(b)! : Infinity
      if (ra !== rb) return ra - rb // recent first (lower index = more recent)
      return byFreq.indexOf(a) - byFreq.indexOf(b) // then frequency order
    })
    .slice(0, MAX_SUGGESTIONS)
}
