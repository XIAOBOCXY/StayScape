import api from './client'
import type { Dashboard, HotelService, Merchant, PartnerResource, Room, TravelProduct, User, Recommendation } from '../types'

export const authApi = {
  login: (payload: { username: string; password: string }) => api.post<{ access_token: string; user: User }>('/auth/login', payload),
  me: () => api.get<User>('/auth/me')
}

export const hotelApi = {
  dashboard: () => api.get<Dashboard>('/hotel/dashboard', { timeout: 8000 }),
  rooms: (params?: { from_date?: string; days?: number }) => api.get<Room[]>('/hotel/rooms', { params }),
  createRoom: (payload: Record<string, unknown>) => api.post<Room>('/hotel/rooms', payload),
  updateRoom: (id: number, payload: Record<string, unknown>) => api.patch<Room>(`/hotel/rooms/${id}`, payload),
  uploadMedia: (file: File) => { const body = new FormData(); body.append('file', file); return api.post<{ image_url: string; image_source: string; image_attribution: string }>('/hotel/media/upload', body) },
  searchMedia: (query: string, limit = 8) => api.post<{ items: Array<{ title: string; preview_url: string; source_url: string; source: string; attribution: string; detail_url: string }> }>('/hotel/media/search', { query, limit }),
  importMedia: (payload: { url: string; source?: string; attribution?: string }) => api.post<{ image_url: string; image_source: string; image_attribution: string }>('/hotel/media/import', payload),
  services: () => api.get<HotelService[]>('/hotel/services'),
  updateService: (id: number, payload: Record<string, unknown>) => api.patch<HotelService>(`/hotel/services/${id}`, payload),
  merchants: () => api.get<Merchant[]>('/hotel/merchants'),
  resources: () => api.get<PartnerResource[]>('/hotel/resources'),
  createResource: (payload: Record<string, unknown>) => api.post<PartnerResource>('/hotel/resources', payload),
  updateResource: (id: number, payload: Record<string, unknown>) => api.patch<PartnerResource>(`/hotel/resources/${id}`, payload),
  updateResourceAddress: (id: number, address: string) => api.patch<PartnerResource>(`/hotel/resources/${id}/address`, { address }),
  toggleResourcePackage: (id: number, package_enabled: boolean) => api.patch<PartnerResource>(`/hotel/resources/${id}/package`, { package_enabled }),
  updateResourceMedia: (id: number, payload: { image_url: string; image_source: string; image_attribution: string }) => api.patch<PartnerResource>(`/hotel/resources/${id}/media`, payload),
  products: (status?: string, limit?: number, includeMarketingAssets = true, offset?: number, targetDate?: string) => api.get<{ items: TravelProduct[]; total: number; dates: Array<{ target_date: string; sale_quantity: number }> }>('/hotel/products', { params: { ...(status ? { status } : {}), ...(limit ? { limit } : {}), ...(offset !== undefined ? { offset } : {}), ...(targetDate ? { target_date: targetDate } : {}), include_marketing_assets: includeMarketingAssets }, timeout: 30000 }),
  generateProduct: (payload: Record<string, unknown>) => api.post<{ product: TravelProduct; products: TravelProduct[]; trace_id: string; trace_ids: string[]; validation: Record<string, unknown>; fallback_used: boolean; provider: string; transport: string; agent_id: string; skill_name: string; skill_version: string }>('/hotel/products/generate', payload),
  interpretProductDraft: (natural_language: string) => api.post<{ interpreted: Record<string, unknown>; parsed_fields: Array<{ field: string; label: string; value: unknown }>; message: string }>('/hotel/products/interpret', { natural_language }),
  refineProductMarketing: (payload: { product_ids: number[]; natural_language: string; style?: 'ARTISTIC' | 'PROMOTIONAL' | 'EMPATHETIC' | 'SEEDING'; generate_image?: boolean }) => api.post<TravelProduct[]>('/hotel/products/refine-marketing', payload),
  product: (id: number) => api.get<TravelProduct>(`/hotel/products/${id}`),
  updateProduct: (id: number, payload: Record<string, unknown>) => api.patch<TravelProduct>(`/hotel/products/${id}`, payload),
  batchApplyProduct: (id: number, targets: Array<{ target_date: string; room_inventory_id: number }>) => api.post<{ created: Array<Record<string, any>>; skipped: Array<Record<string, any>>; created_count: number; skipped_count: number }>(`/hotel/products/${id}/batch-apply`, { targets }),
  rewriteProductCopy: (id: number, payload: { field: string; current_text: string; context?: string }) => api.post<{ replacement_text: string; field: string; trace_id: string; fallback_used: boolean }>(`/hotel/products/${id}/copy-rewrite`, payload),
  refineProduct: (id: number, natural_language: string) => api.post<{
    layer: string
    layer_label: string
    version: number
    changes: Array<Record<string, any>>
    checks: Array<Record<string, any>>
    message: string
    product: TravelProduct
  }>(`/hotel/products/${id}/refine`, { natural_language }),
  productRefinements: (id: number) => api.get<{ version: number; items: Array<Record<string, any>> }>(`/hotel/products/${id}/refinements`),
  rollbackRefinement: (id: number, refinementId: number) => api.post<Record<string, any> & { product: TravelProduct }>(`/hotel/products/${id}/refinements/${refinementId}/rollback`, {}),
  deleteProduct: (id: number) => api.delete<{ deleted: boolean; archived: boolean; message: string }>(`/hotel/products/${id}`),
  regenerateMarketing: (id: number, payload: { style?: 'ARTISTIC' | 'PROMOTIONAL' | 'EMPATHETIC' | 'SEEDING'; generate_image?: boolean } = {}) => api.post<TravelProduct>(`/hotel/products/${id}/marketing-assets`, payload),
  productStatus: (id: number, status: string) => api.patch<TravelProduct>(`/hotel/products/${id}/status`, { status }),
  changes: () => api.get<Array<Record<string, unknown>>>('/hotel/changes'),
  intents: () => api.get<Array<Record<string, unknown>>>('/hotel/intents'),
  updateIntent: (id: number, status: 'CONFIRMED' | 'CANCELLED') => api.patch<Record<string, unknown>>(`/hotel/intents/${id}`, { status }),
  skillLogs: () => api.get<Array<Record<string, unknown>>>('/hotel/skill-logs'),
  agentDiagnostics: () => api.get<Record<string, unknown>>('/hotel/agent-diagnostics'),
  aiOverview: (params?: { section?: string; target_date?: string }) => api.get<Record<string, unknown>>('/hotel/ai/overview', { params, timeout: 8000 }),
  aiConversations: (limit = 1) => api.get<Array<Record<string, unknown>>>('/hotel/ai/conversations', { params: { limit }, timeout: 8000 }),
  createAiConversation: (title = '酒店 AI 运营任务') => api.post<Record<string, unknown>>('/hotel/ai/conversations', { title }),
  sendAiMessage: (conversationId: number, natural_language: string) => api.post<Record<string, unknown>>(`/hotel/ai/conversations/${conversationId}/messages`, { natural_language }),
  analyzeOperationsQuestion: (conversationId: number, query: string) => api.post<Record<string, any>>(`/hotel/ai/conversations/${conversationId}/analysis`, { query }),
  advisor: (conversationId: number, natural_language: string, auto = false) => api.post<{
    conversation: Record<string, any>
    advisor: Record<string, any>
    proposals: Array<Record<string, any>>
  }>(`/hotel/ai/conversations/${conversationId}/advisor`, { natural_language, auto }),
  aiProposals: (status?: string, conversationId?: number) => api.get<Array<Record<string, unknown>>>('/hotel/ai/proposals', { params: { ...(status ? { status } : {}), ...(conversationId ? { conversation_id: conversationId } : {}), limit: 10 } }),
  confirmAiProposal: (proposalId: number, action: 'DRAFT' | 'PUBLISH') => api.post<Record<string, unknown>>(`/hotel/ai/proposals/${proposalId}/confirm`, { action }),
  clearAiConversation: (conversationId: number) => api.post<Record<string, unknown>>(`/hotel/ai/conversations/${conversationId}/clear`),
  deleteAiConversation: (conversationId: number) => api.delete<Record<string, unknown>>(`/hotel/ai/conversations/${conversationId}`),
  knowledge: (params?: { q?: string; category?: string; limit?: number }) => api.get<{ items: Array<Record<string, unknown>>; categories: string[]; total: number; disclosure: string }>('/hotel/knowledge', { params }),
  refreshKnowledge: () => api.post<{ checked: number; refreshed: number; failed_count: number; failed: Array<{ name: string; reason: string }>; checked_at: string }>('/hotel/knowledge/refresh'),
  salesCommand: (natural_language: string) => api.post<{ action: string; scope: string; affected: Array<Record<string, unknown>>; message: string }>('/hotel/products/sales-command', { natural_language }),
  ordersOverview: () => api.get<{
    total: number
    confirmed: number
    held: number
    cancelled: number
    confirmed_revenue: string
    sold_product_count: number
    estimated_amount_count: number
    categories: Array<{ label: string; count: number; confirmed: number; revenue: string }>
    recent: { from_date: string; confirmed_count: number; confirmed_revenue: string; average_order_value: string | null; estimated_amount_count: number; top_crowds: Array<{ target_crowd: string; confirmed_orders: number; share: number }>; top_products: Array<{ product_id: number; product_name: string; confirmed_orders: number; revenue: string }>; orders: Array<Record<string, any>> }
    orders: Array<{ id: number; product_id: number; product_name: string; category: string; amount: string | null; amount_is_estimate: boolean; target_date: string; created_at: string; confirmed_at: string | null; status: string; product_status: string; contact_name: string; contact_phone: string; note: string }>
  }>('/hotel/orders/overview'),
  integrationSettings: () => api.get<Record<string, any>>('/hotel/settings/integrations'),
  updateIntegrationSettings: (payload: Record<string, unknown>) => api.put<Record<string, any>>('/hotel/settings/integrations', payload),
  agentTokens: () => api.get<{ items: Array<{ id: number; name: string; is_active: boolean; created_at: string; last_used_at: string | null }> }>('/hotel/agent-tokens'),
  createAgentToken: (name: string) => api.post<{ token: string; item: { id: number; name: string; is_active: boolean; created_at: string; last_used_at: string | null }; notice: string }>('/hotel/agent-tokens', { name }),
  revokeAgentToken: (id: number) => api.post<{ revoked: boolean }>(`/hotel/agent-tokens/${id}/revoke`),
  wsTicket: () => api.post<{ ticket: string; expires_in: number }>('/hotel/ws-ticket'),
  exportData: () => api.get<Record<string, unknown>>('/hotel/settings/export')
}

