'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/shared/toast'
import type { VideoRequest } from './request-card'

export const LINKS_KEY = '/submission-links'

/**
 * Create a request already filed in the folder you are standing in.
 *
 * Filing is not asked for — it is taken from the current folder, which is the
 * entire reason for creating one from in here rather than from the projects page.
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
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState('')

  React.useEffect(() => {
    if (open) {
      setTitle('')
      setInstructions('')
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
    setSaving(true)
    setError('')
    try {
      await api.post<VideoRequest>(LINKS_KEY, {
        title: trimmed,
        instructions: instructions.trim() || null,
        home_project_id: projectId,
        home_folder_id: folderId,
      })
      onCreated?.()
      onOpenChange(false)
      toast.success(`Request created in ${folderName}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the request.')
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
                placeholder="e.g. Static - iPhone 17e"
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
