export const VISITOR_PROFILE_KEY = 'stayscape.visitor.confirmed-profile'
export const VISITOR_CONVERSATION_KEY = 'stayscape.visitor.conversation-id'

export interface VisitorProfile {
  natural_language: string
  target_date: string | null
  weather: string
  target_crowd: string
  adult_count: number
  child_count: number
  child_ages: number[]
  budget: string | number
  interests: string[]
  negative_interests: string[]
  activity_level: string
  requested_places: string[]
  dietary_restrictions: string[]
  allergy_information: string
  arrival_time: string | null
  preferred_experience_time: string | null
  other_requirements: string
}

export function saveVisitorProfile(profile: VisitorProfile) {
  try { sessionStorage.setItem(VISITOR_PROFILE_KEY, JSON.stringify(profile)) } catch { /* private browsing */ }
}

export function loadVisitorProfile(): VisitorProfile | null {
  try {
    const raw = sessionStorage.getItem(VISITOR_PROFILE_KEY)
    return raw ? JSON.parse(raw) as VisitorProfile : null
  } catch { return null }
}

/** Keep a browser visitor's multi-turn Concierge history isolated from others. */
export function visitorConversationId(): string {
  try {
    const existing = sessionStorage.getItem(VISITOR_CONVERSATION_KEY)
    if (existing) return existing
    const generated = typeof crypto?.randomUUID === 'function'
      ? crypto.randomUUID()
      : `visitor-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    sessionStorage.setItem(VISITOR_CONVERSATION_KEY, generated)
    return generated
  } catch {
    return 'visitor-ephemeral'
  }
}
