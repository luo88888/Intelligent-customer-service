import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // SSE 流式代理：禁用响应缓冲，让每个 chunk 立刻转发到浏览器
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // 对 SSE (text/event-stream) 响应关闭缓冲
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              // 标记为不缓冲 —— 数据块立刻写出
              proxyRes.headers['cache-control'] = 'no-cache'
              proxyRes.headers['x-accel-buffering'] = 'no'
            }
          })
        },
      },
      '/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
