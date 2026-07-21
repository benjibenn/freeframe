'use client'

import { useEffect, useState, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import { getAccessToken } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { BriefView } from '@/components/projects/brief-view'

interface SubmissionLinkPublic {
  title: string
  instructions: string | null
  requires_auth: boolean
  has_brief: boolean
  has_reference_video: boolean
  brief_json: Record<string, unknown> | null
  persona_label: string | null
  angle_label: string | null
  problem: string | null
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

  const hasBriefJson = !!link?.brief_json || !!link?.has_reference_video

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary px-4 py-8">
      <div
        className={`w-full rounded-xl border border-border bg-bg-secondary p-6 sm:p-8 ${
          hasBriefJson ? 'max-w-3xl' : 'max-w-md'
        }`}
      >
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
            {(link.persona_label || link.angle_label || link.problem) && (
              <p className="mb-3 text-xs text-text-tertiary">
                Campaign:{' '}
                {[
                  link.persona_label,
                  link.angle_label,
                  link.problem ? `Problem: ${link.problem}` : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            )}
            <p className="mb-6 text-sm text-text-secondary">
              {link.instructions ||
                'Sign in or create an account to upload your submission. Your uploads stay private — only you and the project owner can see them.'}
            </p>
            {link.has_brief && (
              <a
                href={`${process.env.NEXT_PUBLIC_API_URL || ''}/submit/${token}/brief.pdf`}
                target="_blank"
                rel="noopener noreferrer"
                className="mb-6 inline-flex items-center gap-2 text-sm text-accent hover:underline"
              >
                📄 View brief (PDF)
              </a>
            )}
            {link.has_reference_video && (
              <div className="mb-6">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-tertiary">Reference video</p>
                <video
                  controls
                  playsInline
                  preload="metadata"
                  src={`${process.env.NEXT_PUBLIC_API_URL || ''}/submit/${token}/reference-video`}
                  className="w-full rounded-lg border border-border bg-black"
                  controlsList="nodownload noremoteplayback"
                  disablePictureInPicture
                  onContextMenu={(e) => e.preventDefault()}
                />
              </div>
            )}
            {link.brief_json && (
              <div className="mb-6 rounded-lg border border-border bg-bg-primary p-4 sm:p-5">
                <BriefView data={link.brief_json} />
              </div>
            )}
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
