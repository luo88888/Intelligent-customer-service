import { create } from 'zustand'
import { setToken, getToken, removeToken } from '../utils/token'
import * as authApi from '../api/auth'
import type { TokenResponse } from '../types/auth'

interface UserInfo {
  user_id: number
  username: string
  display_name: string | null
}

interface AuthState {
  token: string | null
  user: UserInfo | null
  isAuthenticated: boolean

  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, displayName?: string) => Promise<void>
  logout: () => void
  loadFromStorage: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,

  login: async (username: string, password: string) => {
    const res: TokenResponse = await authApi.login({ username, password })
    setToken(res.access_token)
    set({
      token: res.access_token,
      user: {
        user_id: res.user_id,
        username: res.username,
        display_name: res.display_name,
      },
      isAuthenticated: true,
    })
  },

  register: async (username: string, password: string, displayName?: string) => {
    const res: TokenResponse = await authApi.register({
      username,
      password,
      display_name: displayName,
    })
    setToken(res.access_token)
    set({
      token: res.access_token,
      user: {
        user_id: res.user_id,
        username: res.username,
        display_name: res.display_name,
      },
      isAuthenticated: true,
    })
  },

  logout: () => {
    removeToken()
    set({ token: null, user: null, isAuthenticated: false })
  },

  loadFromStorage: () => {
    const token = getToken()
    if (token) {
      // 简单解码 JWT payload 获取用户信息
      try {
        const payload = JSON.parse(atob(token.split('.')[1]))
        set({
          token,
          user: {
            user_id: payload.sub ? Number(payload.sub) : 0,
            username: payload.username || '',
            display_name: null,
          },
          isAuthenticated: true,
        })
      } catch {
        removeToken()
        set({ token: null, user: null, isAuthenticated: false })
      }
    }
  },
}))
