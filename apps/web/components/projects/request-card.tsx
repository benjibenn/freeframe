'use client'

import * as React from 'react'
import Link from 'next/link'
import { FolderGit2, Copy, Check, Trash2, Users } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface VideoRequest {
  id: string
  token: string
  title: string
  instructions: string | null
  is_enabled: boolean
  expires_at: string | null
  created_at: string
  submission_count: number
  has_brief?: boolean
  has_brief_json?: boolean
  has_reference_video?: boolean
  brief_json?: Record<string, unknown> | null
  reference_project_id?: string | null
  // CF campaign labels (null for hand-made requests).
  persona_label?: string | null
  angle_label?: string | null
  problem?: string | null
}

function submitUrl(token: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}/submit/${token}`
}

/**
 * Folder-style card representing a "video request" (a submission link). Clicking it
 * opens the request detail page where the per-editor submissions live as sub-cards.
 */
export function RequestCard({
  request,
  onDelete,
  className,
}: {
  request: VideoRequest
  onDelete?: (id: string) => void
  className?: string
}) {
  const [copied, setCopied] = React.useState(false)

  const copy = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(submitUrl(request.token))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }

  const count = request.submission_count

  return (
    <div className={cn('group relative', className)}>
      <Link
        href={`/projects/requests/${request.id}`}
        className="block rounded-xl overflow-hidden bg-bg-secondary border border-border hover:border-accent/40 transition-all duration-200 hover:shadow-lg hover:shadow-black/10"
      >
        <div className="relative aspect-square w-full overflow-hidden bg-gradient-to-br from-indigo-600 to-sky-500">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_40%,rgba(255,255,255,0.12),transparent_60%)]" />
          <div className="absolute inset-0 flex items-center justify-center">
            <FolderGit2 className="h-14 w-14 text-white/85 drop-shadow" />
          </div>

          {/* Bottom gradient + title */}
          <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/70 via-black/30 to-transparent" />
          <div className="absolute inset-x-0 bottom-0 p-3">
            <p className="text-sm font-semibold text-white line-clamp-2 drop-shadow-sm">
              {request.title}
            </p>
          </div>

          {/* Submitter count badge */}
          <span className="absolute top-2.5 left-2.5 inline-flex items-center gap-1 rounded-full bg-black/30 backdrop-blur-sm px-2 py-0.5 text-[10px] font-medium text-white/90">
            <Users className="h-2.5 w-2.5" />
            {count}
          </span>
          {!request.is_enabled && (
            <span className="absolute top-2.5 right-2.5 inline-flex items-center rounded-full bg-black/40 backdrop-blur-sm px-2 py-0.5 text-[10px] font-medium text-white/90">
              Closed
            </span>
          )}
        </div>

        <div className="flex items-center justify-between px-3 py-2.5">
          <span className="text-2xs text-text-tertiary">
            {count} submission{count !== 1 ? 's' : ''}
          </span>
        </div>
      </Link>

      {/* Copy link */}
      <button
        type="button"
        onClick={copy}
        title="Copy submission link"
        aria-label="Copy submission link"
        className="absolute bottom-2 right-2.5 flex h-7 w-7 items-center justify-center rounded-md text-text-tertiary hover:bg-bg-hover hover:text-text-primary transition-all opacity-0 group-hover:opacity-100"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-status-success" /> : <Copy className="h-3.5 w-3.5" />}
      </button>

      {onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onDelete(request.id)
          }}
          title="Close request"
          aria-label="Close request"
          className="absolute bottom-2 right-10 flex h-7 w-7 items-center justify-center rounded-md text-text-tertiary hover:bg-status-error/10 hover:text-status-error transition-all opacity-0 group-hover:opacity-100"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}
