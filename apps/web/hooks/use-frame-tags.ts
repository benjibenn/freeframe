'use client'

import useSWR from 'swr'
import { api } from '@/lib/api'

export interface FrameTag {
  id: string
  asset_id: string
  version_id: string
  timecode_start: number
  timecode_end?: number
  label: string
  created_by: string
  created_at: string
}

function buildSWRKey(assetId: string | null, versionId: string | null): string | null {
  if (!assetId || !versionId) return null
  return `/assets/${assetId}/frame-tags?version_id=${versionId}`
}

export function useFrameTags(assetId: string | null, versionId: string | null) {
  const swrKey = buildSWRKey(assetId, versionId)

  const { data, error, isLoading, mutate } = useSWR<FrameTag[]>(
    swrKey,
    (key: string) => api.get<FrameTag[]>(key),
    { revalidateOnFocus: false },
  )

  const frameTags = data ?? []

  async function createFrameTag(timecodeStart: number, label: string, timecodeEnd?: number): Promise<FrameTag> {
    if (!assetId) throw new Error('No asset selected')
    if (!versionId) throw new Error('No version selected')
    const tag = await api.post<FrameTag>(`/assets/${assetId}/frame-tags`, {
      version_id: versionId,
      timecode_start: timecodeStart,
      timecode_end: timecodeEnd ?? null,
      label,
    })
    await mutate()
    return tag
  }

  async function deleteFrameTag(id: string): Promise<void> {
    await api.delete(`/frame-tags/${id}`)
    await mutate()
  }

  return { frameTags, isLoading, error, createFrameTag, deleteFrameTag, mutate }
}
