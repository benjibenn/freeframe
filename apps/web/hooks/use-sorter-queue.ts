'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { AssetResponse } from '@/types'

export function useSorterQueue(projectId: string, tag?: string) {
  const [assets, setAssets] = useState<AssetResponse[]>([])
  const [index, setIndex] = useState(0)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams({ exclude_archived: 'true' })
    if (tag) params.set('tag', tag)
    api
      .get<AssetResponse[]>(`/projects/${projectId}/assets?${params.toString()}`)
      .then((data) => { setAssets(data ?? []); setIndex(0) })
      .finally(() => setLoading(false))
  }, [projectId, tag])

  useEffect(() => { load() }, [load])

  const next = useCallback(
    () => setIndex((i) => Math.min(i + 1, Math.max(0, assets.length - 1))),
    [assets.length],
  )
  const prev = useCallback(() => setIndex((i) => Math.max(i - 1, 0)), [])

  const removeCurrent = useCallback(() => {
    setAssets((prevAssets) => {
      const nextAssets = prevAssets.filter((_, i) => i !== index)
      setIndex((i) => Math.min(i, Math.max(0, nextAssets.length - 1)))
      return nextAssets
    })
  }, [index])

  const restoreAt = useCallback((restoreIndex: number, asset: AssetResponse) => {
    setAssets((prevAssets) => {
      const next = [...prevAssets]
      next.splice(restoreIndex, 0, asset)
      return next
    })
    setIndex(restoreIndex)
  }, [])

  const patchCurrent = useCallback(
    (updater: (prevKeywords: string[]) => string[]) =>
      setAssets((prevAssets) =>
        prevAssets.map((a, i) =>
          i === index ? { ...a, keywords: updater(a.keywords ?? []) } : a,
        ),
      ),
    [index],
  )

  const patchById = useCallback(
    (assetId: string, updater: (prevKeywords: string[]) => string[]) =>
      setAssets((prevAssets) =>
        prevAssets.map((a) =>
          a.id === assetId ? { ...a, keywords: updater(a.keywords ?? []) } : a,
        ),
      ),
    [],
  )

  return {
    assets,
    index,
    current: assets[index],
    loading,
    next,
    prev,
    removeCurrent,
    restoreAt,
    patchCurrent,
    patchById,
    refresh: load,
  }
}
