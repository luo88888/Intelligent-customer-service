// 认证相关类型定义

export interface RegisterRequest {
  username: string
  password: string
  display_name?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: number
  username: string
  display_name: string | null
}

export interface UserInfo {
  id: number
  username: string
  display_name: string | null
  created_at: string
}
