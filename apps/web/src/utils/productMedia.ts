import type { TravelProduct } from '../types'

export interface ProductMediaAsset {
  id: string
  url: string
  alt: string
  source: string
  source_url: string
  kind: 'scene' | 'room' | 'culture' | 'tea' | 'city' | 'family'
}

// Stable demo media only. These are atmosphere references, not hotel or merchant supplied photos.
const MEDIA_LIBRARY: Record<string, ProductMediaAsset> = {
  hangzhou: {
    id: 'hangzhou-water-town',
    url: 'https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1800&q=85',
    alt: '江南水乡与山水的旅行氛围图',
    source: 'Unsplash',
    source_url: 'https://unsplash.com/',
    kind: 'scene'
  },
  hotel: {
    id: 'boutique-hotel-room',
    url: 'https://images.unsplash.com/photo-1564501049412-61c2a3083791?auto=format&fit=crop&w=1400&q=85',
    alt: '暖色精品酒店客房与床铺',
    source: 'Unsplash',
    source_url: 'https://unsplash.com/',
    kind: 'room'
  },
  craft: {
    id: 'hands-on-craft',
    url: 'https://images.unsplash.com/photo-1452860606245-08befc0ff44b?auto=format&fit=crop&w=1400&q=85',
    alt: '双手在木桌上进行手作体验',
    source: 'Unsplash',
    source_url: 'https://unsplash.com/',
    kind: 'culture'
  },
  tea: {
    id: 'tea-culture',
    url: 'https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=1400&q=85',
    alt: '茶杯与茶叶组成的茶文化场景',
    source: 'Unsplash',
    source_url: 'https://unsplash.com/',
    kind: 'tea'
  },
  city: {
    id: 'hangzhou-city-walk',
    url: 'https://images.unsplash.com/photo-1480714378408-67cf0d13bc1b?auto=format&fit=crop&w=1400&q=85',
    alt: '城市街区与夜间漫游氛围图',
    source: 'Unsplash',
    source_url: 'https://unsplash.com/',
    kind: 'city'
  },
  family: {
    id: 'family-travel',
    url: 'https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=1400&q=85',
    alt: '家庭旅行中的亲密陪伴场景',
    source: 'Unsplash',
    source_url: 'https://unsplash.com/',
    kind: 'family'
  }
}

function includesAny(text: string, words: string[]) {
  return words.some((word) => text.includes(word))
}

export function mediaForProduct(product?: Pick<TravelProduct, 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> | null): ProductMediaAsset[] {
  if (!product) return [MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.city]
  const text = [product.product_name, product.theme, product.target_crowd, product.weather, ...product.resources.map((item) => item.resource_name)].join(' ').toLowerCase()
  const culture = includesAny(text, ['非遗', '手作', '文化', '体验', 'craft'])
  const tea = includesAny(text, ['茶', '点茶', '茶器', 'tea'])
  const family = includesAny(text, ['亲子', '家庭', 'family']) || product.target_crowd === 'FAMILY'
  const couple = includesAny(text, ['情侣', '夫妻', 'couple']) || product.target_crowd === 'COUPLE'
  const city = includesAny(text, ['西湖', '运河', '旅拍', '城市', '漫游', '摄影', 'city']) || couple

  const selected = [
    family ? MEDIA_LIBRARY.family : couple ? MEDIA_LIBRARY.city : MEDIA_LIBRARY.hangzhou,
    tea ? MEDIA_LIBRARY.tea : culture ? MEDIA_LIBRARY.craft : MEDIA_LIBRARY.hotel,
    city ? MEDIA_LIBRARY.city : MEDIA_LIBRARY.hangzhou,
    MEDIA_LIBRARY.hotel
  ]
  return selected.filter((item, index, list) => list.findIndex((candidate) => candidate.id === item.id) === index)
}

export function heroMedia(product?: Pick<TravelProduct, 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> | null) {
  return mediaForProduct(product)[0]
}

export function experienceLabel(resourceType: string) {
  return ({ ROOM: 'STAY', HOTEL_SERVICE: 'TASTE', PARTNER_RESOURCE: 'EXPERIENCE' } as Record<string, string>)[resourceType] || 'MOMENT'
}

export function experienceLabelZh(resourceType: string) {
  return ({ ROOM: '住宿', HOTEL_SERVICE: '酒店服务', PARTNER_RESOURCE: '文化体验' } as Record<string, string>)[resourceType] || '旅居内容'
}

export function weatherLabel(weather: string) {
  return ({ RAIN: 'RAIN FRIENDLY', SUNNY: 'SUNNY DAY', CLOUDY: 'SOFT CLOUDS' } as Record<string, string>)[weather] || weather
}

export { MEDIA_LIBRARY }
