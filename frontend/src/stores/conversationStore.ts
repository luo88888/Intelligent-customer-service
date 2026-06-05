import { create } from 'zustand'
import * as conversationsApi from '../api/conversations'
import type { ConversationListItem } from '../types/conversation'

interface ConversationState {
  conversations: ConversationListItem[]
  total: number
  activeConversationId: number | null
  loading: boolean

  fetchConversations: (page?: number) => Promise<void>
  createConversation: (title?: string) => Promise<number>
  deleteConversation: (id: number) => Promise<void>
  setActiveConversation: (id: number | null) => void
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  total: 0,
  activeConversationId: null,
  loading: false,

  fetchConversations: async (page = 1) => {
    set({ loading: true })
    try {
      const res = await conversationsApi.listConversations(page)
      set({ conversations: res.conversations, total: res.total })
    } finally {
      set({ loading: false })
    }
  },

  createConversation: async (title?: string) => {
    const res = await conversationsApi.createConversation({ title })
    // 刷新列表
    await get().fetchConversations()
    return res.id
  },

  deleteConversation: async (id: number) => {
    await conversationsApi.deleteConversation(id)
    const { activeConversationId } = get()
    if (activeConversationId === id) {
      set({ activeConversationId: null })
    }
    await get().fetchConversations()
  },

  setActiveConversation: (id: number | null) => {
    set({ activeConversationId: id })
  },
}))
