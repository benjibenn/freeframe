'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import useSWR, { mutate as globalMutate } from 'swr'
import * as Dialog from '@radix-ui/react-dialog'
import { X, FolderGit2, FolderOpen, Eye } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/shared/toast'
import type { VideoRequest } from './request-card'
import type { Project } from '@/types'

type Mode = 'new' | 'existing'
type Placement = 'folder' | 'reference'

export function ConvertToRequestDialog({
  project,
  open,
  onOpenChange,
  onDone,
}: {
  project: Project
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone?: () => void
}) {
  const router = useRouter()
  const toast = useToast()

  const { data: requests } = useSWR<VideoRequest[]>(
    open ? '/submission-links' : null,
    () => api.get<VideoRequest[]>('/submission-links'),
  )

  const [mode, setMode] = React.useState<Mode>('new')
  const [placement, setPlacement] = React.useState<Placement>('reference')
  const [targetId, setTargetId] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState('')

  React.useEffect(() => {
    if (open) {
      setMode('new')
      setPlacement('reference')
      setTargetId('')
      setError('')
    }
  }, [open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (mode === 'existing' && !targetId) {
      setError('Pick a request to add this project to.')
      return
    }
    setSubmitting(true)
    setError('')
    const asReference = placement === 'reference'
    try {
      let requestId = targetId
      if (mode === 'new') {
        const created = await api.post<{ id: string }>(
          `/submission-links/from-project/${project.id}`,
          { as_reference: asReference },
        )
        requestId = created.id
      } else {
        await api.post(`/submission-links/${targetId}/attach-project/${project.id}`, {
          as_reference: asReference,
        })
      }
      await Promise.all([globalMutate('/projects'), globalMutate('/submission-links')])
      onDone?.()
      onOpenChange(false)
      toast.success(
        mode === 'new' ? 'Created request from project' : 'Added project to request',
      )
      if (requestId) router.push(`/projects/requests/${requestId}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Could not complete the action')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-bg-secondary p-6 shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Close className="absolute right-4 top-4 text-text-tertiary hover:text-text-primary transition-colors">
            <X className="h-4 w-4" />
          </Dialog.Close>

          <Dialog.Title className="text-base font-semibold text-text-primary">
            Add to a request
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-text-secondary">
            Put “{project.name}” into a video request.
          </Dialog.Description>

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            {/* Target: new or existing */}
            <div className="grid grid-cols-2 gap-2">
              <ChoiceButton
                active={mode === 'new'}
                onClick={() => setMode('new')}
                icon={<FolderGit2 className="h-4 w-4" />}
                label="New request"
                hint="Create one named after this project"
              />
              <ChoiceButton
                active={mode === 'existing'}
                onClick={() => setMode('existing')}
                icon={<FolderOpen className="h-4 w-4" />}
                label="Existing request"
                hint="Add into one you already have"
              />
            </div>

            {mode === 'existing' && (
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-text-secondary">Request</label>
                <select
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
                >
                  <option value="">Select a request…</option>
                  {(requests ?? []).map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                    </option>
                  ))}
                </select>
                {(requests ?? []).length === 0 && (
                  <p className="text-xs text-text-tertiary">
                    No requests yet — use “New request”.
                  </p>
                )}
              </div>
            )}

            {/* Placement */}
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-text-secondary">Add as</label>
              <div className="grid grid-cols-2 gap-2">
                <ChoiceButton
                  active={placement === 'reference'}
                  onClick={() => setPlacement('reference')}
                  icon={<Eye className="h-4 w-4" />}
                  label="Shared reference"
                  hint="All editors can view it"
                />
                <ChoiceButton
                  active={placement === 'folder'}
                  onClick={() => setPlacement('folder')}
                  icon={<FolderOpen className="h-4 w-4" />}
                  label="Folder"
                  hint="Private child under the request"
                />
              </div>
            </div>

            {error && <p className="text-sm text-status-error">{error}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <Dialog.Close asChild>
                <Button type="button" variant="secondary" size="sm">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button type="submit" size="sm" loading={submitting}>
                {mode === 'new' ? 'Create request' : 'Add to request'}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function ChoiceButton({
  active,
  onClick,
  icon,
  label,
  hint,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
  hint: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors',
        active
          ? 'border-accent bg-accent/5'
          : 'border-border bg-bg-secondary hover:border-border-focus',
      )}
    >
      <span
        className={cn(
          'flex items-center gap-1.5 text-sm font-medium',
          active ? 'text-text-primary' : 'text-text-secondary',
        )}
      >
        {icon}
        {label}
      </span>
      <span className="text-2xs text-text-tertiary">{hint}</span>
    </button>
  )
}
