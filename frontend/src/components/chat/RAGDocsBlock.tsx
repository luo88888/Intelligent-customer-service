import { Tag } from 'antd'
import { FileTextOutlined, SearchOutlined } from '@ant-design/icons'
import CollapsibleSection from '../common/CollapsibleSection'

interface RAGDocsBlockProps {
  query: string
  docs: string[]
}

export default function RAGDocsBlock({ query, docs }: RAGDocsBlockProps) {
  return (
    <CollapsibleSection
      title={`检索文档（${docs.length} 篇）`}
      icon={<FileTextOutlined style={{ color: '#722ed1' }} />}
      defaultCollapsed={true}
    >
      <div style={{ marginBottom: 12 }}>
        <SearchOutlined style={{ marginRight: 6, color: '#999' }} />
        <span style={{ fontSize: 12, color: '#999' }}>查询词：</span>
        <Tag color="purple">{query}</Tag>
      </div>
      {docs.map((doc, i) => (
        <div
          key={i}
          style={{
            marginBottom: 12,
            padding: '10px 12px',
            background: '#fafafa',
            borderRadius: 8,
            border: '1px solid #f0f0f0',
          }}
        >
          <div
            style={{
              fontSize: 11,
              color: '#999',
              marginBottom: 6,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <FileTextOutlined />
            文档片段 {i + 1}
          </div>
          <div
            style={{
              fontSize: 13,
              lineHeight: 1.8,
              color: '#333',
              maxHeight: 180,
              overflowY: 'auto',
            }}
          >
            {doc.length > 500 ? doc.slice(0, 500) + '...' : doc}
          </div>
        </div>
      ))}
    </CollapsibleSection>
  )
}
