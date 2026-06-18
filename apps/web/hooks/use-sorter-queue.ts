'use client'

import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import type { Asset } from '@/types'

export function useSorterQueue(projectId: string, tag?: string) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [index, setIndex] = useState(0)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams({ exclude_archived: 'true' })
    if (tag) params.set('tag', tag)
    api
      .get<Asset[]>(`/projects/${projectId}/assets?${params.toString()}`)
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

  const restoreAt = useCallback((restoreIndex: number, asset: Asset) => {
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
    refresh: load,
  }
}
