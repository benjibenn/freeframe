'use client'

import { useEffect } from 'react'
import { APP_TITLE } from '@/lib/constants'

/**
 * Sets the browser tab title. No brand suffix is appended — the page's own
 * title stands alone. Pass null/undefined to fall back to the generic title.
 */
export function usePageTitle(title: string | null | undefined) {
  useEffect(() => {
    document.title = title || APP_TITLE
    return () => { document.title = APP_TITLE }
  }, [title])
}
