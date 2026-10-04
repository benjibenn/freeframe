import { vi } from 'vitest'

/** jsdom has no IntersectionObserver. This one does nothing until the test
 *  calls reveal(), which tells every observer its sentinel scrolled into view. */
export function stubIntersectionObserver() {
  const callbacks = new Set<IntersectionObserverCallback>()
  class StubObserver {
    private cb: IntersectionObserverCallback
    constructor(cb: IntersectionObserverCallback) {
      this.cb = cb
    }
    observe() {
      callbacks.add(this.cb)
    }
    disconnect() {
      callbacks.delete(this.cb)
    }
    unobserve() {}
    takeRecords() {
      return []
    }
  }
  vi.stubGlobal('IntersectionObserver', StubObserver)
  return {
    reveal() {
      // forEach rather than for..of/spread: the project's tsconfig has no
      // target set (defaults to ES3), which rejects Set iteration without
      // downlevelIteration (TS2802). forEach is a plain method call.
      callbacks.forEach((cb) => {
        cb([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
      })
    },
  }
}
