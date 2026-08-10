export const VISITOR_PROFILE_KEY = 'stayscape.visitor.confirmed-profile'

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
