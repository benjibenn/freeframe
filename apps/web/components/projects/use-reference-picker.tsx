'use client'

import * as React from 'react'
import useSWR from 'swr'
import { Film, Image as ImageIcon, X } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  ReferencePickerDialog,
  type PickedReference,
  type ReferenceLibrary,
} from './reference-picker-dialog'
import type { AssetResponse } from '@/types'

/** Attach one already-existing asset to a request as a reference. The server
 *  copies the object, so the source asset is never aliased or endangered. */
export const attachReferenceAsset = (linkId: string, assetId: string) =>
  api.post(`/submission-links/${linkId}/reference-from-asset`, { asset_id: assetId })

/** The configured default project for the picker. Null is normal — the picker
 *  falls back to the first project the user can read. */
export function useReferenceLibrary() {
  const { data } = useSWR<ReferenceLibrary | null>(
    '/references/library',
    () => api.get<ReferenceLibrary | null>('/references/library'),
    { shouldRetryOnError: false },
  )
  return data ?? null
}

/**
 * "Use existing" for brief forms whose request does not exist yet.
 *
 * A create form has no link id to attach to, so picks are held in state and
 * flushed by `attachAll` once the request has been created — mirroring how the
 * same forms already defer their file uploads until after creation.
 */
export function useDeferredReferences() {
  const [picked, setPicked] = React.useState<PickedReference[]>([])

  const add = (asset: AssetResponse, kind: 'video' | 'image') =>
    setPicked((prev) =>
      prev.some((p) => p.id === asset.id)
        ? prev
        : [...prev, { id: asset.id, name: asset.name, kind }],
    )

  const remove = (id: string) => setPicked((prev) => prev.filter((p) => p.id !== id))

  /** Attach every held pick to a freshly created request, in pick order. */
  const attachAll = async (linkId: string) => {
    for (const p of picked) {
      await attachReferenceAsset(linkId, p.id)
    }
    setPicked([])
  }

  return { picked, add, remove, attachAll, reset: () => setPicked([]) }
}

/** The chips a create form shows for picks not yet attached. */
export function PickedReferenceChips({
  picked,
  kind,
  onRemove,
}: {
  picked: PickedReference[]
  kind: 'video' | 'image'
  onRemove: (id: string) => void
}) {
  const mine = picked.filter((p) => p.kind === kind)
  if (!mine.length) return null

  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {mine.map((p) => (
        <span
          key={p.id}
          className="inline-flex max-w-[220px] items-center gap-1 rounded bg-bg-tertiary px-1.5 py-0.5 text-xs text-text-secondary"
        >
          {kind === 'video' ? (
            <Film className="h-3 w-3 shrink-0" />
          ) : (
            <ImageIcon className="h-3 w-3 shrink-0" />
          )}
          <span className="truncate">{p.name}</span>
          <button
            type="button"
            onClick={() => onRemove(p.id)}
            aria-label={`Remove ${p.name}`}
            className="text-text-tertiary hover:text-status-error"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  )
}

/**
 * The "Use existing" button plus its dialog, as one unit.
 *
 * Every brief surface renders this next to its file input, so picking from
 * Freeframe and uploading a file sit side by side wherever references are set.
 */
export function UseExistingReferenceButton({
  kind,
  onPick,
  disabled,
  size = 'sm',
}: {
  kind: 'video' | 'image'
  onPick: (asset: AssetResponse) => Promise<void> | void
  disabled?: boolean
  size?: 'sm' | 'md'
}) {
  const [open, setOpen] = React.useState(false)
  const library = useReferenceLibrary()

  return (
    <>
      <Button variant="secondary" size={size} onClick={() => setOpen(true)} disabled={disabled} type="button">
        {kind === 'video' ? <Film className="h-4 w-4" /> : <ImageIcon className="h-4 w-4" />}
        Use existing
      </Button>
      {open && (
        <ReferencePickerDialog
          library={library}
          kind={kind}
          onClose={() => setOpen(false)}
          onPick={onPick}
        />
      )}
    </>
  )
}
