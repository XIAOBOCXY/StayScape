/** Chinese labels for every enum-ish value the API returns.
 *
 * Operators and visitors only ever see Chinese: resource types, knowledge
 * categories, crowds and weather tags are translated in one place instead of
 * leaking `PARTNER_RESOURCE` / `CULTURE` / `FAMILY` into the UI.
 */

export const RESOURCE_TYPE_LABELS: Record<string, string> = {
  ROOM: '酒店房间',
  HOTEL_SERVICE: '酒店服务',
  PARTNER_RESOURCE: '在地体验',
}

export const KNOWLEDGE_CATEGORY_LABELS: Record<string, string> = {
  MUSEUM: '博物馆',
  ART_MUSEUM: '美术馆',
  SCIENCE_MUSEUM: '科技馆',
  LIBRARY: '图书馆',
  CITY_WALK: '城市漫步',
  NATURE: '自然湿地',
  FAMILY_PARK: '亲子公园',
  THEME_PARK: '主题乐园',
  PERFORMANCE: '演出剧场',
  NIGHTLIFE: '夜游',
  FOOD: '美食街区',
  WORKSHOP: '手作工坊',
  SPORT: '运动体验',
  PARK: '遗址公园',
}

export const CROWD_LABELS: Record<string, string> = {
  FAMILY: '亲子家庭',
  COUPLE: '两人同行',
  FRIENDS: '朋友出行',
  SOLO: '独自旅行',
  LOCAL_WEEKEND: '本地周末',
  ALL: '不限客群',
}

export const WEATHER_LABELS: Record<string, string> = {
  RAIN: '雨天',
  CLOUDY: '多云',
  SUNNY: '晴天',
}

export const INDOOR_LABELS: Record<string, string> = {
  INDOOR: '室内',
  OUTDOOR: '户外',
  MIXED: '室内外皆可',
}

export const ACTIVITY_LABELS: Record<string, string> = {
  LOW: '轻松',
  MEDIUM: '适中',
  HIGH: '高强度',
}

function split(value: unknown): string[] {
  return String(value ?? '')
    .replace(/，/g, ',')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

export function labelResourceType(value: unknown): string {
  const text = String(value ?? '').trim()
  return RESOURCE_TYPE_LABELS[text] || '行程内容'
}

export function labelCategory(value: unknown): string {
  const text = String(value ?? '').trim()
  return KNOWLEDGE_CATEGORY_LABELS[text] || text || '未分类'
}

export function labelCrowds(value: unknown, fallback = '不限客群'): string {
  const parts = split(value).map((part) => CROWD_LABELS[part.toUpperCase()] || part)
  return parts.join('、') || fallback
}

export function labelWeather(value: unknown, fallback = '不限天气'): string {
  const parts = split(value).map((part) => WEATHER_LABELS[part.toUpperCase()] || part)
  return parts.join('、') || fallback
}

export function labelIndoor(value: unknown): string {
  return INDOOR_LABELS[String(value ?? '').trim().toUpperCase()] || '室内外皆可'
}

export function labelActivity(value: unknown): string {
  return ACTIVITY_LABELS[String(value ?? '').trim().toUpperCase()] || '适中'
}
