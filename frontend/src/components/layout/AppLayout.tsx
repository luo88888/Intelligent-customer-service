import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Layout } from 'antd'
import { useConversationStore } from '../../stores/conversationStore'
import { useChatStore } from '../../stores/chatStore'
import ConversationSidebar from '../sidebar/ConversationSidebar'
import ChatArea from '../chat/ChatArea'
import styles from './AppLayout.module.css'

const { Sider, Content } = Layout

export default function AppLayout() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const setActiveConversation = useConversationStore((s) => s.setActiveConversation)
  const activeConversationId = useConversationStore((s) => s.activeConversationId)
  const loadMessages = useChatStore((s) => s.loadMessages)

  // 同步 URL 参数到 store
  useEffect(() => {
    const id = conversationId ? Number(conversationId) : null
    if (id && id !== activeConversationId) {
      setActiveConversation(id)
      loadMessages(id)
    } else if (!id) {
      setActiveConversation(null)
      useChatStore.getState().clearMessages()
    }
  }, [conversationId, activeConversationId, setActiveConversation, loadMessages])

  const handleSelectConversation = (id: number) => {
    setActiveConversation(id)
    loadMessages(id)
    navigate(`/chat/${id}`)
  }

  const handleNewConversation = () => {
    setActiveConversation(null)
    useChatStore.getState().clearMessages()
    navigate('/chat')
  }

  return (
    <Layout className={styles.layout}>
      <Sider
        width={320}
        className={styles.sider}
        breakpoint="md"
        collapsedWidth={0}
        trigger={null}
      >
        <ConversationSidebar
          onSelect={handleSelectConversation}
          onNew={handleNewConversation}
        />
      </Sider>
      <Content className={styles.content}>
        <ChatArea />
      </Content>
    </Layout>
  )
}
