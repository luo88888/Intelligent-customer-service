import { useCallback, useRef } from 'react'
import { useChatStore } from '../stores/chatStore'
import * as messagesApi from '../api/messages'
import { ApiError } from '../api/client'
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
          // 尝试解析响应体中的错误信息（尤其是 429 的 reject_message）
          let errorText = '未知错误'
          let rejectMessage: string | null = null
          try {
            const errorBody = JSON.parse(await response.text())
            errorText = errorBody.message || errorBody.detail || `HTTP ${response.status}`
            rejectMessage = errorBody.reject_message || errorBody.message || null
          } catch {
            errorText = `请求失败: ${response.status}`
          }

          // 429 错误使用 setRejectError 以在聊天区域显示持久化横幅
          if (response.status === 429 && rejectMessage) {
            store.setRejectError(rejectMessage)
          } else {
            store.setError(errorText)
          }
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
              case 'error': {
                // 流内错误事件（如上游 LLM 返回 429）
                const { reject_message: sseRejectMsg, message: sseMsg } = event.error
                if (event.error.type === 'token_budget_exceeded' && sseRejectMsg) {
                  store.setRejectError(sseRejectMsg)
                } else {
                  store.setError(sseRejectMsg || sseMsg || '服务暂时不可用')
                }
                return  // 错误后终止读取
              }
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
          // 检查 ApiError 中是否有 rejectMessage（如 429）
          if (err instanceof ApiError && err.rejectMessage) {
            store.setRejectError(err.rejectMessage)
          } else {
            const errorMsg =
              err instanceof Error ? err.message : '网络请求失败'
            store.setError(errorMsg)
          }
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
