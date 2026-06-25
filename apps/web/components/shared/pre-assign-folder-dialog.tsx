'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { FolderPlus, X } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/shared/toast'

interface Project {
  id: string
  name: string
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function PreAssignFolderDialog({ open, onOpenChange }: Props) {
  const toast = useToast()
  const [email, setEmail] = React.useState('')
  const [folderName, setFolderName] = React.useState('')
  const [projectId, setProjectId] = React.useState('')
  const [projects, setProjects] = React.useState<Project[]>([])
  const [submitting, setSubmitting] = React.useState(false)

  React.useEffect(() => {
    if (!open) return
    api.get<Project[]>('/library/projects').then(setProjects).catch(() => {})
  }, [open])

  function reset() {
    setEmail('')
    setFolderName('')
    setProjectId('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim() || !folderName.trim() || !projectId) return
    setSubmitting(true)
    try {
      const result = await api.post<{ user_created: boolean; user_email: string }>('/admin/pre-assign-folder', {
        email: email.trim(),
        folder_name: folderName.trim(),
        project_id: projectId,
      })
      toast.success(
        result.user_created
          ? `Folder created. Account reserved for ${result.user_email} — they'll get access on first login.`
          : `Folder created and granted to ${result.user_email}.`,
      )
      reset()
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not create folder')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v) }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-bg-secondary shadow-xl p-6 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <div className="flex items-start justify-between gap-3 mb-5">
            <div>
              <Dialog.Title className="text-sm font-semibold text-text-primary">
                Pre-assign folder to email
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-text-tertiary">
                Creates the folder and grants access. If the email has no account yet, one is reserved and activated on first login.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button className="flex h-6 w-6 items-center justify-center rounded text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors">
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <Input
              label="Email"
              type="email"
              placeholder="editor@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
            <Input
              label="Folder name"
              placeholder="e.g. Brand Assets"
              value={folderName}
              onChange={(e) => setFolderName(e.target.value)}
              required
            />
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-secondary">Project</label>
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                required
                className="flex h-10 w-full rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
              >
                <option value="">Select a project…</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            <div className="flex justify-end gap-2 mt-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={submitting}>
                Cancel
              </Button>
              <Button type="submit" size="sm" loading={submitting}>
                <FolderPlus className="h-4 w-4" />
                Create &amp; assign
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
