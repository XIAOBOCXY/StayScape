import type { TravelProduct } from '../types'

export interface ProductMediaAsset {
  id: string
  url: string
  alt: string
  source: string
  source_url: string
  kind: 'scene' | 'room' | 'culture' | 'tea' | 'city' | 'family' | 'food'
}

// 固定的公开演示素材：这是杭州主题的氛围参考图，不代表酒店或合作商户真实供图。
// 页面只消费 mediaForProduct 的结果，避免把几十个 URL 散落在组件中。
const MEDIA_LIBRARY: Record<string, ProductMediaAsset> = {
  hangzhou: { id: 'hangzhou-water-town', url: 'https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1800&q=85', alt: '江南水乡与山水的旅行氛围图', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hangzhou-water-town', kind: 'scene' },
  rain: { id: 'hangzhou-rain-window', url: 'https://images.unsplash.com/photo-1515694346937-94d85e41e6f0?auto=format&fit=crop&w=1500&q=85', alt: '雨天窗边的安静旅行场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/rainy-window', kind: 'scene' },
  hotel: { id: 'boutique-hotel-room', url: 'https://images.unsplash.com/photo-1564501049412-61c2a3083791?auto=format&fit=crop&w=1400&q=85', alt: '暖色精品酒店客房与床铺', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/boutique-hotel-room', kind: 'room' },
  hotelWindow: { id: 'hotel-window-room', url: 'https://images.unsplash.com/photo-1590490360182-c33d57733427?auto=format&fit=crop&w=1400&q=85', alt: '带窗景与自然光的精品客房', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hotel-window-room', kind: 'room' },
  breakfast: { id: 'hangzhou-breakfast-table', url: 'https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?auto=format&fit=crop&w=1400&q=85', alt: '旅途中一桌精致早餐', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hotel-breakfast', kind: 'food' },
  craft: { id: 'hands-on-craft', url: 'https://images.unsplash.com/photo-1452860606245-08befc0ff44b?auto=format&fit=crop&w=1400&q=85', alt: '双手在木桌上进行手作体验', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/handmade-craft-workshop', kind: 'culture' },
  craftTable: { id: 'craft-table-detail', url: 'https://images.unsplash.com/photo-1528698827591-e19ccd7bc23d?auto=format&fit=crop&w=1400&q=85', alt: '手作材料、工具与桌面细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/craft-table', kind: 'culture' },
  craftHands: { id: 'craft-hands-detail', url: 'https://images.unsplash.com/photo-1494438639946-1ebd1d20bf85?auto=format&fit=crop&w=1400&q=85', alt: '旅行者共同完成手作的双手特写', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hands-craft', kind: 'culture' },
  tea: { id: 'tea-culture', url: 'https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=1400&q=85', alt: '茶杯与茶叶组成的茶文化场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/chinese-tea-ceremony', kind: 'tea' },
  teaSet: { id: 'tea-set-table', url: 'https://images.unsplash.com/photo-1564890369478-c89ca6d9cde9?auto=format&fit=crop&w=1400&q=85', alt: '茶器与茶席的近景细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/tea-set', kind: 'tea' },
  teaGarden: { id: 'tea-garden', url: 'https://images.unsplash.com/photo-1594631252845-29fc4cc8cde9?auto=format&fit=crop&w=1400&q=85', alt: '江南茶园与绿色山坡', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/tea-garden', kind: 'tea' },
  city: { id: 'hangzhou-city-walk', url: 'https://images.unsplash.com/photo-1480714378408-67cf0d13bc1b?auto=format&fit=crop&w=1400&q=85', alt: '城市街区与夜间漫游氛围图', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hangzhou-city-night', kind: 'city' },
  canal: { id: 'canal-night-lights', url: 'https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=1400&q=85', alt: '运河夜色与城市灯光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/canal-night', kind: 'city' },
  lake: { id: 'lake-walk', url: 'https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=1400&q=85', alt: '湖边散步与江南风景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/lake-walk', kind: 'scene' },
  family: { id: 'family-travel', url: 'https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=1400&q=85', alt: '家庭旅行中的亲密陪伴场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-travel', kind: 'family' },
  familyRoom: { id: 'family-hotel-room', url: 'https://images.unsplash.com/photo-1595576508898-0ad5c879a061?auto=format&fit=crop&w=1400&q=85', alt: '适合家庭入住的明亮客房', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-hotel-room', kind: 'family' },
  familyTable: { id: 'family-table', url: 'https://images.unsplash.com/photo-1472162072942-cd5147eb3902?auto=format&fit=crop&w=1400&q=85', alt: '家人围坐分享旅行时光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-dinner-travel', kind: 'family' }
}

function includesAny(text: string, words: string[]) { return words.some((word) => text.includes(word)) }

function rotate(items: ProductMediaAsset[], seed: number) {
  if (!items.length) return []
  const offset = Math.abs(seed) % items.length
  return [...items.slice(offset), ...items.slice(0, offset)]
}

export function mediaForProduct(product?: Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> | null): ProductMediaAsset[] {
  if (!product) return [MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.rain, MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.tea]
  const text = [product.product_name, product.theme, product.target_crowd, product.weather, ...product.resources.map((item) => `${item.resource_name} ${item.description || ''}`)].join(' ').toLowerCase()
  const culture = includesAny(text, ['非遗', '手作', '文化', '工坊', 'craft'])
  const tea = includesAny(text, ['茶', '点茶', '茶器', '茶园', 'tea'])
  const family = includesAny(text, ['亲子', '家庭', 'family']) || product.target_crowd === 'FAMILY'
  const couple = includesAny(text, ['情侣', '夫妻', '旅拍', 'couple']) || product.target_crowd === 'COUPLE'
  const city = includesAny(text, ['西湖', '运河', '城市', '漫游', '摄影', 'city']) || couple
  const seed = Number(product.id || 0)
  const themeSet = tea ? [MEDIA_LIBRARY.tea, MEDIA_LIBRARY.teaSet, MEDIA_LIBRARY.teaGarden] : culture ? [MEDIA_LIBRARY.craft, MEDIA_LIBRARY.craftTable, MEDIA_LIBRARY.craftHands] : city ? [MEDIA_LIBRARY.city, MEDIA_LIBRARY.canal, MEDIA_LIBRARY.lake] : family ? [MEDIA_LIBRARY.family, MEDIA_LIBRARY.familyRoom, MEDIA_LIBRARY.familyTable] : [MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.hotelWindow, MEDIA_LIBRARY.hangzhou]
  const supportSet = family ? [MEDIA_LIBRARY.familyRoom, MEDIA_LIBRARY.breakfast, MEDIA_LIBRARY.hotel] : tea ? [MEDIA_LIBRARY.tea, MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.hotel] : culture ? [MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.breakfast, MEDIA_LIBRARY.hangzhou] : [MEDIA_LIBRARY.hotelWindow, MEDIA_LIBRARY.breakfast, MEDIA_LIBRARY.hangzhou]
  const contextSet = product.weather === 'RAIN' ? [MEDIA_LIBRARY.rain, MEDIA_LIBRARY.hangzhou] : city ? [MEDIA_LIBRARY.canal, MEDIA_LIBRARY.lake] : [MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.city]
  return [...rotate(themeSet, seed), ...rotate(supportSet, seed + 1), ...rotate(contextSet, seed + 2)].filter((item, index, list) => list.findIndex((candidate) => candidate.id === item.id) === index).slice(0, 8)
}

export function heroMedia(product?: Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> | null) { return mediaForProduct(product)[0] }
export function experienceLabel(resourceType: string) { return ({ ROOM: 'STAY', HOTEL_SERVICE: 'TASTE', PARTNER_RESOURCE: 'EXPERIENCE' } as Record<string, string>)[resourceType] || 'MOMENT' }
export function experienceLabelZh(resourceType: string) { return ({ ROOM: '住宿', HOTEL_SERVICE: '酒店服务', PARTNER_RESOURCE: '文化体验' } as Record<string, string>)[resourceType] || '旅居内容' }
export function weatherLabel(weather: string) { return ({ RAIN: 'RAIN FRIENDLY', SUNNY: 'SUNNY DAY', CLOUDY: 'SOFT CLOUDS' } as Record<string, string>)[weather] || weather }

export { MEDIA_LIBRARY }
