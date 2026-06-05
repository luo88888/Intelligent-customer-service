import { request } from './client'
import type { LoginRequest, RegisterRequest, TokenResponse } from '../types/auth'

export async function login(data: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function register(data: RegisterRequest): Promise<TokenResponse> {
  return request<TokenResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
