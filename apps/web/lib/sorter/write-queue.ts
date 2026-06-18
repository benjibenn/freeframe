// Serializes async writes that share a key (e.g. an assetId) so rapid keypresses
// can't issue overlapping read-modify-write tag calls for the same asset.
const chains = new Map<string, Promise<unknown>>()

export function enqueueWrite(key: string, task: () => Promise<void>): Promise<void> {
  const prev = chains.get(key) ?? Promise.resolve()
  // Chain regardless of whether the previous task rejected.
  const next = prev.catch(() => {}).then(task)
  chains.set(key, next)
  // Clean up the map once this is the tail, to avoid unbounded growth.
  next.finally(() => {
    if (chains.get(key) === next) chains.delete(key)
  })
  return next
}
