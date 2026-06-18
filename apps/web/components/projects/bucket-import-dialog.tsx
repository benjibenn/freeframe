'use client'

import * as React from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useToast } from '@/components/shared/toast'

interface BucketImportDialogProps {
  projectId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onImported?: () => void
}

interface ImportResult {
  imported: number
  skipped: number
  assets: { id: string; name: string }[]
}

export function BucketImportDialog({
  projectId,
  open,
  onOpenChange,
  onImported,
}: BucketImportDialogProps) {
  const [prefix, setPrefix] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const toast = useToast()

  // Reset on open
  React.useEffect(() => {
    if (open) {
      setPrefix('')
      setLoading(false)
    }
  }, [open])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      const result = await api.post<ImportResult>(
        `/projects/${projectId}/import/bucket`,
        { prefix: prefix.trim(), folder_id: null },
      )
      toast.success(`Imported ${result.imported}, skipped ${result.skipped}`)
      onImported?.()
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-bg-secondary shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Description className="sr-only">
            Import assets from a bucket prefix into this project.
          </Dialog.Description>

          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <Dialog.Title className="text-sm font-semibold text-text-primary">
              Import from Bucket
            </Dialog.Title>
            <Dialog.Close className="text-text-tertiary hover:text-text-primary transition-colors">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {/* Content */}
          <form onSubmit={handleSubmit}>
            <div className="px-5 py-4 space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-text-secondary">
                  S3 / Backblaze prefix
                </label>
                <input
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                  placeholder="incoming/"
                  disabled={loading}
                  className="flex h-9 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent disabled:opacity-50"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end border-t border-border px-5 py-3 gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => onOpenChange(false)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" size="sm" loading={loading} disabled={loading || !prefix.trim()}>
                Import
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
