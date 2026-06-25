'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { UserPlus, X } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/shared/toast'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  linkId: string
  onCreated?: () => void
}

export function PreAssignFolderDialog({ open, onOpenChange, linkId, onCreated }: Props) {
  const toast = useToast()
  const [email, setEmail] = React.useState('')
  const [displayName, setDisplayName] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)

  function reset() {
    setEmail('')
    setDisplayName('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setSubmitting(true)
    try {
      await api.post(`/submission-links/${linkId}/pre-create`, {
        email: email.trim(),
        display_name: displayName.trim() || null,
      })
      toast.success(`Slot created for ${email.trim()} — they'll see their project on first login.`)
      reset()
      onOpenChange(false)
      onCreated?.()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not create submission slot')
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
                Pre-assign submission slot
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-text-tertiary">
                Creates their project now. When they sign in, they land straight into it.
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
              label="Display name (optional)"
              placeholder="Defaults to their account name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
            <div className="flex justify-end gap-2 mt-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={submitting}>
                Cancel
              </Button>
              <Button type="submit" size="sm" loading={submitting}>
                <UserPlus className="h-4 w-4" />
                Create slot
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
