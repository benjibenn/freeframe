'use client'

import * as React from 'react'
import { Megaphone } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

/**
 * "Run as ad" toggle for the asset review header. Mirrors the toggle on the
 * admin Tasks page: the flag is what the external integration API filters
 * ad-ready videos by, so — like the pipeline-stage select next to it — it's
 * only shown to platform admins (superadmin / sub-admin). Self-contained state
 * (the review provider holds the asset in local state with no exposed setter),
 * optimistic with rollback on failure.
 */
export function RunAsAdToggle({
  assetId,
  initial,
}: {
  assetId: string
  initial: boolean
}) {
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)
  const [active, setActive] = React.useState(initial)
  const [saving, setSaving] = React.useState(false)

  React.useEffect(() => {
    setActive(initial)
  }, [initial])

  if (!isPlatformAdmin) return null

  const handleToggle = async () => {
    const next = !active
    setActive(next)
    setSaving(true)
    try {
      await api.patch(`/assets/${assetId}/run-as-ad`, { run_as_ad: next })
    } catch (err) {
      setActive(!next)
      alert(err instanceof Error ? err.message : 'Failed to update "run as ad"')
    } finally {
      setSaving(false)
    }
  }

  return (
    <button
      onClick={handleToggle}
      disabled={saving}
      aria-pressed={active}
      title={active ? 'Cleared to run as ad — click to clear' : 'Mark as run as ad'}
      className={cn(
        'hidden sm:inline-flex items-center gap-1.5 rounded-md px-2.5 h-8 text-xs font-medium border transition-colors disabled:opacity-60',
        active
          ? 'border-accent/40 bg-accent/10 text-accent'
          : 'border-border bg-bg-secondary text-text-secondary hover:text-text-primary hover:border-border-focus',
      )}
    >
      <Megaphone className="h-3.5 w-3.5" />
      {active ? 'Running as ad' : 'Run as ad'}
    </button>
  )
}
