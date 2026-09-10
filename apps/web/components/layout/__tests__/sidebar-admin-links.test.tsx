/**
 * The sidebar's other admin links (Activity, Tasks) are gated on
 * `is_superadmin || is_subadmin`. Brief overview must NOT be: it spans every
 * owner's briefs and submitters, so a sub-admin who can review any asset still
 * cannot see it. That difference is easy to erase by copy-pasting the block
 * above it, so it gets its own test.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// jsdom has no matchMedia; the sidebar's useIsDesktop hook needs one.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: true,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
})

const authState = { user: null as Record<string, unknown> | null, logout: vi.fn() }

vi.mock('next/navigation', () => ({ usePathname: () => '/projects' }))
vi.mock('@/stores/auth-store', () => ({ useAuthStore: () => authState }))
vi.mock('@/stores/upload-store', () => ({
  useUploadStore: () => ({ files: [], togglePanel: vi.fn(), panelOpen: false }),
}))
vi.mock('@/stores/notification-store', () => ({
  useNotificationStore: () => ({ unreadCount: 0, fetchNotifications: vi.fn() }),
}))
vi.mock('@/stores/activity-store', () => ({
  useActivityStore: () => ({ unreadCount: 0, fetchUnreadCount: vi.fn() }),
}))
vi.mock('@/stores/branding-store', () => ({
  useBrandingStore: () => ({ orgName: 'Joolabs', orgLogoDark: null, orgLogoLight: null }),
}))
vi.mock('@/stores/theme-store', () => ({ useThemeStore: () => ({ theme: 'dark' }) }))
vi.mock('./notification-drawer', () => ({ NotificationDrawer: () => null }))
vi.mock('@/components/layout/notification-drawer', () => ({ NotificationDrawer: () => null }))

import { Sidebar } from '../sidebar'

function renderSidebar() {
  return render(<Sidebar collapsed={false} onToggle={() => {}} />)
}

beforeEach(() => {
  authState.user = null
})

describe('Sidebar — Brief overview link', () => {
  it('shows Brief overview to a superadmin', () => {
    authState.user = { id: 'u1', name: 'Boss', is_superadmin: true, is_subadmin: false }
    renderSidebar()
    expect(screen.getByRole('link', { name: /brief overview/i })).toHaveAttribute(
      'href',
      '/admin/briefs',
    )
  })

  it('hides Brief overview from a sub-admin, who still sees Activity', () => {
    authState.user = { id: 'u2', name: 'Sub', is_superadmin: false, is_subadmin: true }
    renderSidebar()
    expect(screen.getByRole('link', { name: /activity/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /brief overview/i })).toBeNull()
  })

  it('hides Brief overview from an ordinary editor', () => {
    authState.user = { id: 'u3', name: 'Ada', is_superadmin: false, is_subadmin: false }
    renderSidebar()
    expect(screen.queryByRole('link', { name: /brief overview/i })).toBeNull()
  })
})
