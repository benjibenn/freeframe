export type SorterAction =
  | { kind: 'prev' } | { kind: 'next' }
  | { kind: 'seek'; delta: number }
  | { kind: 'togglePlay' }
  | { kind: 'slot'; slot: number }
  | { kind: 'applyAll' }
  | { kind: 'focusTag' } | { kind: 'filter' }
  | { kind: 'archive' } | { kind: 'undo' } | { kind: 'exit' }

export function keyToAction(key: string, seekStep: number): SorterAction | null {
  switch (key) {
    case 'ArrowUp': return { kind: 'prev' }
    case 'ArrowDown': return { kind: 'next' }
    case 'ArrowLeft': return { kind: 'seek', delta: -seekStep }
    case 'ArrowRight': return { kind: 'seek', delta: seekStep }
    case ' ': return { kind: 'togglePlay' }
    case 'a': return { kind: 'applyAll' }
    case 't': return { kind: 'focusTag' }
    case 'f': return { kind: 'filter' }
    case 'd': return { kind: 'archive' }
    case 'z': return { kind: 'undo' }
    case 'Escape': return { kind: 'exit' }
    default:
      if (/^[1-9]$/.test(key)) return { kind: 'slot', slot: Number(key) }
      return null
  }
}