export const merchantApi = {
  dashboard: () => api.get<Record<string, unknown>>('/merchant/dashboard'),
  resources: () => api.get<PartnerResource[]>('/merchant/resources'),
  uploadMedia: (file: File) => { const body = new FormData(); body.append('file', file); return api.post<{ image_url: string; image_source: string; image_attribution: string }>('/merchant/media/upload', body) },
  searchMedia: (query: string, limit = 8) => api.post<{ items: Array<{ title: string; preview_url: string; source_url: string; source: string; attribution: string; detail_url: string }> }>('/merchant/media/search', { query, limit }),
  importMedia: (payload: { url: string; source?: string; attribution?: string }) => api.post<{ image_url: string; image_source: string; image_attribution: string }>('/merchant/media/import', payload),
  createResource: (payload: Record<string, unknown>) => api.post<PartnerResource>('/merchant/resources', payload),
  updateResource: (id: number, payload: Record<string, unknown>) => api.patch<Record<string, unknown>>(`/merchant/resources/${id}`, payload),
  references: (id: number) => api.get<Array<Record<string, unknown>>>(`/merchant/resources/${id}/references`),
  changes: () => api.get<Array<Record<string, unknown>>>('/merchant/changes')
}

export const visitorApi = {
  products: (params?: Record<string, unknown>) => api.get<TravelProduct[]>('/visitor/products', { params }),
  product: (id: number, nights = 1, roomInventoryId?: number | null) => api.get<TravelProduct>(`/visitor/products/${id}`, { params: roomInventoryId ? { nights, room_inventory_id: roomInventoryId } : { nights } }),
  productDates: (id: number) => api.get<{ theme: string; dates: Array<{ id: number; target_date: string; weekday: string; sale_quantity: number; status: string; price: string; room_type: string }> }>(`/visitor/products/${id}/dates`),
  productRooms: (id: number) => api.get<{ product_id: number; date: string; rooms: Array<{ room_inventory_id: number; room_type: string; max_guests: number; features: string; price: string; price_delta: string; sale_quantity: number; available: boolean; is_current: boolean }> }>(`/visitor/products/${id}/rooms`),
  productAlternatives: (id: number) => api.get<{ date: string; current_room_type: string; room_types: Array<Record<string, any>>; same_room_packages: Array<Record<string, any>> }>(`/visitor/products/${id}/alternatives`),
  consult: (payload: Record<string, unknown>) => api.post<Record<string, unknown>>('/visitor/consult', payload),
  assistantIntro: (productId?: number | null) => api.get<{ greeting: string; suggestions: string[] }>('/visitor/assistant/intro', { params: productId ? { product_id: productId } : undefined }),
  interpret: (payload: { natural_language: string }) => api.post<{ interpreted_needs: Record<string, unknown>; follow_up_questions: string[] }>('/visitor/interpret', payload),
  recommend: (payload: Record<string, unknown>) => api.post<{ results: Recommendation[]; trace_id: string; fallback_used: boolean; interpreted_needs: Record<string, unknown>; provider: string; skill_name: string; skill_version: string }>('/visitor/recommend', payload),
  intent: (payload: Record<string, unknown>) => api.post<Record<string, unknown>>('/visitor/intents', payload),
  publicResources: (weather = 'RAIN') => api.get<Array<Record<string, unknown>>>('/visitor/public-resources', { params: { weather } }),
  guides: (query: string, near?: string) => api.get<Array<{
    source: string
    title: string
    summary: string
    content?: string
    url: string
    address?: string
    area?: string
    category_label?: string
    crowds_label?: string
    weather_label?: string
    duration_minutes?: number | null
    opening_hours?: string
    reservation_notice?: string
    best_time?: string
    transport?: string
    verified_at?: string | null
    verification_status?: string
  }>>('/visitor/guides', { params: near ? { query, near } : { query } })
}

export const demoApi = {
  seed: () => api.post<Record<string, unknown>>('/demo/seed'),
  reset: () => api.post<Record<string, unknown>>('/demo/reset')
}

export { api }
