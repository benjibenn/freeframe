'use client'

import * as React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { User, Bell, Shield, Palette, Brush, KeyRound, HardDrive } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

interface SettingsNavItem {
  href: string
  label: string
  icon: React.ElementType
  adminOnly?: boolean
  /** Visible to super-admins and sub-admins */
  adminOrSubadmin?: boolean
}

const settingsNavItems: SettingsNavItem[] = [
  { href: '/settings/profile', label: 'Profile', icon: User },
  { href: '/settings/appearance', label: 'Appearance', icon: Palette },
  { href: '/settings/notifications', label: 'Notifications', icon: Bell },
  { href: '/settings/sync', label: 'Sync', icon: HardDrive, adminOrSubadmin: true },
  { href: '/settings/branding', label: 'Branding', icon: Brush, adminOnly: true },
  { href: '/settings/admin', label: 'Admin', icon: Shield, adminOnly: true },
  { href: '/settings/api-keys', label: 'API Keys', icon: KeyRound, adminOnly: true },
]

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const { user, isSuperAdmin, isSubAdmin } = useAuthStore()

  return (
    <div className="flex h-full flex-col md:flex-row">
      {/* Settings Sidebar — horizontal scroll bar on mobile, side rail on desktop */}
      <aside className="w-full md:w-56 border-b md:border-b-0 md:border-r border-border bg-bg-secondary shrink-0">
        <div className="hidden md:block p-4 border-b border-border">
          <h2 className="text-sm font-semibold text-text-primary">Settings</h2>
          <p className="text-xs text-text-tertiary mt-0.5">
            {user?.name ?? 'User'}
          </p>
        </div>

        <nav className="flex md:flex-col gap-1 md:gap-0.5 p-2 overflow-x-auto">
          {settingsNavItems.map((item) => {
            // Hide admin-only items from non-admins
            if (item.adminOnly && !isSuperAdmin) return null
            // Sync tab is visible to super-admins and sub-admins
            if (item.adminOrSubadmin && !isSuperAdmin && !isSubAdmin) return null

            const isActive = pathname === item.href || pathname?.startsWith(item.href + '/')
            const Icon = item.icon

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors shrink-0 whitespace-nowrap',
                  isActive
                    ? 'bg-bg-hover text-text-primary font-medium'
                    : 'text-text-secondary hover:bg-bg-hover/70 hover:text-text-primary',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </aside>

      {/* Settings Content */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}
