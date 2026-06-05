import { Tag } from 'antd'
import { CheckCircleOutlined } from '@ant-design/icons'
import CollapsibleSection from '../common/CollapsibleSection'
import MarkdownRenderer from '../common/MarkdownRenderer'

interface ToolResultBlockProps {
  toolName: string
  content: string
}

export default function ToolResultBlock({ toolName, content }: ToolResultBlockProps) {
  return (
    <CollapsibleSection
      title={`工具结果：${toolName}`}
      icon={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
      defaultCollapsed={true}
    >
      <div style={{ marginBottom: 8 }}>
        <Tag color="green">{toolName}</Tag>
        <span style={{ fontSize: 12, color: '#999' }}>执行完成</span>
      </div>
      <MarkdownRenderer>{content}</MarkdownRenderer>
    </CollapsibleSection>
  )
}
