import { useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, App } from 'antd'
import {
  UserOutlined,
  LockOutlined,
  RobotOutlined,
  SmileOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../../stores/authStore'
import styles from './AuthPages.module.css'

const { Title, Text } = Typography

interface RegisterFormValues {
  username: string
  password: string
  confirmPassword: string
  displayName: string
}

export default function RegisterPage() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const register = useAuthStore((s) => s.register)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/chat', { replace: true })
    }
  }, [isAuthenticated, navigate])

  const onFinish = async (values: RegisterFormValues) => {
    try {
      await register(
        values.username,
        values.password,
        values.displayName || undefined
      )
      message.success('注册成功，欢迎使用智扫通！')
      navigate('/chat', { replace: true })
    } catch (err) {
      message.error(err instanceof Error ? err.message : '注册失败')
    }
  }

  return (
    <div className={styles.container}>
      <Card className={styles.card} bordered={false}>
        <div className={styles.header}>
          <RobotOutlined className={styles.logo} />
          <Title level={3} className={styles.title}>创建账号</Title>
          <Text type="secondary">注册智扫通智能客服</Text>
        </div>

        <Form<RegisterFormValues>
          name="register"
          onFinish={onFinish}
          layout="vertical"
          size="large"
          autoComplete="off"
        >
          <Form.Item
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, max: 64, message: '用户名长度 3-64 个字符' },
              {
                pattern: /^[a-zA-Z0-9_]+$/,
                message: '仅支持字母、数字和下划线',
              },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
              autoFocus
            />
          </Form.Item>

          <Form.Item
            name="displayName"
            rules={[{ max: 128, message: '显示名称不超过 128 个字符' }]}
          >
            <Input
              prefix={<SmileOutlined />}
              placeholder="显示名称（可选）"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, max: 128, message: '密码长度 6-128 个字符' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
            />
          </Form.Item>

          <Form.Item
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="确认密码"
            />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              注册
            </Button>
          </Form.Item>
        </Form>

        <div className={styles.footer}>
          <Text type="secondary">已有账号？</Text>
          <Link to="/login">立即登录</Link>
        </div>
      </Card>
    </div>
  )
}
