'use client'

import useSWR from 'swr'
import { api } from '@/lib/api'

export interface PaletteTag {
  id: string
  project_id: string
  label: string
  color: string
  position: number
}

export function useTagPalette(projectId: string | null) {
  const swrKey = projectId ? `/projects/${projectId}/tag-palette` : null

  const { data, error, isLoading, mutate } = useSWR<PaletteTag[]>(
    swrKey,
    (key: string) => api.get<PaletteTag[]>(key),
    { revalidateOnFocus: false },
  )

  const palette = data ?? []

  async function createLabel(label: string, color?: string): Promise<PaletteTag> {
    if (!projectId) throw new Error('No project selected')
    const tag = await api.post<PaletteTag>(`/projects/${projectId}/tag-palette`, {
      label,
      ...(color ? { color } : {}),
    })
    await mutate()
    return tag
  }

  async function updateLabel(
    id: string,
    patch: { label?: string; color?: string; position?: number },
  ): Promise<PaletteTag> {
    const tag = await api.patch<PaletteTag>(`/tag-palette/${id}`, patch)
    await mutate()
    return tag
  }

  async function deleteLabel(id: string): Promise<void> {
    await api.delete(`/tag-palette/${id}`)
    await mutate()
  }

  return { palette, isLoading, error, createLabel, updateLabel, deleteLabel, mutate }
}
