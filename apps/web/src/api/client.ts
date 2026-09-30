import axios from 'axios'

let authRedirecting = false

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  // Product generation can make several sequential model calls; image creation
  // can add another server-side wait.  The previous 20 s browser timeout made a
  // successful Live request look like a generic failure to the operator.
  timeout: 240000,
  headers: { 'Content-Type': 'application/json' }
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('stayscape_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('stayscape_token')
      localStorage.removeItem('stayscape_user')
      // A cached user object can let Vue Router mount protected pages before
      // the expired JWT is rejected. Reset the in-memory Pinia state as well
      // by returning through the login route, preserving the intended page.
      if (!authRedirecting && window.location.pathname !== '/login') {
        authRedirecting = true
        const redirect = `${window.location.pathname}${window.location.search}${window.location.hash}`
        window.location.replace(`/login?redirect=${encodeURIComponent(redirect)}`)
      }
    }
    return Promise.reject(error)
  }
)

export function errorMessage(error: unknown): string {
  const typed = error as { code?: string; response?: { data?: { error?: { code?: string; message?: string; suggestion?: string } } }; config?: { url?: string } }
  if (typed.code === 'ECONNABORTED') {
    if (typed.config?.url?.endsWith('/hotel/dashboard') || typed.config?.url?.endsWith('/hotel/products')) return '经营数据请求超时，请稍后重试。'
    return '生成耗时较长，浏览器已停止等待；请稍后刷新产品池查看结果。'
  }
  const detail = typed.response?.data?.error
  if (!detail?.message) return '请求失败，请稍后重试'
  return detail.suggestion ? `${detail.message}（${detail.suggestion}）` : detail.message
}

export default api
