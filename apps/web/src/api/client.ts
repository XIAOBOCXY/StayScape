import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 20000,
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
    }
    return Promise.reject(error)
  }
)

export function errorMessage(error: unknown): string {
  const response = (error as { response?: { data?: { error?: { message?: string } } } })?.response
  return response?.data?.error?.message || '请求失败，请稍后重试'
}

export default api

