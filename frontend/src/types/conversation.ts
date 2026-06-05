// 对话相关类型定义

export interface ConversationListItem {
  id: number
  title: string | null
  message_count: number
  last_message_preview: string | null
  created_at: string
  updated_at: string
}

export interface ConversationListResponse {
  conversations: ConversationListItem[]
  total: number
  page: number
  page_size: number
}

export interface CreateConversationRequest {
  title?: string
}

export interface ConversationDetailResponse {
  id: number
  user_id: number
  title: string | null
  created_at: string
  updated_at: string
}
