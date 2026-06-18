'use client'

import * as React from 'react'
import useSWR from 'swr'
import { HardDrive, RefreshCw, Trash2 } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/components/shared/toast'
import { useDriveSync } from '@/hooks/use-drive-sync'
import type { Project } from '@/types'

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={[
        'relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-accent',
        'disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'bg-accent' : 'bg-bg-tertiary',
      ].join(' ')}
    >
      <span
        className={[
          'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200',
          checked ? 'translate-x-4' : 'translate-x-0',
        ].join(' ')}
      />
    </button>
  )
}

export function DriveSyncPanel() {
  const toast = useToast()
  const {
    connections,
    serviceAccountEmail,
    isLoading,
    createConnection,
    setEnabled,
    deleteConnection,
    syncNow,
  } = useDriveSync()

  const { data: projects } = useSWR<Project[]>(
    '/projects',
    () => api.get<Project[]>('/projects'),
    { revalidateOnFocus: false },
  )

  const [folderLink, setFolderLink] = React.useState('')
  const [targetProjectId, setTargetProjectId] = React.useState('')
  const [adding, setAdding] = React.useState(false)
  const [syncingIds, setSyncingIds] = React.useState<Set<string>>(new Set())
  const [togglingIds, setTogglingIds] = React.useState<Set<string>>(new Set())
  const [deletingIds, setDeletingIds] = React.useState<Set<string>>(new Set())

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!folderLink.trim() || !targetProjectId) return
    setAdding(true)
    try {
      await createConnection(folderLink.trim(), targetProjectId)
      setFolderLink('')
      setTargetProjectId('')
      toast.success('Drive folder connected.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to add connection.')
    } finally {
      setAdding(false)
    }
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    setTogglingIds((prev) => new Set(prev).add(id))
    try {
      await setEnabled(id, enabled)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to update.')
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleSyncNow = async (id: string) => {
    setSyncingIds((prev) => new Set(prev).add(id))
    try {
      await syncNow(id)
      toast.success('Sync queued.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to queue sync.')
    } finally {
      setSyncingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleDelete = async (id: string) => {
    setDeletingIds((prev) => new Set(prev).add(id))
    try {
      await deleteConnection(id)
      toast.success('Connection removed.')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to remove connection.')
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const projectMap = React.useMemo(() => {
    const m: Record<string, string> = {}
    for (const p of projects ?? []) m[p.id] = p.name
    return m
  }, [projects])

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <HardDrive className="h-4 w-4 text-text-secondary" />
        <h2 className="text-sm font-semibold text-text-primary">Google Drive Sync</h2>
      </div>

      {/* Service account hint */}
      <div className="rounded-lg border border-border bg-bg-secondary px-4 py-3 text-sm">
        {isLoading ? (
          <div className="h-4 w-64 animate-pulse rounded bg-bg-tertiary" />
        ) : serviceAccountEmail ? (
          <p className="text-text-secondary">
            Share each Google Drive folder with{' '}
            <span className="font-medium text-text-primary select-all">
              {serviceAccountEmail}
            </span>{' '}
            (Viewer role), then paste the folder link below.
          </p>
        ) : (
          <p className="text-status-error text-xs">
            Google Drive credentials are not configured on this server. Contact your administrator.
          </p>
        )}
      </div>

      {/* Add connection form */}
      <form onSubmit={handleAdd} className="flex flex-wrap gap-2">
        <Input
          className="min-w-0 flex-1"
          placeholder="https://drive.google.com/drive/folders/…"
          value={folderLink}
          onChange={(e) => setFolderLink(e.target.value)}
          disabled={adding}
        />
        <select
          value={targetProjectId}
          onChange={(e) => setTargetProjectId(e.target.value)}
          disabled={adding}
          className="rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus disabled:opacity-50"
        >
          <option value="">Select project…</option>
          {(projects ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <Button
          type="submit"
          size="sm"
          loading={adding}
          disabled={!folderLink.trim() || !targetProjectId}
        >
          Add
        </Button>
      </form>

      {/* Connection list */}
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-bg-tertiary" />
          ))}
        </div>
      ) : connections.length === 0 ? (
        <p className="text-sm text-text-tertiary">No Drive folders connected yet.</p>
      ) : (
        <div className="rounded-lg border border-border bg-bg-secondary overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-bg-tertiary">
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary whitespace-nowrap">
                    Folder
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary whitespace-nowrap hidden sm:table-cell">
                    Project
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary whitespace-nowrap hidden md:table-cell">
                    Last synced
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-text-tertiary whitespace-nowrap hidden md:table-cell">
                    Files
                  </th>
                  <th className="px-4 py-2.5 text-center text-xs font-medium text-text-tertiary whitespace-nowrap">
                    Enabled
                  </th>
                  <th className="px-4 py-2.5 text-right text-xs font-medium text-text-tertiary whitespace-nowrap">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {connections.map((c) => (
                  <tr
                    key={c.id}
                    className="border-b border-border last:border-0 hover:bg-bg-tertiary transition-colors"
                  >
                    <td className="px-4 py-3 max-w-[180px]">
                      <p className="text-sm text-text-primary truncate font-medium">
                        {c.folder_name ?? c.drive_folder_id}
                      </p>
                      {c.last_error && (
                        <p className="text-xs text-status-error truncate" title={c.last_error}>
                          {c.last_error}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-text-secondary whitespace-nowrap hidden sm:table-cell">
                      {projectMap[c.target_project_id] ?? c.target_project_id}
                    </td>
                    <td className="px-4 py-3 text-xs text-text-tertiary whitespace-nowrap hidden md:table-cell">
                      {c.last_synced_at
                        ? new Date(c.last_synced_at).toLocaleString()
                        : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-text-tertiary whitespace-nowrap hidden md:table-cell">
                      {c.synced_count}
                    </td>
                    <td className="px-4 py-3 text-center whitespace-nowrap">
                      <Toggle
                        checked={c.enabled}
                        onChange={(v) => handleToggle(c.id, v)}
                        disabled={togglingIds.has(c.id)}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleSyncNow(c.id)}
                          disabled={syncingIds.has(c.id)}
                          className="gap-1"
                        >
                          <RefreshCw
                            className={[
                              'h-3.5 w-3.5',
                              syncingIds.has(c.id) ? 'animate-spin' : '',
                            ].join(' ')}
                          />
                          Sync now
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(c.id)}
                          disabled={deletingIds.has(c.id)}
                          className="text-status-error hover:text-status-error"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
