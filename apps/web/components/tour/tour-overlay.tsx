'use client'

import * as React from 'react'
import { usePathname } from 'next/navigation'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { TOUR_STEPS, lookAheadIndex } from '@/components/tour/tour-steps'
import { useTourStore } from '@/stores/tour-store'
import { cn } from '@/lib/utils'

const CARD_WIDTH = 320
const GAP = 12
const EDGE = 12
/** Targets are re-measured on a timer as well as on scroll/resize: steps span
 *  pages, and elements appear from data loading, not just from layout. */
const POLL_MS = 250

function findTarget(key: string | null): HTMLElement | null {
  if (!key) return null
  return document.querySelector<HTMLElement>(`[data-tour="${key}"]`)
}

/** Where the card sits relative to the spotlight. Below when there's room,
 *  above otherwise, always clamped inside the viewport. */
function cardPosition(rect: DOMRect | null) {
  if (typeof window === 'undefined') return { top: 0, left: 0 }
  const vw = window.innerWidth
  const vh = window.innerHeight

  if (!rect) {
    return { top: Math.max(EDGE, vh / 2 - 120), left: Math.max(EDGE, vw / 2 - CARD_WIDTH / 2) }
  }

  const below = rect.bottom + GAP
  const fitsBelow = below + 200 < vh
  const top = fitsBelow ? below : Math.max(EDGE, rect.top - 200 - GAP)
  const left = Math.min(
    Math.max(EDGE, rect.left + rect.width / 2 - CARD_WIDTH / 2),
    vw - CARD_WIDTH - EDGE,
  )
  return { top, left }
}

export function TourOverlay() {
  const { active, stepIndex, next, back, jumpTo, finish } = useTourStore()
  const [rect, setRect] = React.useState<DOMRect | null>(null)
  const pathname = usePathname()

  const step = TOUR_STEPS[stepIndex]
  const isLast = stepIndex === TOUR_STEPS.length - 1

  // Auto-start once, on a project page — that's where a new submitter lands
  // after accepting a request link, and where step 1's target lives. The delay
  // covers both persist rehydration (`seen` reads false for a tick after a
  // reload) and the project's first data fetch, so `seen` is re-read on fire.
  React.useEffect(() => {
    if (!/^\/projects\/[^/]+/.test(pathname)) return
    const timer = window.setTimeout(() => {
      const state = useTourStore.getState()
      if (!state.seen && !state.active) state.start()
    }, 800)
    return () => window.clearTimeout(timer)
  }, [pathname])

  // Track the spotlight target. When the current step's element isn't on this
  // page, look ahead: if a later step's page-scoped element is present the user
  // has already navigated there, so follow them instead of stranding them on a
  // dead step. Steps targeting layout chrome are excluded — see lookAheadIndex.
  React.useEffect(() => {
    if (!active) return

    function measure() {
      const current = TOUR_STEPS[useTourStore.getState().stepIndex]
      const el = findTarget(current.target)
      if (el) {
        setRect(el.getBoundingClientRect())
        return
      }
      setRect(null)
      if (!current.target) return
      const ahead = lookAheadIndex(useTourStore.getState().stepIndex, (t) => !!findTarget(t))
      if (ahead !== -1) jumpTo(ahead)
    }

    measure()
    const timer = window.setInterval(measure, POLL_MS)
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [active, jumpTo])

  // Bring the target into view when the step changes.
  React.useEffect(() => {
    if (!active) return
    findTarget(TOUR_STEPS[stepIndex]?.target ?? null)?.scrollIntoView({
      block: 'center',
      behavior: 'smooth',
    })
  }, [active, stepIndex])

  React.useEffect(() => {
    if (!active) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') finish()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [active, finish])

  if (!active || !step) return null

  const { top, left } = cardPosition(rect)
  const waiting = !!step.target && !rect

  return (
    // pointer-events-none throughout: the tour never blocks the app, so a user
    // can actually do the thing the current step is describing.
    <div className="fixed inset-0 z-[60] pointer-events-none">
      {rect ? (
        <div
          className="absolute rounded-lg ring-2 ring-accent transition-all duration-200"
          style={{
            top: rect.top - 4,
            left: rect.left - 4,
            width: rect.width + 8,
            height: rect.height + 8,
            boxShadow: '0 0 0 9999px rgba(0,0,0,0.55)',
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-black/55" />
      )}

      <div
        role="dialog"
        aria-label={step.title}
        className="absolute pointer-events-auto rounded-xl border border-border bg-bg-secondary p-4 shadow-xl animate-in fade-in-0 zoom-in-95 duration-150"
        style={{ top, left, width: CARD_WIDTH }}
      >
        <button
          onClick={finish}
          className="absolute right-3 top-3 text-text-tertiary hover:text-text-primary transition-colors"
          aria-label="Skip tour"
        >
          <X className="h-4 w-4" />
        </button>

        <h2 className="pr-6 text-sm font-semibold text-text-primary">{step.title}</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-secondary">{step.body}</p>

        {waiting && step.waitingFor && (
          <p className="mt-2 rounded-md bg-bg-tertiary px-2.5 py-1.5 text-xs text-text-tertiary">
            {step.waitingFor}
          </p>
        )}

        <div className="mt-4 flex items-center justify-between">
          <div className="flex items-center gap-1.5" aria-label={`Step ${stepIndex + 1} of ${TOUR_STEPS.length}`}>
            {TOUR_STEPS.map((s, i) => (
              <span
                key={s.id}
                className={cn(
                  'h-1.5 w-1.5 rounded-full transition-colors',
                  i === stepIndex ? 'bg-accent' : 'bg-border',
                )}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            {stepIndex > 0 && (
              <Button variant="secondary" size="sm" onClick={back}>
                Back
              </Button>
            )}
            <Button size="sm" onClick={next}>
              {isLast ? 'Done' : 'Next'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
