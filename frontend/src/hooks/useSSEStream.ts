import { useCallback, useRef } from 'react'
import { useChatStore } from '../stores/chatStore'
import * as messagesApi from '../api/messages'
import { parseSSEBuffer } from '../utils/sseParser'

export function useSSEStream() {
  const abortRef = useRef<AbortController | null>(null)

  const startStream = useCallback(
    async (conversationId: number, content: string) => {
      const store = useChatStore.getState()

      // 如果有正在进行的流，先取消
      if (abortRef.current) {
        abortRef.current.abort()
      }

      const abortController = new AbortController()
      abortRef.current = abortController

      store.startStream(conversationId)

      try {
        const response = await messagesApi.sendMessageStream(conversationId, {
          content,
        })

        if (!response.ok || !response.body) {
          const errorText = await response.text().catch(() => '未知错误')
          store.setError(`请求失败: ${response.status} ${errorText}`)
          return
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done || abortController.signal.aborted) break

          buffer += decoder.decode(value, { stream: true })

          const [events, remaining] = parseSSEBuffer(buffer)
          buffer = remaining

          for (const event of events) {
            if (abortController.signal.aborted) break

            switch (event.type) {
              case 'thinking':
                store.appendThinking(event.content, event.toolCalls)
                break
              case 'tool_result':
                store.appendToolResult(event.content, event.toolName)
                break
              case 'answer':
                store.appendAnswer(event.content)
                break
              case 'rag_docs':
                store.appendRAGDocs(event.query, event.docs)
                break
              case 'stop':
                // 防重入：实时读取 isStreaming 而非用捕获的 store 快照
                if (useChatStore.getState().isStreaming) {
                  store.finishStream()
                }
                break
            }
          }
        }

        // 如果 stream 自然结束但没收到 stop 信号（实时读取状态）
        if (!abortController.signal.aborted && useChatStore.getState().isStreaming) {
          store.finishStream()
        }
      } catch (err) {
        if (!abortController.signal.aborted) {
          const errorMsg =
            err instanceof Error ? err.message : '网络请求失败'
          store.setError(errorMsg)
        }
      }
    },
    []
  )

  const abortStream = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    useChatStore.getState().abortStream()
  }, [])

  return { startStream, abortStream }
}
