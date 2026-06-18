import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// Keep tag normalization in lockstep with the API's normalize_tags().
export function normalizeTag(raw: string): string {
  return raw.trim().toLowerCase().replace(/\s+/g, ' ').slice(0, 50)
}

interface SorterState {
  bindings: Record<string, Record<number, string>>
  seekStep: number
  setBinding: (projectId: string, slot: number, keyword: string) => void
  clearBinding: (projectId: string, slot: number) => void
  setSeekStep: (seconds: number) => void
}

export const useSorterStore = create<SorterState>()(
  persist(
    (set) => ({
      bindings: {},
      seekStep: 3,
      setBinding: (projectId, slot, keyword) =>
        set((s) => ({
          bindings: {
            ...s.bindings,
            [projectId]: { ...(s.bindings[projectId] ?? {}), [slot]: normalizeTag(keyword) },
          },
        })),
      clearBinding: (projectId, slot) =>
        set((s) => {
          const next = { ...(s.bindings[projectId] ?? {}) }
          delete next[slot]
          return { bindings: { ...s.bindings, [projectId]: next } }
        }),
      setSeekStep: (seconds) => set({ seekStep: seconds }),
    }),
    { name: 'freeframe-sorter-settings' },
  ),
)

export function getBindings(
  state: SorterState,
  projectId: string,
): Record<number, string> {
  return state.bindings[projectId] ?? {}
}
