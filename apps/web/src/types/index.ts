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
  suitable_crowds: string
  tags: string
  image_url?: string
  image_source?: string
  image_attribution?: string
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
  image_url?: string
  image_source?: string
  image_attribution?: string
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
  image_url?: string
  image_source?: string
  image_attribution?: string
  package_enabled: boolean
  source_type: string
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
  available_date?: string
  start_time?: string
  end_time?: string
  address?: string
  description?: string
  booking_notice?: string
  cancellation_rule?: string
  image_url?: string
  image_source?: string
  image_attribution?: string
}

export interface MarketingAsset {
  asset_type: 'POSTER' | 'SOCIAL_POST' | 'SHORT_VIDEO_SCRIPT' | 'STORE_CARD'
  platform: string
  title: string
  content: string
  visual_brief: string
  call_to_action: string
  poster_svg?: string
  creative_angle?: string
  poster_style?: string
  copy_style?: string
  image_url?: string
  image_source?: string
  image_model?: string
  image_watermarked?: boolean
  image_request_id?: string
}

export interface StayOption {
  nights: number
  days: number
  label: string
  check_in?: string | null
  check_out?: string | null
  price: string
  available: boolean
}

export interface StayPlan extends StayOption {
  room_type: string
  room_name: string
  hotel_name: string
  hotel_address?: string
  requested_nights: number
  adjusted: boolean
  max_nights: number
  check_in_time: string
  check_out_time: string
  options: StayOption[]
}

export interface DayItem {
  time: string
  title: string
  description: string
  kind: string
  slot?: string
  slot_label?: string
  duration_minutes?: number | null
  duration_text?: string
  notes?: string
  address?: string
  included?: boolean
  route_only?: boolean
  area?: string
  source_name?: string
  source_url?: string
  verification_status?: string
  opening_hours?: string
  reservation_notice?: string
  route_role?: string
  schedule_conflict?: boolean
  recommended_buffer_minutes?: number | null
}

export interface DayPlan {
  day_index: number
  label: string
  date?: string | null
  title: string
  summary: string
  slot_summary?: string
  items: DayItem[]
}

export interface RouteStop {
  time: string
  title: string
  address: string
  kind: string
  slot: string
  included?: boolean
  route_only?: boolean
  source_name?: string
  source_url?: string
}

export interface RouteLeg {
  from_stop: string
  to_stop: string
  mode: string
  minutes: number
  note: string
  distance_label?: string
}

export interface DayRoute {
  day_index: number
  label: string
  date?: string | null
  title: string
  summary: string
  stops: RouteStop[]
  legs: RouteLeg[]
}

export interface ExperienceDetail {
  name: string
  time: string
  duration: string
  address: string
  included: string
  extra_cost: string
  feature: string
  tips: string
  source_note: string
}

export interface DetailSections {
  intro: string[]
  experience_details: ExperienceDetail[]
  spend_notes: string[]
  tips: string[]
}

export interface ProductReview {
  id: number
  author_name: string
  author_tag: string
  rating: string | number
  content: string
  highlights: string[]
  source: string
  stayed_on?: string | null
}

export interface TravelProduct {
  id: number
  hotel_id: number
  product_code: string
  product_name: string
  theme: string
  target_crowd: string
  party_size: number
  weather: string
  target_date: string
  room_inventory_id: number
  listed_quantity: number
  sale_quantity: number
  sold_quantity?: number
  unit_cost: string
  minimum_allowed_price: string
  suggested_price: string
  gross_profit: string
  gross_margin: string
  minimum_gross_margin_requirement?: string
  visitor_budget_limit?: string
  price_anchor?: string
  bottleneck_resource?: string
  marketing_title: string
  marketing_content: string
  marketing_assets: MarketingAsset[]
  recommendation_reason: string
  risk_message: string
  status: string
  created_at: string
  updated_at: string
  resources: ProductResource[]
  stay?: StayPlan | null
  day_plan?: DayPlan[]
  route_plan?: DayRoute[]
  detail_sections?: DetailSections | null
  reviews?: ProductReview[]
  rating_average?: string | number | null
  rating_count?: number
  visitor_copy?: Record<string, any>
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
  confirmed_order_count: number
  confirmed_revenue: string
  confirmed_gross_profit: string
  held_order_count: number
  held_revenue: string
  available_package_count: number
  listed_value: string
  sales_timeline: Array<{
    date: string
    confirmed_orders: number
    confirmed_revenue: string
    confirmed_gross_profit: string
    on_sale_products: number
    available_packages: number
    listed_value: string
  }>
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
  provider?: string
  skill_name?: string
  fallback_used?: boolean
}
