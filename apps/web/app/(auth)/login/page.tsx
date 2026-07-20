'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { getAccessToken } from '@/lib/auth'
import { LoginForm } from '@/components/auth/login-form'
import type { SetupStatus } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Drop a stored token WITHOUT redirecting (unlike clearTokens, which navigates to
// /login and would strip the `from` param we need to preserve here).
function dropStaleToken() {
  localStorage.removeItem('ff_access_token')
  localStorage.removeItem('ff_refresh_token')
  document.cookie = 'ff_access_token=; path=/; max-age=0'
  document.cookie = 'ff_refresh_token=; path=/; max-age=0'
}

export default function LoginPage() {
  const router = useRouter()

  useEffect(() => {
    let cancelled = false

    async function run() {
      const token = getAccessToken()
      if (token) {
        // A token in localStorage is NOT proof of a live session — it may be stale
        // or expired. Validate it before redirecting, otherwise a public page that
        // bounces guests here (e.g. /submit, which stays requires_auth on a bad
        // token) creates an infinite /login ⇄ /submit loop. Raw fetch so the api
        // client's 401→refresh→clearTokens machinery (which would redirect and
        // drop `from`) never runs.
        try {
          const res = await fetch(`${API_URL}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          })
          if (cancelled) return
          if (res.ok) {
            document.cookie = `ff_access_token=${token}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`
            const from = new URLSearchParams(window.location.search).get('from')
            router.replace(from && from.startsWith('/') ? from : '/projects')
            return
          }
          // Rejected token — clear it and fall through to the login form.
          dropStaleToken()
        } catch {
          if (cancelled) return
          dropStaleToken()
        }
      }

      // Redirect to setup if first-time setup is needed.
      try {
        const status = await api.get<SetupStatus>('/setup/status')
        if (!cancelled && status.needs_setup) router.replace('/setup')
      } catch {
        // ignore — proceed to show login
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [router])

  return <LoginForm />
}
