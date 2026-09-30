'use client'

/**
 * Asks for the source link before a new version is uploaded.
 *
 * Every upload must say where the artwork lives — the API requires it and keeps
 * it as the version's first comment (apps/api/services/source_link.py). On the
 * project page the field sits in the upload dialog; a new version has no dialog,
 * it starts the moment a file is picked, so this stands in for one.
 *
 * A revision is usually a different Figma frame, which is why it is asked again
 * per version rather than inherited from v1.
 */

import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'

export function SourceLinkPrompt({
  fileName,
  onCancel,
  onConfirm,
}: {
  fileName: string
  onCancel: () => void
  onConfirm: (sourceUrl: string) => void
}) {
  const [value, setValue] = useState('')
  const ready = value.trim().length > 0

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onCancel()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-bg-primary p-5 shadow-xl"
        >
          <Dialog.Title className="text-base font-semibold text-text-primary">
            Where was this made?
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-text-secondary">
            {fileName} — paste the Figma or Canva link. It is saved as the version&apos;s first
            comment so the next person can open the working file.
          </Dialog.Description>
          <form
            className="mt-4 flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              if (ready) onConfirm(value.trim())
            }}
          >
            <input
              autoFocus
              type="text"
              aria-label="Source link"
              placeholder="https://figma.com/file/…"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="h-10 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onCancel}
                className="h-8 rounded-md border border-border px-3 text-sm text-text-secondary hover:bg-bg-hover"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!ready}
                className="h-8 rounded-md bg-accent px-3 text-sm font-medium text-white disabled:opacity-50"
              >
                Upload
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
