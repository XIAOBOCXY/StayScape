import api from './client'
import type { Dashboard, HotelService, Merchant, PartnerResource, Room, TravelProduct, User, Recommendation } from '../types'

export const authApi = {
  login: (payload: { username: string; password: string }) => api.post<{ access_token: string; user: User }>('/auth/login', payload),
  me: () => api.get<User>('/auth/me')
}

export const hotelApi = {
  dashboard: () => api.get<Dashboard>('/hotel/dashboard'),
  rooms: () => api.get<Room[]>('/hotel/rooms'),
  createRoom: (payload: Record<string, unknown>) => api.post<Room>('/hotel/rooms', payload),
  updateRoom: (id: number, payload: Record<string, unknown>) => api.patch<Room>(`/hotel/rooms/${id}`, payload),
  services: () => api.get<HotelService[]>('/hotel/services'),
  updateService: (id: number, payload: Record<string, unknown>) => api.patch<HotelService>(`/hotel/services/${id}`, payload),
  merchants: () => api.get<Merchant[]>('/hotel/merchants'),
  resources: () => api.get<PartnerResource[]>('/hotel/resources'),
  toggleResourcePackage: (id: number, package_enabled: boolean) => api.patch<PartnerResource>(`/hotel/resources/${id}/package`, { package_enabled }),
  products: (status?: string) => api.get<{ items: TravelProduct[]; total: number }>('/hotel/products', { params: status ? { status } : undefined }),
  generateProduct: (payload: Record<string, unknown>) => api.post<{ product: TravelProduct; products: TravelProduct[]; trace_id: string; trace_ids: string[]; validation: Record<string, unknown>; fallback_used: boolean; provider: string; transport: string; agent_id: string; skill_name: string; skill_version: string }>('/hotel/products/generate', payload),
  interpretProductDraft: (natural_language: string) => api.post<{ interpreted: Record<string, unknown>; parsed_fields: Array<{ field: string; label: string; value: unknown }>; message: string }>('/hotel/products/interpret', { natural_language }),
  product: (id: number) => api.get<TravelProduct>(`/hotel/products/${id}`),
  updateProduct: (id: number, payload: Record<string, unknown>) => api.patch<TravelProduct>(`/hotel/products/${id}`, payload),
  deleteProduct: (id: number) => api.delete<{ deleted: boolean; archived: boolean; message: string }>(`/hotel/products/${id}`),
  regenerateMarketing: (id: number, payload: { style?: 'ARTISTIC' | 'PROMOTIONAL' | 'EMPATHETIC' | 'SEEDING'; generate_image?: boolean; image_model?: 'wan2.7-image' | 'wan2.7-image-pro' } = {}) => api.post<TravelProduct>(`/hotel/products/${id}/marketing-assets`, payload),
  productStatus: (id: number, status: string) => api.patch<TravelProduct>(`/hotel/products/${id}/status`, { status }),
  changes: () => api.get<Array<Record<string, unknown>>>('/hotel/changes'),
  intents: () => api.get<Array<Record<string, unknown>>>('/hotel/intents'),
  updateIntent: (id: number, status: 'CONFIRMED' | 'CANCELLED') => api.patch<Record<string, unknown>>(`/hotel/intents/${id}`, { status }),
  skillLogs: () => api.get<Array<Record<string, unknown>>>('/hotel/skill-logs'),
  agentDiagnostics: () => api.get<Record<string, unknown>>('/hotel/agent-diagnostics')
}

export const merchantApi = {
  dashboard: () => api.get<Record<string, unknown>>('/merchant/dashboard'),
  resources: () => api.get<PartnerResource[]>('/merchant/resources'),
  createResource: (payload: Record<string, unknown>) => api.post<PartnerResource>('/merchant/resources', payload),
  updateResource: (id: number, payload: Record<string, unknown>) => api.patch<Record<string, unknown>>(`/merchant/resources/${id}`, payload),
  references: (id: number) => api.get<Array<Record<string, unknown>>>(`/merchant/resources/${id}/references`),
  changes: () => api.get<Array<Record<string, unknown>>>('/merchant/changes')
}

export const visitorApi = {
  products: (params?: Record<string, unknown>) => api.get<TravelProduct[]>('/visitor/products', { params }),
  product: (id: number) => api.get<TravelProduct>(`/visitor/products/${id}`),
  consult: (payload: Record<string, unknown>) => api.post<Record<string, unknown>>('/visitor/consult', payload),
  interpret: (payload: { natural_language: string }) => api.post<{ interpreted_needs: Record<string, unknown>; follow_up_questions: string[] }>('/visitor/interpret', payload),
  recommend: (payload: Record<string, unknown>) => api.post<{ results: Recommendation[]; trace_id: string; fallback_used: boolean; interpreted_needs: Record<string, unknown>; provider: string; skill_name: string; skill_version: string }>('/visitor/recommend', payload),
  intent: (payload: Record<string, unknown>) => api.post<Record<string, unknown>>('/visitor/intents', payload),
  publicResources: (weather = 'RAIN') => api.get<Array<Record<string, unknown>>>('/visitor/public-resources', { params: { weather } })
}

export const demoApi = {
  seed: () => api.post<Record<string, unknown>>('/demo/seed'),
  reset: () => api.post<Record<string, unknown>>('/demo/reset')
}

export { api }
