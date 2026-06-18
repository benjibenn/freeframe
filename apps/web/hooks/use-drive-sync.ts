'use client'

import useSWR from 'swr'
import { api } from '@/lib/api'

export interface DriveConnection {
  id: string
  drive_folder_id: string
  folder_name: string | null
  target_project_id: string
  enabled: boolean
  last_synced_at: string | null
  last_error: string | null
  synced_count: number
}

interface ServiceAccountResp {
  email: string | null
}

export function useDriveSync() {
  const {
    data: connections,
    isLoading: loadingConnections,
    mutate: mutateConnections,
  } = useSWR<DriveConnection[]>(
    '/admin/drive-sync',
    () => api.get<DriveConnection[]>('/admin/drive-sync'),
    { revalidateOnFocus: false },
  )

  const { data: serviceAccountResp, isLoading: loadingSA } =
    useSWR<ServiceAccountResp>(
      '/admin/drive-sync/service-account',
      () => api.get<ServiceAccountResp>('/admin/drive-sync/service-account'),
      { revalidateOnFocus: false },
    )

  const isLoading = loadingConnections || loadingSA

  async function createConnection(
    folderLink: string,
    targetProjectId: string,
  ): Promise<void> {
    await api.post('/admin/drive-sync', {
      folder_link: folderLink,
      target_project_id: targetProjectId,
    })
    await mutateConnections()
  }

  async function setEnabled(id: string, enabled: boolean): Promise<void> {
    await api.patch(`/admin/drive-sync/${id}`, { enabled })
    await mutateConnections()
  }

  async function deleteConnection(id: string): Promise<void> {
    await api.delete(`/admin/drive-sync/${id}`)
    await mutateConnections()
  }

  async function syncNow(id: string): Promise<void> {
    await api.post(`/admin/drive-sync/${id}/sync-now`, {})
  }

  return {
    connections: connections ?? [],
    serviceAccountEmail: serviceAccountResp?.email ?? null,
    isLoading,
    createConnection,
    setEnabled,
    deleteConnection,
    syncNow,
    mutate: mutateConnections,
  }
}
