import type { SSEChunk, ParsedSSEEvent, ToolCall } from '../types/sse'

/**
 * 解析单行 SSE "data:" 事件
 * 格式: "data: {json}" 或 "data: [DONE]"
 */
export function parseSSELine(line: string): ParsedSSEEvent {
  // 去除 "data: " 前缀
  let data = line.trim()
  if (data.startsWith('data: ')) {
    data = data.slice(6)
  } else if (data.startsWith('data:')) {
    data = data.slice(5)
  } else {
    return { type: 'unknown' }
  }

  data = data.trim()

  // 结束信号
  if (data === '[DONE]') {
    return { type: 'stop' }
  }

  try {
    const chunk: SSEChunk = JSON.parse(data)
    const delta = chunk.choices?.[0]?.delta
    if (!delta) {
      return { type: 'unknown' }
    }

    // RAG 文档块
    if (delta.rag_docs) {
      return {
        type: 'rag_docs',
        query: delta.rag_docs.query || '',
        docs: delta.rag_docs.docs || [],
      }
    }

    // 根据 subtype 判断
    if (delta.subtype === 'thinking') {
      return {
        type: 'thinking',
        content: delta.content || '',
        toolCalls: (delta.tool_calls || []) as ToolCall[],
      }
    }

    if (delta.subtype === 'tool_result') {
      return {
        type: 'tool_result',
        content: delta.content || '',
        toolName: delta.tool_name || '未知工具',
      }
    }

    if (delta.subtype === 'answer') {
      return {
        type: 'answer',
        content: delta.content || '',
      }
    }

    // finish_reason="stop"
    if (chunk.choices[0].finish_reason === 'stop') {
      return { type: 'stop' }
    }

    return { type: 'unknown' }
  } catch {
    return { type: 'unknown' }
  }
}

/**
 * 批量解析 SSE 文本缓冲区，分离完整事件和残留数据
 * 返回 [parsedEvents[], remainingBufferString]
 */
export function parseSSEBuffer(buffer: string): [ParsedSSEEvent[], string] {
  const parts = buffer.split('\n')
  // 最后一行可能不完整，保留到下次
  const remaining = parts.pop() || ''

  const events: ParsedSSEEvent[] = []
  for (const line of parts) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const event = parseSSELine(trimmed)
    if (event.type !== 'unknown') {
      events.push(event)
    }
  }

  return [events, remaining]
}
