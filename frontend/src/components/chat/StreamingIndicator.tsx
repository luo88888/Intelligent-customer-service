import { LoadingOutlined } from '@ant-design/icons'
import styles from './ChatArea.module.css'

interface StreamingIndicatorProps {
  visible: boolean
}

export default function StreamingIndicator({ visible }: StreamingIndicatorProps) {
  if (!visible) return null

  return (
    <div className={styles.streamingIndicator}>
      <LoadingOutlined style={{ marginRight: 8 }} />
      <span>正在思考中...</span>
    </div>
  )
}
