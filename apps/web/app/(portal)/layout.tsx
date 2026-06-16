'use client'

import * as React from 'react'
import { useAuthStore } from '@/stores/auth-store'

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const { user, fetchUser, logout } = useAuthStore()

  React.useEffect(() => {
    fetchUser()
  }, [fetchUser])

  return (
    <div className="min-h-screen bg-bg-primary">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <span className="text-lg font-semibold text-text-primary">Creative Flywheel</span>
        <div className="flex items-center gap-3 text-sm text-text-secondary">
          {user?.name || user?.email}
          <button onClick={logout} className="text-text-tertiary hover:text-text-primary">
            Log out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-10">
        <h1 className="mb-6 text-xl font-semibold text-text-primary">Your tools</h1>
        {children}
      </main>
    </div>
  )
}
