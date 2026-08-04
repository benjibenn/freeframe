'use client'

import * as React from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import * as Dialog from '@radix-ui/react-dialog'
import { FileText, Plus, Users, X } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/shared/toast'
import type { VideoRequest } from './request-card'

const LINKS_KEY = '/submission-links'

/**
 * The requests filed in the folder you are currently looking at, plus a way to
 * create one right here.
 *
 * Requests used to live only on the projects index, disconnected from the folder
 * tree, so "which briefs are for this product?" had no answer anywhere. Filing is
 * pre-filled from the current folder — the whole point of creating it in place.
 */
export function FolderRequests({
  projectId,
  folderId,
  folderName,
  canCreate,
}: {
  projectId: string
  folderId: string | null
  folderName: string
  canCreate: boolean
}) {
  const toast = useToast()
  const { data: all, mutate } = useSWR<VideoRequest[]>(LINKS_KEY, () =>
    api.get<VideoRequest[]>(LINKS_KEY),
  )

  const requests = React.useMemo(
    () =>
      (all ?? []).filter(
        (r) => r.home_project_id === projectId && (r.home_folder_id ?? null) === folderId,
      ),
    [all, projectId, folderId],
  )

  const [open, setOpen] = React.useState(false)
  const [title, setTitle] = React.useState('')
  const [instructions, setInstructions] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState('')

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
      await mutate()
      setOpen(false)
      setTitle('')
      setInstructions('')
      toast.success(`Request created in ${folderName}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the request.')
    } finally {
      setSaving(false)
    }
  }

  // Nothing filed here and no way to add: render nothing rather than an empty box.
  if (requests.length === 0 && !canCreate) return null

  return (
    <div className="mb-4 rounded-xl border border-border">
      <div className="flex items-center gap-2 border-b border-border bg-bg-secondary px-3 py-2">
        <FileText className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
        <span className="text-xs font-medium text-text-secondary">
          Requests in {folderName}
        </span>
        <span className="text-xs text-text-tertiary">{requests.length}</span>
        {canCreate && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="ml-auto flex shrink-0 items-center gap-1 rounded px-2 py-0.5 text-xs text-accent hover:bg-bg-hover"
          >
            <Plus className="h-3 w-3" />
            New request here
          </button>
        )}
      </div>

      {requests.length === 0 ? (
        <p className="px-3 py-2.5 text-xs text-text-tertiary">
          No requests filed here yet.
        </p>
      ) : (
        requests.map((r) => (
          <div
            key={r.id}
            className="flex items-center gap-3 border-b border-border/60 px-3 py-2 last:border-b-0 hover:bg-bg-hover/40"
          >
            <Link
              href={`/projects/requests/${r.id}`}
              className="min-w-0 flex-1 truncate text-sm text-text-primary hover:text-accent"
            >
              {r.title}
            </Link>
            {(r.has_brief || r.has_brief_json) && (
              <FileText className="h-3.5 w-3.5 shrink-0 text-text-tertiary" aria-label="Has a brief" />
            )}
            <span className="flex shrink-0 items-center gap-1 text-xs text-text-tertiary">
              <Users className="h-3 w-3" />
              {r.submission_count}
            </span>
          </div>
        ))
      )}

      <Dialog.Root open={open} onOpenChange={setOpen}>
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
    </div>
  )
}
