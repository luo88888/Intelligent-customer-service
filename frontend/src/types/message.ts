// 消息相关类型定义

import type { StreamBlock } from './sse'

export interface MessageItem {
  id: number
  role: 'user' | 'assistant'
  content: string
  blocks?: StreamBlock[]
  created_at: string
}

export interface MessageListResponse {
  conversation_id: number
  messages: MessageItem[]
}

export interface MessageSendRequest {
  content: string
}

export interface MessageSendResponse {
  message_id: number
  role: string
  content: string
  rag_docs: RAGDocEntry[] | null
  created_at: string
}

export interface RAGDocEntry {
  query: string
  docs: string[]
}
