import { create } from 'zustand'
import * as messagesApi from '../api/messages'
import type { MessageItem } from '../types/message'
import type { StreamBlock, ToolCall } from '../types/sse'

let _blockIdCounter = 0
function nextBlockId(): string {
  return `block_${++_blockIdCounter}_${Date.now()}`
}

interface ChatState {
  messages: MessageItem[]
  streamMessages: StreamBlock[]
  isStreaming: boolean
  streamingConversationId: number | null
  error: string | null
  rejectMessage: string | null  // 429 / token 超限时由后端返回的拒绝信息

  loadMessages: (conversationId: number) => Promise<void>
  clearMessages: () => void

  // 流式状态管理
  startStream: (conversationId: number) => void
  appendThinking: (content: string, toolCalls: ToolCall[]) => void
  appendToolResult: (content: string, toolName: string) => void
  appendAnswer: (content: string) => void
  appendRAGDocs: (query: string, docs: string[]) => void
  finishStream: (messageId?: number) => void
  abortStream: () => void
  setError: (error: string | null) => void
  setRejectError: (rejectMessage: string) => void  // 设置 token 超限错误
  clearRejectMessage: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streamMessages: [],
  isStreaming: false,
  streamingConversationId: null,
  error: null,
  rejectMessage: null,

  loadMessages: async (conversationId: number) => {
    set({ messages: [], streamMessages: [], error: null, rejectMessage: null })
    try {
      const res = await messagesApi.getMessages(conversationId)
      set({ messages: res.messages })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '加载消息失败' })
    }
  },

  clearMessages: () => {
    set({ messages: [], streamMessages: [] })
  },

  startStream: (conversationId: number) => {
    set({
      isStreaming: true,
      streamingConversationId: conversationId,
      streamMessages: [],
      error: null,
      rejectMessage: null,
    })
  },

  appendThinking: (content: string, toolCalls: ToolCall[]) => {
    const block: StreamBlock = {
      id: nextBlockId(),
      type: 'thinking',
      content,
      toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
    }
    set((state) => ({
      streamMessages: [...state.streamMessages, block],
    }))
  },

  appendToolResult: (content: string, toolName: string) => {
    const block: StreamBlock = {
      id: nextBlockId(),
      type: 'tool_result',
      content,
      toolName,
    }
    set((state) => ({
      streamMessages: [...state.streamMessages, block],
    }))
  },

  appendAnswer: (content: string) => {
    set((state) => {
      const lastBlock = state.streamMessages[state.streamMessages.length - 1]
      if (lastBlock && lastBlock.type === 'answer') {
        return {
          streamMessages: state.streamMessages.map((b, i) =>
            i === state.streamMessages.length - 1
              ? { ...b, content: b.content + content }
              : b
          ),
        }
      }
      const block: StreamBlock = {
        id: nextBlockId(),
        type: 'answer',
        content,
      }
      return { streamMessages: [...state.streamMessages, block] }
    })
  },

  appendRAGDocs: (query: string, docs: string[]) => {
    const block: StreamBlock = {
      id: nextBlockId(),
      type: 'rag_docs',
      content: '',
      query,
      docs,
    }
    set((state) => ({
      streamMessages: [...state.streamMessages, block],
    }))
  },

  finishStream: (messageId?: number) => {
    const state = get()
    // 防止重复调用（双重 stop 信号场景）
    if (!state.isStreaming) return

    const answerBlocks = state.streamMessages.filter((b) => b.type === 'answer')
    const content = answerBlocks.map((b) => b.content).join('')

    // 保留所有 blocks（思考/工具/RAG）到消息中
    const newMsg: MessageItem = {
      id: messageId || Date.now(),
      role: 'assistant',
      content: content || '（无回复内容）',
      blocks: [...state.streamMessages],
      created_at: new Date().toISOString(),
    }

    set({
      messages: [...state.messages, newMsg],
      streamMessages: [],
      isStreaming: false,
      streamingConversationId: null,
    })
  },

  abortStream: () => {
    set({
      streamMessages: [],
      isStreaming: false,
      streamingConversationId: null,
    })
  },

  setError: (error: string | null) => {
    set({ error, isStreaming: false })
  },

  setRejectError: (rejectMessage: string) => {
    set({
      error: rejectMessage,
      rejectMessage,
      isStreaming: false,
    })
  },

  clearRejectMessage: () => {
    set({ rejectMessage: null })
  },
}))
