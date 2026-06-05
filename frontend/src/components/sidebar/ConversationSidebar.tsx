import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button,
  List,
  Typography,
  Dropdown,
  App,
  Spin,
  Empty,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  MessageOutlined,
  RobotOutlined,
  LogoutOutlined,
  MoreOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useConversationStore } from '../../stores/conversationStore'
import { useAuthStore } from '../../stores/authStore'
import { useChatStore } from '../../stores/chatStore'
import styles from './ConversationSidebar.module.css'

const { Text } = Typography

interface ConversationSidebarProps {
  onSelect: (id: number) => void
  onNew: () => void
}

export default function ConversationSidebar({
  onSelect,
  onNew,
}: ConversationSidebarProps) {
  const navigate = useNavigate()
  const { message: msg } = App.useApp()
  const conversations = useConversationStore((s) => s.conversations)
  const loading = useConversationStore((s) => s.loading)
  const activeId = useConversationStore((s) => s.activeConversationId)
  const fetchConversations = useConversationStore((s) => s.fetchConversations)
  const createConversation = useConversationStore((s) => s.createConversation)
  const deleteConversation = useConversationStore((s) => s.deleteConversation)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const clearMessages = useChatStore((s) => s.clearMessages)
  const isStreaming = useChatStore((s) => s.isStreaming)

  useEffect(() => {
    fetchConversations()
  }, [fetchConversations])

  const handleCreate = async () => {
    try {
      const id = await createConversation()
      onSelect(id)
      navigate(`/chat/${id}`)
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '创建会话失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteConversation(id)
      if (activeId === id) {
        clearMessages()
        onNew()
        navigate('/chat')
      }
      msg.success('会话已删除')
    } catch (err) {
      msg.error(err instanceof Error ? err.message : '删除会话失败')
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return `${diffMins}分钟前`
    if (diffHours < 24) return `${diffHours}小时前`
    if (diffDays < 7) return `${diffDays}天前`
    return date.toLocaleDateString('zh-CN')
  }

  return (
    <div className={styles.sidebar}>
      {/* 头部 */}
      <div className={styles.header}>
        <div className={styles.brand}>
          <RobotOutlined className={styles.brandIcon} />
          <Text strong className={styles.brandName}>智扫通</Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleCreate}
          className={styles.newBtn}
          disabled={isStreaming}
        >
          新建会话
        </Button>
      </div>

      {/* 会话列表 */}
      <div className={styles.listWrapper}>
        {loading && conversations.length === 0 ? (
          <div className={styles.loading}>
            <Spin tip="加载中..." />
          </div>
        ) : conversations.length === 0 ? (
          <Empty
            className={styles.empty}
            description="暂无会话"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Button type="primary" onClick={handleCreate}>
              开始新对话
            </Button>
          </Empty>
        ) : (
          <List
            dataSource={conversations}
            renderItem={(item) => (
              <List.Item
                className={`${styles.convItem} ${
                  activeId === item.id ? styles.active : ''
                }`}
                onClick={() => onSelect(item.id)}
              >
                <div className={styles.convContent}>
                  <div className={styles.convIcon}>
                    <MessageOutlined />
                  </div>
                  <div className={styles.convInfo}>
                    <Text
                      className={styles.convTitle}
                      ellipsis={{ tooltip: item.title || '新对话' }}
                    >
                      {item.title || '新对话'}
                    </Text>
                    <div className={styles.convMeta}>
                      <Text type="secondary" className={styles.convPreview}>
                        {item.last_message_preview || '暂无消息'}
                      </Text>
                      <Text type="secondary" className={styles.convTime}>
                        {formatTime(item.updated_at)}
                      </Text>
                    </div>
                  </div>
                </div>

                <Dropdown
                  menu={{
                    items: [
                      {
                        key: 'delete',
                        label: '删除会话',
                        icon: <DeleteOutlined />,
                        danger: true,
                        onClick: (e) => {
                          e.domEvent.stopPropagation()
                          handleDelete(item.id)
                        },
                      },
                    ],
                  }}
                  trigger={['click']}
                >
                  <Button
                    type="text"
                    size="small"
                    icon={<MoreOutlined />}
                    className={styles.moreBtn}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Dropdown>
              </List.Item>
            )}
          />
        )}
      </div>

      {/* 用户信息 */}
      <div className={styles.userBar}>
        <div className={styles.userInfo}>
          <UserOutlined className={styles.userIcon} />
          <Text className={styles.userName}>
            {user?.display_name || user?.username || '用户'}
          </Text>
        </div>
        <Button
          type="text"
          icon={<LogoutOutlined />}
          onClick={handleLogout}
          title="退出登录"
        />
      </div>
    </div>
  )
}
