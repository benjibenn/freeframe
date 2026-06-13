'use client'

import * as React from 'react'

/**
 * Subscribe to a CSS media query. SSR-safe: returns `defaultValue` until the
 * component mounts, then reflects the real match and updates on change.
 *
 * Default is `true` (desktop-first) so the persistent sidebar renders correctly
 * on the server / first paint for the common desktop case; on mobile the drawer
 * starts closed, so the one-frame correction is never visible.
 */
export function useMediaQuery(query: string, defaultValue = true): boolean {
  const [matches, setMatches] = React.useState(defaultValue)

  React.useEffect(() => {
    const mql = window.matchMedia(query)
    const update = () => setMatches(mql.matches)
    update()
    mql.addEventListener('change', update)
    return () => mql.removeEventListener('change', update)
  }, [query])

  return matches
}

/** True at Tailwind's `md` breakpoint (≥768px) and up. */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 768px)')
}
