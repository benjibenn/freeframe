import { create } from 'zustand'
import { User } from '@/types'
import { api } from '@/lib/api'
import { clearTokens } from '@/lib/auth'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isSuperAdmin: boolean
  isSubAdmin: boolean
  isLoading: boolean
  setUser: (user: User) => void
  logout: () => void
  fetchUser: () => Promise<void>
}

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  isAuthenticated: false,
  isSuperAdmin: false,
  isSubAdmin: false,
  isLoading: false,

  setUser: (user: User) => {
    set({
      user,
      isAuthenticated: true,
      isSuperAdmin: user.is_superadmin,
      isSubAdmin: user.is_subadmin,
    })
  },

  logout: () => {
    clearTokens()
    set({
      user: null,
      isAuthenticated: false,
      isSuperAdmin: false,
      isSubAdmin: false,
    })
  },

  fetchUser: async () => {
    set({ isLoading: true })
    try {
      const user = await api.get<User>('/auth/me')
      set({
        user,
        isAuthenticated: true,
        isSuperAdmin: user.is_superadmin,
        isSubAdmin: user.is_subadmin,
      })
    } catch {
      set({
        user: null,
        isAuthenticated: false,
        isSuperAdmin: false,
        isSubAdmin: false,
      })
    } finally {
      set({ isLoading: false })
    }
  },
}))
