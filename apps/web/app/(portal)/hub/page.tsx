'use client'

import useSWR from 'swr'
import { LayoutGrid } from 'lucide-react'
import { api } from '@/lib/api'
import { EmptyState } from '@/components/shared/empty-state'

interface PortalApp {
  slug: string
  name: string
  launch_url: string
  description: string
  icon: string | null
}

export default function HubPage() {
  const { data, error, isLoading } = useSWR<{ apps: PortalApp[] }>(
    '/portal/apps',
    (path: string) => api.get(path),
  )

  if (isLoading) {
    return <p className="py-12 text-center text-sm text-text-secondary">Loading your tools…</p>
  }

  if (error) {
    return (
      <EmptyState
        icon={LayoutGrid}
        title="Couldn't load your tools"
        description="We couldn't reach the identity provider. Please retry in a moment."
        action={{ label: 'Retry', onClick: () => window.location.reload() }}
      />
    )
  }

  const apps = data?.apps ?? []
  if (apps.length === 0) {
    return (
      <EmptyState
        icon={LayoutGrid}
        title="No tools assigned yet"
        description="You don't have access to any tools yet. Contact your administrator."
      />
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {apps.map((app) => (
        <a
          key={app.slug}
          href={app.launch_url}
          aria-label={app.name}
          className="flex flex-col gap-2 rounded-xl border border-border bg-bg-secondary p-5 transition hover:border-accent hover:bg-bg-tertiary"
        >
          <span className="text-base font-medium text-text-primary">{app.name}</span>
          {app.description && (
            <span className="text-sm text-text-secondary">{app.description}</span>
          )}
        </a>
      ))}
    </div>
  )
}
