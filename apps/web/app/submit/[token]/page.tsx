'use client'

import { useEffect, useState, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import { getAccessToken } from '@/lib/auth'
import { Button } from '@/components/ui/button'

interface SubmissionLinkPublic {
  title: string
  instructions: string | null
  requires_auth: boolean
}

type Phase = 'loading' | 'needs_auth' | 'accepting' | 'error'

export default function SubmitPage() {
  const router = useRouter()
  const params = useParams<{ token: string }>()
  const token = params.token

  const [phase, setPhase] = useState<Phase>('loading')
  const [link, setLink] = useState<SubmissionLinkPublic | null>(null)
  const [error, setError] = useState('')
  const accepting = useRef(false)

  useEffect(() => {
    let cancelled = false

    async function run() {
      try {
        const info = await api.get<SubmissionLinkPublic>(`/submit/${token}`)
        if (cancelled) return
        setLink(info)

        // requires_auth reflects whether a valid bearer token was sent.
        if (info.requires_auth || !getAccessToken()) {
          setPhase('needs_auth')
          return
        }

        // Logged in — provision (or fetch) this user's private project and go.
        if (accepting.current) return
        accepting.current = true
        setPhase('accepting')
        const res = await api.post<{ project_id: string }>(`/submit/${token}/accept`)
        if (cancelled) return
        router.replace(`/projects/${res.project_id}`)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof ApiError ? err.detail : 'This submission link could not be opened.')
        setPhase('error')
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [token, router])

  const loginHref = `/login?from=${encodeURIComponent(`/submit/${token}`)}`

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary px-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-bg-secondary p-8">
        {phase === 'loading' && (
          <p className="text-center text-sm text-text-secondary">Loading…</p>
        )}

        {phase === 'accepting' && (
          <p className="text-center text-sm text-text-secondary">
            Setting up your private submission space…
          </p>
        )}

        {phase === 'needs_auth' && link && (
          <div className="animate-slide-up">
            <h1 className="mb-1 text-xl font-semibold text-text-primary">{link.title}</h1>
            <p className="mb-6 text-sm text-text-secondary">
              {link.instructions ||
                'Sign in or create an account to upload your submission. Your uploads stay private — only you and the project owner can see them.'}
            </p>
            <Button size="lg" className="w-full" onClick={() => router.push(loginHref)}>
              Sign in to submit
            </Button>
          </div>
        )}

        {phase === 'error' && (
          <div className="text-center">
            <h1 className="mb-1 text-xl font-semibold text-text-primary">Can’t open this link</h1>
            <p className="text-sm text-status-error">{error}</p>
          </div>
        )}
      </div>
    </div>
  )
}
