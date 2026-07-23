export type SelectableItem = { kind: 'asset' | 'folder'; id: string }

/**
 * Inclusive slice of `items` between `anchor` and `target`, order-agnostic.
 * Used for shift-click range selection over the combined folders+assets list.
 * If either endpoint is missing from `items`, selects just the target.
 */
export function rangeBetween(
  items: SelectableItem[],
  anchor: SelectableItem,
  target: SelectableItem,
): SelectableItem[] {
  const key = (i: SelectableItem) => `${i.kind}:${i.id}`
  const ai = items.findIndex((i) => key(i) === key(anchor))
  const ti = items.findIndex((i) => key(i) === key(target))
  if (ai === -1 || ti === -1) return [target]
  const [lo, hi] = ai <= ti ? [ai, ti] : [ti, ai]
  return items.slice(lo, hi + 1)
}
