import * as React from 'react'

/** Nearest scrollable ancestor — the IntersectionObserver root. */
function getScrollParent(node: Element | null): Element | null {
  let el: Element | null = node?.parentElement ?? null
  while (el) {
    const overflowY = window.getComputedStyle(el).overflowY
    if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') {
      return el
    }
    el = el.parentElement
  }
  return null // falls back to the viewport
}

/**
 * Fires `onLoadMore` when the returned sentinel element scrolls into view.
 *
 * Dashboard pages scroll inside an inner `overflow-y-auto` container, not the
 * document, so the observer's root is auto-detected from the sentinel's nearest
 * scrollable ancestor — otherwise it would watch the viewport and never fire.
 * `rootMargin` pre-loads the next page before the user reaches the bottom.
 *
 * Pass `enabled: hasMore && !isLoadingMore` so we never queue duplicate loads
 * while a page is in flight.
 */
export function useInfiniteScroll({
  onLoadMore,
  enabled,
  rootMargin = '800px',
}: {
  onLoadMore: () => void
  enabled: boolean
  rootMargin?: string
}) {
  const sentinelRef = React.useRef<HTMLDivElement | null>(null)
  // Keep the latest callback without re-subscribing the observer every render.
  const onLoadMoreRef = React.useRef(onLoadMore)
  onLoadMoreRef.current = onLoadMore

  React.useEffect(() => {
    const node = sentinelRef.current
    if (!node || !enabled) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) onLoadMoreRef.current()
      },
      { root: getScrollParent(node), rootMargin },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [enabled, rootMargin])

  return sentinelRef
}
