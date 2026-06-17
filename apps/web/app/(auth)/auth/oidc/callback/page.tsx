'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { setTokens } from '@/lib/auth'
import { useAuthStore } from '@/stores/auth-store'

/**
 * OIDC callback landing page.
 *
 * The API's /auth/oidc/callback redirects here with tokens in the URL fragment
 * (#access_token=...&refresh_token=...). Fragments never reach the server, so we
 * read them client-side, persist via setTokens (same as the magic-code flow),
 * then hand off to the dashboard.
 */
export default function OidcCallbackPage() {
  const router = useRouter()

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1))
    const access = params.get('access_token')
    const refresh = params.get('refresh_token')

    if (!access || !refresh) {
      router.replace('/login?error=sso_failed')
      return
    }

    setTokens(access, refresh)
    // Strip the tokens out of the URL/history so they aren't left in the bar.
    window.history.replaceState(null, '', window.location.pathname)

    // Only redirect to a same-origin path. `startsWith('/')` alone still admits
    // protocol-relative ("//evil.com") and backslash ("/\evil.com") URLs that
    // browsers resolve off-origin — an open redirect. Resolve against our own
    // origin and require it to match, then keep only the path portion.
    const from = params.get('from')
    let dest = '/projects'
    if (from) {
      try {
        const parsed = new URL(from, window.location.origin)
        if (parsed.origin === window.location.origin) {
          dest = parsed.pathname + parsed.search + parsed.hash
        }
      } catch {
        // malformed `from` — fall back to the default destination
      }
    }
    useAuthStore
      .getState()
      .fetchUser()
      .finally(() => router.replace(dest))
  }, [router])

  return (
    <div className="animate-slide-up text-center">
      <p className="text-sm text-text-secondary">Signing you in…</p>
    </div>
  )
}
