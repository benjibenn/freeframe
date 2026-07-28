import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { TOUR_STEPS } from '@/components/tour/tour-steps'

interface TourStore {
  /** Whether the overlay is on screen right now. Never persisted — a reload
   *  should not drop someone back into a half-finished tour. */
  active: boolean
  stepIndex: number
  /** Set once the tour has been finished or skipped, so it only auto-starts
   *  for a genuinely new user. Persisted. */
  seen: boolean
  start: () => void
  next: () => void
  back: () => void
  /** Jump forward to a step whose target just appeared (see TourOverlay). Never
   *  moves backwards, so the tour can't loop when a user navigates back. */
  jumpTo: (index: number) => void
  finish: () => void
}

export const useTourStore = create<TourStore>()(
  persist(
    (set, get) => ({
      active: false,
      stepIndex: 0,
      seen: false,

      start: () => set({ active: true, stepIndex: 0 }),

      next: () => {
        const { stepIndex } = get()
        if (stepIndex >= TOUR_STEPS.length - 1) {
          set({ active: false, seen: true })
          return
        }
        set({ stepIndex: stepIndex + 1 })
      },

      back: () => set((s) => ({ stepIndex: Math.max(0, s.stepIndex - 1) })),

      jumpTo: (index) =>
        set((s) => (index > s.stepIndex ? { stepIndex: index } : {})),

      finish: () => set({ active: false, seen: true }),
    }),
    {
      name: 'ff-tour',
      partialize: (state: TourStore) => ({ seen: state.seen }),
    },
  ),
)
