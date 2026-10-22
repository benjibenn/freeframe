'use client'

import * as React from 'react'

/**
 * The value, settled: it changes only once `delay` ms pass with no new value.
 *
 * For the project search box, where the raw input drives the field (so typing
 * stays instant) while the settled value drives the SWR key — otherwise every
 * keystroke is a new key, a new request, and a grid that flickers back to its
 * loading state mid-word.
 */
export function useDebounced<T>(value: T, delay = 250): T {
  const [settled, setSettled] = React.useState(value)

  React.useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return settled
}
