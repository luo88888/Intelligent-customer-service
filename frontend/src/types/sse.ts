// SSE 流式块类型定义

/** 工具调用信息 */
export interface ToolCall {
  name: string
  args: Record<string, unknown>
}

/** 流式块的基础类型 */
export type StreamBlockType = 'thinking' | 'tool_result' | 'answer' | 'rag_docs'

/** 流式消息块 */
export interface StreamBlock {
  id: string
  type: StreamBlockType
  content: string
  toolName?: string
  toolCalls?: ToolCall[]
  query?: string
  docs?: string[]
}

/** 完成后的助手消息（含所有中间块） */
export interface AssistantMessageFull {
  id: number
  role: 'assistant'
  content: string
  blocks: StreamBlock[]
  ragDocs?: { query: string; docs: string[] }[]
  created_at: string
}

/** SSE 原始数据块类型 */
export interface SSEChunkDelta {
  content?: string
  subtype?: 'thinking' | 'tool_result' | 'answer'
  tool_calls?: ToolCall[]
  tool_name?: string
  rag_docs?: {
    query: string
    docs: string[]
  }
  error?: SSEError
}

export interface SSEChunkChoice {
  index: number
  delta: SSEChunkDelta
  finish_reason: string | null
}

export interface SSEChunk {
  id: string
  object: string
  created: number
  model: string
  choices: SSEChunkChoice[]
}

/** SSE 错误事件信息 */
export interface SSEError {
  type: string
  message: string
  reject_message: string
}

/** 解析后的 SSE 事件 */
export type ParsedSSEEvent =
  | { type: 'thinking'; content: string; toolCalls: ToolCall[] }
  | { type: 'tool_result'; content: string; toolName: string }
  | { type: 'answer'; content: string }
  | { type: 'rag_docs'; query: string; docs: string[] }
  | { type: 'error'; error: SSEError }
  | { type: 'stop' }
  | { type: 'unknown' }
