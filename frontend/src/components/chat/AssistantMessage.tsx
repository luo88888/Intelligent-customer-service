import { RobotOutlined } from '@ant-design/icons'
import ThinkingBlock from './ThinkingBlock'
import ToolResultBlock from './ToolResultBlock'
import RAGDocsBlock from './RAGDocsBlock'
import StreamingIndicator from './StreamingIndicator'
import MarkdownRenderer from '../common/MarkdownRenderer'
import type { StreamBlock } from '../../types/sse'
import styles from './ChatArea.module.css'

interface AssistantMessageProps {
  content: string
  blocks?: StreamBlock[]
  isStreaming?: boolean
}

export default function AssistantMessage({
  content,
  blocks,
  isStreaming = false,
}: AssistantMessageProps) {
  const hasBlocks = blocks && blocks.length > 0

  return (
    <div className={styles.messageRow + ' ' + styles.assistantRow}>
      <div className={styles.assistantAvatar}>
        <RobotOutlined />
      </div>
      <div className={styles.assistantContent}>
        {/* 渲染流式块 */}
        {hasBlocks &&
          blocks!.map((block) => {
            switch (block.type) {
              case 'thinking':
                return (
                  <ThinkingBlock
                    key={block.id}
                    content={block.content}
                    toolCalls={block.toolCalls}
                  />
                )
              case 'tool_result':
                return (
                  <ToolResultBlock
                    key={block.id}
                    toolName={block.toolName || '未知工具'}
                    content={block.content}
                  />
                )
              case 'rag_docs':
                return (
                  <RAGDocsBlock
                    key={block.id}
                    query={block.query || ''}
                    docs={block.docs || []}
                  />
                )
              case 'answer':
                return null // answer 内容在下方统一显示
              default:
                return null
            }
          })}

        {/* 最终回答 */}
        {content && (
          <div className={styles.assistantBubble}>
            <MarkdownRenderer>{content}</MarkdownRenderer>
          </div>
        )}

        {/* 流式进行中指示器 */}
        <StreamingIndicator visible={isStreaming && !content} />
      </div>
    </div>
  )
}
