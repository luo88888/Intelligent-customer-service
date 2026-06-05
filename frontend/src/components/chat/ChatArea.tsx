import { useEffect, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Typography, App } from 'antd'
import { RobotOutlined, MessageOutlined, LoadingOutlined } from '@ant-design/icons'
import { useChatStore } from '../../stores/chatStore'
import { useConversationStore } from '../../stores/conversationStore'
import { useSSEStream } from '../../hooks/useSSEStream'
import UserMessage from './UserMessage'
import AssistantMessage from './AssistantMessage'
import ChatInput from './ChatInput'
import styles from './ChatArea.module.css'

const { Title, Text } = Typography

export default function ChatArea() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const { message: antdMsg } = App.useApp()
  const messages = useChatStore((s) => s.messages)
  const streamMessages = useChatStore((s) => s.streamMessages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const error = useChatStore((s) => s.error)
  const setError = useChatStore((s) => s.setError)
  const loadMessages = useChatStore((s) => s.loadMessages)
  const activeConversationId = useConversationStore((s) => s.activeConversationId)
  const fetchConversations = useConversationStore((s) => s.fetchConversations)
  const { startStream } = useSSEStream()

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)
  const shouldAutoScroll = useRef(true)

  // 加载消息
  useEffect(() => {
    const id = conversationId ? Number(conversationId) : null
    if (id) {
      loadMessages(id)
    }
  }, [conversationId, loadMessages])

  // 显示错误
  useEffect(() => {
    if (error) {
      antdMsg.error(error)
      setError(null)
    }
  }, [error, antdMsg, setError])

  // 自动滚动
  const scrollToBottom = useCallback(() => {
    if (shouldAutoScroll.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [])

  // 检测用户是否手动上滚
  const handleScroll = useCallback(() => {
    const container = chatContainerRef.current
    if (!container) return
    const { scrollTop, scrollHeight, clientHeight } = container
    shouldAutoScroll.current = scrollHeight - scrollTop - clientHeight < 80
  }, [])

  // 新消息时滚动
  useEffect(() => {
    scrollToBottom()
  }, [messages, streamMessages, scrollToBottom])

  const handleSend = useCallback(
    async (content: string) => {
      const convId = activeConversationId
      if (!convId) return

      // 添加用户消息到列表
      const chatStore = useChatStore.getState()
      const userMsg = {
        id: Date.now(),
        role: 'user' as const,
        content,
        created_at: new Date().toISOString(),
      }
      useChatStore.setState({
        messages: [...chatStore.messages, userMsg],
        error: null,
      })

      shouldAutoScroll.current = true

      try {
        await startStream(convId, content)
        // 流结束后刷新对话列表
        fetchConversations()
      } catch (err) {
        // 错误已在 hook 中处理
      }
    },
    [activeConversationId, startStream, fetchConversations]
  )

  const hasStreamContent = streamMessages.length > 0

  // 空状态：没有选择对话
  if (!conversationId && !activeConversationId) {
    return (
      <div className={styles.chatContainer}>
        <div className={styles.emptyState}>
          <RobotOutlined className={styles.emptyIcon} />
          <Title level={4} style={{ color: '#666' }}>
            智扫通智能客服
          </Title>
          <Text type="secondary">
            选择左侧的会话开始对话，或创建一个新会话
          </Text>
        </div>
        {!activeConversationId && (
          <ChatInput
            onSend={handleSend}
            disabled={true}
          />
        )}
      </div>
    )
  }

  return (
    <div className={styles.chatContainer}>
      {/* 消息列表 */}
      <div
        className={styles.messageList}
        ref={chatContainerRef}
        onScroll={handleScroll}
      >
        {messages.length === 0 && !hasStreamContent && (
          <div className={styles.emptyChat}>
            <MessageOutlined className={styles.emptyChatIcon} />
            <Text type="secondary">发送消息开始对话</Text>
          </div>
        )}

        {messages.map((msg) =>
          msg.role === 'user' ? (
            <UserMessage key={msg.id} content={msg.content} />
          ) : (
            <AssistantMessage
              key={msg.id}
              content={msg.content}
              blocks={msg.blocks}
              isStreaming={false}
            />
          )
        )}

        {/* 流式内容 */}
        {hasStreamContent && (
          <AssistantMessage
            content={
              streamMessages
                .filter((b) => b.type === 'answer')
                .map((b) => b.content)
                .join('') || ''
            }
            blocks={streamMessages}
            isStreaming={isStreaming}
          />
        )}

        {/* 流式等待中：已开始但尚未收到任何内容 */}
        {isStreaming && !hasStreamContent && (
          <div className={styles.messageRow + ' ' + styles.assistantRow}>
            <div className={styles.assistantAvatar}>
              <RobotOutlined />
            </div>
            <div className={styles.loadingBubble}>
              <LoadingOutlined style={{ fontSize: 20, color: '#1677ff' }} />
              <span style={{ marginLeft: 10, color: '#999', fontSize: 14 }}>正在思考...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入区域 */}
      <ChatInput
        onSend={handleSend}
        disabled={isStreaming || !activeConversationId}
      />
    </div>
  )
}
