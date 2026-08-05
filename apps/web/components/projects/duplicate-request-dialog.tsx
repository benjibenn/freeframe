'use client'

import * as React from 'react'
import useSWR from 'swr'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { languagesFromBrief, withLanguages } from '@/lib/sample-brief'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { HomePicker, type HomeValue } from './home-picker'
import type { VideoRequest } from './request-card'

interface LinkDetail extends VideoRequest {
  brief_json?: Record<string, unknown> | null
}

/**
 * Duplicate as a form, not a blind clone: every copyable field arrives pre-filled
 * from the source so the only required act is choosing where the copy lives.
 * Attachments (PDF, reference images/videos) can't sit in a file input, so they
 * are copied server-side and only summarised here.
 */
export function DuplicateRequestDialog({
  sourceId,
  open,
  onOpenChange,
  onDone,
}: {
  sourceId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone?: (homePath: string | null) => void
}) {
  const { data: source } = useSWR<LinkDetail>(
    open && sourceId ? `/submission-links/${sourceId}` : null,
    (key: string) => api.get<LinkDetail>(key),
  )

  const [title, setTitle] = React.useState('')
  const [instructions, setInstructions] = React.useState('')
  const [home, setHome] = React.useState<HomeValue>({ projectId: null, folderId: null })
  const [languages, setLanguages] = React.useState('')
  const [briefJson, setBriefJson] = React.useState('')
  const [loadedFor, setLoadedFor] = React.useState<string | null>(null)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState('')

  // Pre-fill once per source; reopening with another request re-fills.
  React.useEffect(() => {
    if (open && source && source.id !== loadedFor) {
      setTitle(`${source.title} (copy)`)
      setInstructions(source.instructions ?? '')
      setHome({
        projectId: source.home_project_id ?? null,
        folderId: source.home_folder_id ?? null,
      })
      setLanguages(languagesFromBrief(source.brief_json))
      setBriefJson(source.brief_json ? JSON.stringify(source.brief_json, null, 2) : '')
      setError('')
      setLoadedFor(source.id)
    }
  }, [open, source, loadedFor])

  React.useEffect(() => {
    if (!open) setLoadedFor(null)
  }, [open])

  const attachmentSummary = React.useMemo(() => {
    if (!source) return ''
    const parts: string[] = []
    if (source.has_brief) parts.push('brief PDF')
    const imgs = source.reference_image_count ?? 0
    const vids = source.reference_video_count ?? 0
    if (imgs > 0) parts.push(`${imgs} reference image${imgs === 1 ? '' : 's'}`)
    if (vids > 0) parts.push(`${vids} reference video${vids === 1 ? '' : 's'}`)
    return parts.join(', ')
  }, [source])

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!sourceId) return
    if (!title.trim()) {
      setError('Name is required.')
      return
    }
    if (!home.projectId) {
      setError('Choose where the copy is filed.')
      return
    }
    let parsedBrief: Record<string, unknown> | null = null
    if (briefJson.trim()) {
      try {
        parsedBrief = JSON.parse(briefJson)
      } catch {
        setError('Structured brief is not valid JSON.')
        return
      }
      if (typeof parsedBrief !== 'object' || parsedBrief === null || Array.isArray(parsedBrief)) {
        setError('Structured brief must be a JSON object.')
        return
      }
    }
    parsedBrief = withLanguages(parsedBrief, languages)
    setSaving(true)
    setError('')
    try {
      const created = await api.post<VideoRequest & { home_path?: string | null }>(
        `/submission-links/${sourceId}/duplicate`,
        {
          title: title.trim(),
          instructions: instructions.trim() || null,
          home_project_id: home.projectId,
          home_folder_id: home.folderId,
          brief_json: parsedBrief,
        },
      )
      onOpenChange(false)
      onDone?.(created.home_path ?? null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not duplicate the request.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[92vw] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-border bg-bg-primary p-5 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-base font-semibold text-text-primary">
                Duplicate request
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-secondary">
                Pre-filled from <span className="text-text-primary">{source?.title ?? '…'}</span>.
                Change anything before creating the copy.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                className="rounded-md p-1 text-text-tertiary hover:bg-bg-secondary hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {!source ? (
            <p className="mt-6 text-sm text-text-secondary">Loading request…</p>
          ) : (
            <form onSubmit={create} className="mt-5 space-y-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-text-secondary">Name</label>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
              </div>

              <div className="rounded-lg border border-border p-3">
                <HomePicker value={home} onChange={setHome} autoSelectSingleProject={false} />
                <p className="mt-2 text-xs text-text-tertiary">
                  Where the copy is filed — pre-set to the original&apos;s folder.
                </p>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-text-secondary">
                  Instructions <span className="font-normal text-text-tertiary">(optional)</span>
                </label>
                <textarea
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  rows={3}
                  className="w-full rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-text-secondary">
                  Output languages <span className="font-normal text-text-tertiary">(optional)</span>
                </label>
                <Input
                  value={languages}
                  onChange={(e) => setLanguages(e.target.value)}
                  placeholder="e.g. German, Swedish"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-text-secondary">
                  Structured brief <span className="font-normal text-text-tertiary">(JSON, optional)</span>
                </label>
                <textarea
                  value={briefJson}
                  onChange={(e) => setBriefJson(e.target.value)}
                  rows={8}
                  spellCheck={false}
                  className="w-full rounded-md border border-border bg-bg-secondary px-3 py-2 font-mono text-xs text-text-primary focus:outline-none focus:border-accent"
                />
              </div>

              {attachmentSummary && (
                <p className="text-xs text-text-tertiary">
                  Copied over automatically: {attachmentSummary}.
                </p>
              )}

              {error && <p className="text-sm text-status-error">{error}</p>}
              <div className="flex justify-end gap-2 pt-1">
                <Dialog.Close asChild>
                  <Button type="button" variant="secondary" size="sm">
                    Cancel
                  </Button>
                </Dialog.Close>
                <Button type="submit" size="sm" disabled={saving}>
                  {saving ? 'Creating…' : 'Create copy'}
                </Button>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
