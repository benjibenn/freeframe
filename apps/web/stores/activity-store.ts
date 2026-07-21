import { create } from 'zustand'
import type { ActivityFeedItem } from '@/types'
import { api } from '@/lib/api'

interface ActivityState {
  items: ActivityFeedItem[]
  unreadCount: number
  isLoading: boolean
  hasMore: boolean
  /** Comma-separated action names to filter by, or null for all. */
  filter: string | null
  /** User id to narrow the feed to, or null for all users. */
  userId: string | null
  fetchFeed: () => Promise<void>
  loadMore: () => Promise<void>
  setFilter: (filter: string | null) => Promise<void>
  setUserId: (userId: string | null) => Promise<void>
  fetchUnreadCount: () => Promise<void>
  markSeen: () => Promise<void>
}

const PAGE_SIZE = 50

function buildUrl(filter: string | null, userId: string | null, before?: string): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) })
  if (filter) params.set('action', filter)
  if (userId) params.set('user_id', userId)
  if (before) params.set('before', before)
  return `/activity?${params.toString()}`
}

export const useActivityStore = create<ActivityState>()((set, get) => ({
  items: [],
  unreadCount: 0,
  isLoading: false,
  hasMore: false,
  filter: null,
  userId: null,

  fetchFeed: async () => {
    set({ isLoading: true })
    try {
      const items = await api.get<ActivityFeedItem[]>(buildUrl(get().filter, get().userId))
      set({ items, hasMore: items.length === PAGE_SIZE })
    } finally {
      set({ isLoading: false })
    }
  },

  loadMore: async () => {
    const { items, hasMore, isLoading, filter, userId } = get()
    if (!hasMore || isLoading || items.length === 0) return
    set({ isLoading: true })
    try {
      const before = items[items.length - 1].created_at
      const older = await api.get<ActivityFeedItem[]>(buildUrl(filter, userId, before))
      set({ items: [...items, ...older], hasMore: older.length === PAGE_SIZE })
    } finally {
      set({ isLoading: false })
    }
  },

  setFilter: async (filter: string | null) => {
    if (get().filter === filter) return
    set({ filter, items: [], hasMore: false })
    await get().fetchFeed()
  },

  setUserId: async (userId: string | null) => {
    if (get().userId === userId) return
    set({ userId, items: [], hasMore: false })
    await get().fetchFeed()
  },

  fetchUnreadCount: async () => {
    try {
      const { count } = await api.get<{ count: number }>('/activity/unread-count')
      set({ unreadCount: count })
    } catch {
      // Non-admins get 403 — silently ignore.
    }
  },

  markSeen: async () => {
    await api.post('/activity/seen')
    set({ unreadCount: 0 })
  },
}))
