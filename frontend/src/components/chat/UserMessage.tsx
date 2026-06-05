import { UserOutlined } from '@ant-design/icons'
import MarkdownRenderer from '../common/MarkdownRenderer'
import styles from './ChatArea.module.css'

interface UserMessageProps {
  content: string
}

export default function UserMessage({ content }: UserMessageProps) {
  return (
    <div className={styles.messageRow + ' ' + styles.userRow}>
      <div className={styles.userBubble}>
        <MarkdownRenderer>{content}</MarkdownRenderer>
      </div>
      <div className={styles.userAvatar}>
        <UserOutlined />
      </div>
    </div>
  )
}
