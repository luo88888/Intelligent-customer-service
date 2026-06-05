import { useState, type ReactNode } from 'react'
import { Button } from 'antd'
import { DownOutlined, RightOutlined } from '@ant-design/icons'
import styles from './CollapsibleSection.module.css'

interface CollapsibleSectionProps {
  title: string
  icon?: ReactNode
  defaultCollapsed?: boolean
  children: ReactNode
}

export default function CollapsibleSection({
  title,
  icon,
  defaultCollapsed = true,
  children,
}: CollapsibleSectionProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  return (
    <div className={styles.section}>
      <Button
        type="text"
        className={styles.header}
        onClick={() => setCollapsed(!collapsed)}
        icon={collapsed ? <RightOutlined /> : <DownOutlined />}
      >
        {icon && <span className={styles.icon}>{icon}</span>}
        <span className={styles.title}>{title}</span>
      </Button>
      {!collapsed && <div className={styles.body}>{children}</div>}
    </div>
  )
}
