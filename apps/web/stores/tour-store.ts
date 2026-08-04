import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { visibleSteps, type TourContext, type TourStep } from '@/components/tour/tour-steps'

interface TourStore {
  /** Whether the overlay is on screen right now. Never persisted — a reload
   *  should not drop someone back into a half-finished tour. */
  active: boolean
  stepIndex: number
  /** Set once the tour has been finished or skipped, so it only auto-starts
   *  for a genuinely new user. Persisted. */
  seen: boolean
  /** The project/asset this run walks through. Null until start. Never persisted. */
  ctx: TourContext | null
  /** Steps this run can actually reach — TOUR_STEPS minus unreachable asset steps. */
  steps: TourStep[]
  start: (ctx: TourContext) => void
  next: () => void
  back: () => void
  /** Jump forward to a step the user has navigated to. Never moves backwards. */
  jumpTo: (index: number) => void
  finish: () => void
}

export const useTourStore = create<TourStore>()(
  persist(
    (set, get) => ({
      active: false,
      stepIndex: 0,
      seen: false,
      ctx: null,
      steps: [],

      start: (ctx) => set({ active: true, stepIndex: 0, ctx, steps: visibleSteps(ctx) }),

      next: () => {
        const { stepIndex, steps } = get()
        if (stepIndex >= steps.length - 1) {
          set({ active: false, seen: true })
          return
        }
        set({ stepIndex: stepIndex + 1 })
      },

      back: () => set((s) => ({ stepIndex: Math.max(0, s.stepIndex - 1) })),

      jumpTo: (index) => set((s) => (index > s.stepIndex ? { stepIndex: index } : {})),

      finish: () => set({ active: false, seen: true }),
    }),
    {
      // Versioned key. `seen` lives in each browser's localStorage, so the only
      // way to re-show the tour to people who already dismissed it is to change
      // the key — old state becomes unreadable and everyone is new again, once.
      // Bumped when the tour was fixed from opening on the library step.
      name: 'ff-tour-v2',
      partialize: (state: TourStore) => ({ seen: state.seen }),
    },
  ),
)
