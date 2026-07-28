export type Role = 'HOTEL' | 'MERCHANT' | 'VISITOR'

export interface User {
  id: number
  username: string
  role: Role
  status: string
}

export interface Room {
  id: number
  hotel_id: number
  room_type: string
  available_date: string
  available_count: number
  normal_price: string
  minimum_price: string
  accounting_cost: string
  max_guests: number
  features: string
  status: string
  updated_at: string
}

export interface HotelService {
  id: number
  hotel_id: number
  service_name: string
  service_type: string
  available_date: string
  available_quantity: number
  unit_cost: string
  reference_price: string
  start_time?: string
  end_time?: string
  suitable_crowds: string
  replaceable: boolean
  status: string
}

export interface Merchant {
  id: number
  hotel_id: number
  merchant_name: string
  category: string
  contact_name: string
  contact_phone: string
  cooperation_status: string
}

export interface PartnerResource {
  id: number
  merchant_id: number
  resource_name: string
  category: string
  description: string
  available_date: string
  start_time?: string
  end_time?: string
  remaining_capacity: number
  settlement_price: string
  market_price: string
  suitable_crowds: string
  minimum_age?: number
  maximum_age?: number
  indoor: boolean
  weather_tags: string
  address: string
  booking_notice: string
  cancellation_rule: string
  package_enabled: boolean
  status: string
  updated_at: string
  merchant_name?: string
  referenced_product_count: number
}

export interface ProductResource {
  id: number
  resource_type: string
  resource_id: number
  resource_name: string
  quantity_per_package: number
  unit_cost: string
  replaceable: boolean
  required: boolean
}

export interface TravelProduct {
  id: number
  hotel_id: number
  product_code: string
  product_name: string
  theme: string
  target_crowd: string
  weather: string
  target_date: string
  room_inventory_id: number
  sale_quantity: number
  unit_cost: string
  minimum_allowed_price: string
  suggested_price: string
  gross_profit: string
  gross_margin: string
  bottleneck_resource?: string
  marketing_title: string
  marketing_content: string
  recommendation_reason: string
  risk_message: string
  status: string
  created_at: string
  updated_at: string
  resources: ProductResource[]
}

export interface Adjustment {
  id: number
  product_id: number
  change_event_id?: number
  old_quantity: number
  new_quantity: number
  old_price: string
  new_price: string
  action: string
  replacement_resource_id?: number
  reason: string
  created_at: string
}

export interface Dashboard {
  hotel_id: number
  hotel_name: string
  target_date: string
  room_count: number
  expiring_room_count: number
  available_room_units: number
  partner_resource_count: number
  package_enabled_resource_count: number
  product_count: number
  on_sale_product_count: number
  low_stock_product_count: number
  visitor_intent_count: number
  gross_profit_on_sale: string
  recent_changes: Array<Record<string, unknown>>
}

export interface Recommendation {
  product: TravelProduct
  score: number
  recommendation_reason: string
  budget_match: boolean
  children_match: boolean
  weather_match: boolean
  interest_match: boolean
  schedule: Array<{ time: string; title: string; description: string }>
  limited_adjustments: string[]
  allergy_warning?: string
}
