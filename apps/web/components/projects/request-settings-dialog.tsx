'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/shared/toast'
import { HomePicker, type HomeValue } from './home-picker'
import type { VideoRequest } from './request-card'

/**
 * Edit a video request's own settings. Until now the request page could only
 * edit the submissions inside a request, never the request itself, so the
 * taxonomy path had nowhere to live.
 *
 * PATCH /submission-links/{id} replaces the whole record, so every field is sent
 * on save — omitting one would blank it server-side.
 */
export function RequestSettingsDialog({
  request,
  open,
  onOpenChange,
  onSaved,
}: {
  request: VideoRequest
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved?: () => void
}) {
  const toast = useToast()
  const [title, setTitle] = React.useState('')
  const [instructions, setInstructions] = React.useState('')
  const [home, setHome] = React.useState<HomeValue>({ projectId: null, folderId: null })
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState('')

  // Re-seed from the request each time it opens, so a cancelled edit doesn't
  // linger into the next one.
  React.useEffect(() => {
    if (open) {
      setTitle(request.title ?? '')
      setInstructions(request.instructions ?? '')
      setHome({
        projectId: request.home_project_id ?? null,
        folderId: request.home_folder_id ?? null,
      })
      setError('')
    }
  }, [open, request])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = title.trim()
    if (!trimmed) {
      setError('Title is required.')
      return
    }
    if (!home.projectId) {
      setError('Pick where this request is filed.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.patch(`/submission-links/${request.id}`, {
        title: trimmed,
        instructions: instructions.trim() || null,
        home_project_id: home.projectId,
        home_folder_id: home.folderId,
        expires_at: request.expires_at ?? null,
      })
      onSaved?.()
      onOpenChange(false)
      toast.success('Request updated')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save the request.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-bg-primary p-5 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-base font-semibold text-text-primary">
                Request settings
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-secondary">
                Applies to work submitted from now on.
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

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-secondary">Title</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-secondary">
                Instructions <span className="font-normal text-text-tertiary">(optional)</span>
              </label>
              <textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                rows={3}
                className="w-full rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
              />
            </div>

            <div className="border-t border-border pt-4">
              <HomePicker value={home} onChange={setHome} />
              <p className="mt-2 text-xs text-text-tertiary">
                Moving a request re-files it for work submitted from now on. Files already
                uploaded keep the path they were stamped with.
              </p>
            </div>

            {error && <p className="text-sm text-red-500">{error}</p>}

            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <Button type="button" variant="secondary" size="sm">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button type="submit" size="sm" disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
