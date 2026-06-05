import { getToken, removeToken } from '../utils/token'

const BASE_URL = ''

// 用于在 401 时触发登出回调
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken()
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    removeToken()
    onUnauthorized?.()
    throw new ApiError(401, '未授权，请重新登录')
  }

  if (response.status === 204) {
    return undefined as T
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: '请求失败' }))
    throw new ApiError(response.status, errorBody.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/** 发起 SSE 流式请求，返回原始 Response 供 ReadableStream 消费 */
async function streamRequest(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = getToken()
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    removeToken()
    onUnauthorized?.()
    throw new ApiError(401, '未授权，请重新登录')
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: '请求失败' }))
    throw new ApiError(response.status, errorBody.detail || `HTTP ${response.status}`)
  }

  return response
}

export { request, streamRequest }
