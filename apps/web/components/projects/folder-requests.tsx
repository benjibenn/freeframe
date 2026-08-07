'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { uploadReferenceVideo } from '@/lib/reference-video'
import {
  UseExistingReferenceButton,
  PickedReferenceChips,
  useDeferredReferences,
} from '@/components/projects/use-reference-picker'
import { SAMPLE_BRIEF_JSON, languagesFromBrief, withLanguages } from '@/lib/sample-brief'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/shared/toast'
import type { VideoRequest } from './request-card'

export const LINKS_KEY = '/submission-links'

const SAMPLE_LANGUAGES = languagesFromBrief(JSON.parse(SAMPLE_BRIEF_JSON))

/**
 * Create a request already filed in the folder you are standing in — with the
 * same fields as the Submissions page, because a request made here is the same
 * thing made there. Filing is not asked for: it is taken from the current folder,
 * which is the whole point of creating one in place.
 *
 * The structured brief starts as the full sample rather than an empty box with a
 * hint — editing a concrete brief is faster than composing one from a schema.
 */
export function NewRequestDialog({
  projectId,
  folderId,
  folderName,
  open,
  onOpenChange,
  onCreated,
}: {
  projectId: string
  folderId: string | null
  folderName: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: () => void
}) {
  const toast = useToast()
  const [title, setTitle] = React.useState('')
  const [instructions, setInstructions] = React.useState('')
  const [briefFile, setBriefFile] = React.useState<File | null>(null)
  const [briefVideos, setBriefVideos] = React.useState<File[]>([])
  const refs = useDeferredReferences()
  const [briefImages, setBriefImages] = React.useState<File[]>([])
  const [languages, setLanguages] = React.useState(SAMPLE_LANGUAGES)
  const [briefJson, setBriefJson] = React.useState(SAMPLE_BRIEF_JSON)
  const [videoPct, setVideoPct] = React.useState<number | null>(null)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState('')

  React.useEffect(() => {
    if (open) {
      setTitle('')
      setInstructions('')
      setBriefFile(null)
      setBriefVideos([])
      setBriefImages([])
      setLanguages(SAMPLE_LANGUAGES)
      setBriefJson(SAMPLE_BRIEF_JSON)
      setVideoPct(null)
      setError('')
    }
  }, [open])

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = title.trim()
    if (!trimmed) {
      setError('Request name is required.')
      return
    }
    // Parse up front so a syntax error blocks creation instead of surfacing
    // after the link already exists.
    let parsedBrief: Record<string, unknown> | null = null
    if (briefJson.trim()) {
      try {
        parsedBrief = JSON.parse(briefJson)
      } catch {
        setError('Structured brief is not valid JSON. Clear the box if you don’t need one.')
        return
      }
      if (typeof parsedBrief !== 'object' || parsedBrief === null || Array.isArray(parsedBrief)) {
        setError('Structured brief must be a JSON object.')
        return
      }
    }
    // The dedicated languages input wins over whatever the JSON textarea carries.
    parsedBrief = withLanguages(parsedBrief, languages)
    setSaving(true)
    setError('')
    try {
      const link = await api.post<VideoRequest>(LINKS_KEY, {
        title: trimmed,
        instructions: instructions.trim() || null,
        home_project_id: projectId,
        home_folder_id: folderId,
      })
      // Attachments are separate endpoints (multipart / S3 presign), so they
      // follow the create rather than ride along in it — same as Submissions.
      if (briefFile && link?.id) {
        const fd = new FormData()
        fd.append('file', briefFile)
        await api.upload(`/submission-links/${link.id}/brief`, fd)
      }
      if (parsedBrief && link?.id) {
        await api.put(`/submission-links/${link.id}/brief-json`, { brief: parsedBrief })
      }
      if (link?.id) {
        for (const image of briefImages) {
          const fd = new FormData()
          fd.append('file', image)
          await api.upload(`/submission-links/${link.id}/reference-image`, fd)
        }
        for (const video of briefVideos) {
          setVideoPct(0)
          await uploadReferenceVideo(link.id, video, setVideoPct)
        }
        // Picked-from-Freeframe references attach after creation for the same
        // reason the files do: there is no link id until the request exists.
        await refs.attachAll(link.id)
      }
      onCreated?.()
      onOpenChange(false)
      toast.success(`Request created in ${folderName}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the request.')
    } finally {
      setSaving(false)
      setVideoPct(null)
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
                New request
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-secondary">
                Filed in <span className="text-text-primary">{folderName}</span>.
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

          <form onSubmit={create} className="mt-5 space-y-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-secondary">Request name</label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Denim Jacket - Static - Sale"
                autoFocus
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-secondary">
                Instructions <span className="font-normal text-text-tertiary">(optional)</span>
              </label>
              <textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                rows={3}
                placeholder="Shown to editors before they upload…"
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
              <p className="text-xs text-text-tertiary">
                Comma-separated. One deliverable per language — saved into the brief.
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-secondary">
                Brief PDF <span className="font-normal text-text-tertiary">(optional)</span>
              </label>
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => setBriefFile(e.target.files?.[0] ?? null)}
                className="text-sm text-text-secondary file:mr-3 file:rounded-md file:border file:border-border file:bg-bg-primary file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-text-secondary hover:file:bg-bg-hover"
              />
              <p className="text-xs text-text-tertiary">Editors can view it from the submission page.</p>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-secondary">
                Reference images <span className="font-normal text-text-tertiary">(optional)</span>
              </label>
              <input
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp,image/gif"
                onChange={(e) => setBriefImages(Array.from(e.target.files ?? []))}
                className="text-sm text-text-secondary file:mr-3 file:rounded-md file:border file:border-border file:bg-bg-primary file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-text-secondary hover:file:bg-bg-hover"
              />
              <div className="flex items-center gap-2">
                <UseExistingReferenceButton kind="image" onPick={(a) => refs.add(a, 'image')} />
                <span className="text-xs text-text-tertiary">or upload above</span>
              </div>
              <PickedReferenceChips picked={refs.picked} kind="image" onRemove={refs.remove} />
              <p className="text-xs text-text-tertiary">
                The static ads to adapt — shown as a carousel on the submission page.
                {briefImages.length > 1 && ` ${briefImages.length} selected.`}
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-secondary">
                Reference videos <span className="font-normal text-text-tertiary">(optional)</span>
              </label>
              <input
                type="file"
                multiple
                accept="video/*"
                onChange={(e) => setBriefVideos(Array.from(e.target.files ?? []))}
                className="text-sm text-text-secondary file:mr-3 file:rounded-md file:border file:border-border file:bg-bg-primary file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-text-secondary hover:file:bg-bg-hover"
              />
              <div className="flex items-center gap-2">
                <UseExistingReferenceButton kind="video" onPick={(a) => refs.add(a, 'video')} />
                <span className="text-xs text-text-tertiary">or upload above</span>
              </div>
              <PickedReferenceChips picked={refs.picked} kind="video" onRemove={refs.remove} />
              {videoPct !== null ? (
                <p className="text-xs text-text-tertiary">Uploading video… {videoPct}%</p>
              ) : (
                briefVideos.length > 1 && (
                  <p className="text-xs text-text-tertiary">{briefVideos.length} selected.</p>
                )
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-text-secondary">
                  Structured brief <span className="font-normal text-text-tertiary">(JSON, optional)</span>
                </label>
                <button
                  type="button"
                  onClick={() => setBriefJson('')}
                  className="text-xs text-accent hover:underline"
                >
                  Clear
                </button>
              </div>
              <textarea
                value={briefJson}
                onChange={(e) => setBriefJson(e.target.value)}
                rows={10}
                spellCheck={false}
                className="w-full rounded-md border border-border bg-bg-secondary px-3 py-2 font-mono text-xs text-text-primary focus:outline-none focus:border-accent"
              />
              <p className="text-xs text-text-tertiary">
                Starts as a sample static-ad brief — edit it to fit, or clear it if you don’t
                need one. It renders as a formatted brief on the submission page.
              </p>
            </div>

            {error && <p className="text-sm text-status-error">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <Button type="button" variant="secondary" size="sm">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button type="submit" size="sm" disabled={saving}>
                {saving ? 'Creating…' : 'Create request'}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
