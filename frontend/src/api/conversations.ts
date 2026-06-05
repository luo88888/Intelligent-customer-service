import { request } from './client'
import type {
  ConversationListResponse,
  ConversationDetailResponse,
  CreateConversationRequest,
} from '../types/conversation'

export async function listConversations(
  page: number = 1,
  pageSize: number = 20
): Promise<ConversationListResponse> {
  return request<ConversationListResponse>(
    `/api/conversations?page=${page}&page_size=${pageSize}`
  )
}

export async function createConversation(
  data: CreateConversationRequest = {}
): Promise<ConversationDetailResponse> {
  return request<ConversationDetailResponse>('/api/conversations', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getConversation(
  id: number
): Promise<ConversationDetailResponse> {
  return request<ConversationDetailResponse>(`/api/conversations/${id}`)
}

export async function deleteConversation(id: number): Promise<void> {
  return request<void>(`/api/conversations/${id}`, {
    method: 'DELETE',
  })
}
