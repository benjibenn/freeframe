'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/auth-store'
import { DriveSyncPanel } from '@/components/settings/drive-sync-panel'

export default function SyncPage() {
  const { user, isSuperAdmin, isSubAdmin } = useAuthStore()
  const router = useRouter()

  const canAccess = isSuperAdmin || isSubAdmin

  React.useEffect(() => {
    if (user && !canAccess) {
      router.replace('/')
    }
  }, [user, canAccess, router])

  if (!canAccess) {
    return null
  }

  return (
    <div className="p-4 sm:p-6">
      <DriveSyncPanel />
    </div>
  )
}
