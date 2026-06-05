import { request, streamRequest } from './client'
import type {
  MessageListResponse,
  MessageSendResponse,
  MessageSendRequest,
} from '../types/message'

export async function getMessages(
  conversationId: number
): Promise<MessageListResponse> {
  return request<MessageListResponse>(
    `/api/conversations/${conversationId}/messages`
  )
}

/** 非流式发送消息 */
export async function sendMessage(
  conversationId: number,
  data: MessageSendRequest
): Promise<MessageSendResponse> {
  return request<MessageSendResponse>(
    `/api/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
}

/** 流式发送消息，返回 Response 供 SSE 读取 */
export async function sendMessageStream(
  conversationId: number,
  data: MessageSendRequest
): Promise<Response> {
  return streamRequest(
    `/api/conversations/${conversationId}/messages?stream=true`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
}
