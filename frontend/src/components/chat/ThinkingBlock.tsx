import { Tag } from 'antd'
import { BulbOutlined, ToolOutlined } from '@ant-design/icons'
import CollapsibleSection from '../common/CollapsibleSection'
import MarkdownRenderer from '../common/MarkdownRenderer'
import type { ToolCall } from '../../types/sse'

interface ThinkingBlockProps {
  content: string
  toolCalls?: ToolCall[]
}

export default function ThinkingBlock({ content, toolCalls }: ThinkingBlockProps) {
  return (
    <CollapsibleSection
      title="思考过程"
      icon={<BulbOutlined style={{ color: '#faad14' }} />}
      defaultCollapsed={true}
    >
      {content && (
        <div style={{ marginBottom: toolCalls?.length ? 12 : 0 }}>
          <MarkdownRenderer>{content}</MarkdownRenderer>
        </div>
      )}
      {toolCalls && toolCalls.length > 0 && (
        <div>
          <div style={{ fontWeight: 500, marginBottom: 6, fontSize: 12, color: '#999' }}>
            <ToolOutlined /> 计划调用工具：
          </div>
          {toolCalls.map((tc, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <Tag color="blue" style={{ marginBottom: 4 }}>{tc.name}</Tag>
              {tc.args && Object.keys(tc.args).length > 0 && (
                <pre
                  style={{
                    background: '#f5f5f5',
                    padding: '8px 12px',
                    borderRadius: 6,
                    fontSize: 12,
                    margin: 0,
                    overflow: 'auto',
                    maxHeight: 200,
                  }}
                >
                  {JSON.stringify(tc.args, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </CollapsibleSection>
  )
}
