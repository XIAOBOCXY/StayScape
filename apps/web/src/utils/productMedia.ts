import type { TravelProduct } from '../types'

export interface ProductMediaAsset {
  id: string
  url: string
  alt: string
  source: string
  source_url: string
  kind: 'scene' | 'room' | 'culture' | 'tea' | 'city' | 'family' | 'food' | 'themePark' | 'entertainment' | 'sport' | 'nightlife' | 'nature' | 'photo' | 'performance' | 'couple' | 'kids'
  source_type?: 'UNSPLASH_DEMO' | 'PEXELS_DEMO' | 'WIKIMEDIA_COMMONS' | 'OFFICIAL_REFERENCE' | 'TRAVEL_REFERENCE' | 'EDITORIAL_REFERENCE' | 'HOTEL_UPLOAD' | 'PARTNER_UPLOAD' | 'PROJECT_ASSET'
  attribution?: string
  usage_note?: string
  license?: string
  tags?: string[]
  location?: string
  category?: string
  orientation?: 'portrait' | 'landscape' | 'square'
}

/** Route a curated public image through our own cache endpoint.
 *
 * The first view copies the file to server storage, later views are served
 * from the local cache with a week-long browser cache, which keeps the
 * operator console and the storefront from waiting on third-party CDNs.
 */
function cachedMediaUrl(url: string): string {
  if (!/^https:\/\/(images\.unsplash\.com|images\.pexels\.com|commons\.wikimedia\.org|upload\.wikimedia\.org)\//.test(url)) return url
  return `/api/v1/visitor/media/proxy?url=${encodeURIComponent(url)}`
}

// 固定的公开演示素材：这是杭州主题的氛围参考图，不代表酒店或合作商户真实供图。
// 页面只消费 mediaForProduct 的结果，避免把几十个 URL 散落在组件中。
const MEDIA_LIBRARY_RAW: Record<string, ProductMediaAsset> = {
  hangzhou: { id: 'hangzhou-water-town', url: '/generated-media/resource-media/curated-hangzhou.jpg', alt: '江南水乡与山水的旅行氛围图', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hangzhou-water-town', kind: 'scene' },
  rain: { id: 'hangzhou-rain-window', url: '/generated-media/resource-media/curated-rain.jpg', alt: '雨天窗边的安静旅行场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/rainy-window', kind: 'scene' },
  hotel: { id: 'boutique-hotel-room', url: '/generated-media/resource-media/curated-hotel.jpg', alt: '暖色精品酒店客房与床铺', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/boutique-hotel-room', kind: 'room' },
  hotelWindow: { id: 'hotel-window-room', url: '/generated-media/resource-media/curated-hotelWindow.jpg', alt: '带窗景与自然光的精品客房', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hotel-window-room', kind: 'room' },
  breakfast: { id: 'hangzhou-breakfast-table', url: '/generated-media/resource-media/curated-breakfast.jpg', alt: '旅途中一桌精致早餐', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hotel-breakfast', kind: 'food' },
  craft: { id: 'hands-on-craft', url: '/generated-media/resource-media/curated-craft.jpg', alt: '双手在木桌上进行手作体验', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/handmade-craft-workshop', kind: 'culture' },
  craftTable: { id: 'craft-table-detail', url: '/generated-media/resource-media/curated-craftTable.jpg', alt: '手作材料、工具与桌面细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/craft-table', kind: 'culture' },
  craftHands: { id: 'craft-hands-detail', url: '/generated-media/resource-media/curated-craftHands.jpg', alt: '旅行者共同完成手作的双手特写', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hands-craft', kind: 'culture' },
  tea: { id: 'tea-culture', url: '/generated-media/resource-media/curated-tea.jpg', alt: '茶杯与茶叶组成的茶文化场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/chinese-tea-ceremony', kind: 'tea' },
  teaSet: { id: 'tea-set-table', url: '/generated-media/resource-media/curated-teaSet.jpg', alt: '茶器与茶席的近景细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/tea-set', kind: 'tea' },
  teaGarden: { id: 'tea-garden', url: '/generated-media/resource-media/curated-teaGarden.jpg', alt: '江南茶园与绿色山坡', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/tea-garden', kind: 'tea' },
  city: { id: 'hangzhou-city-walk', url: '/generated-media/resource-media/curated-city.jpg', alt: '城市街区与夜间漫游氛围图', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hangzhou-city-night', kind: 'city' },
  canal: { id: 'canal-night-lights', url: '/generated-media/resource-media/curated-canal.jpg', alt: '运河夜色与城市灯光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/canal-night', kind: 'city' },
  lake: { id: 'lake-walk', url: '/generated-media/resource-media/curated-lake.jpg', alt: '湖边散步与江南风景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/lake-walk', kind: 'scene' },
  family: { id: 'family-travel', url: '/generated-media/resource-media/curated-family.jpg', alt: '家庭旅行中的亲密陪伴场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-travel', kind: 'family' },
  familyRoom: { id: 'family-hotel-room', url: '/generated-media/resource-media/curated-familyRoom.jpg', alt: '适合家庭入住的明亮客房', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-hotel-room', kind: 'family' },
  familyTable: { id: 'family-table', url: '/generated-media/resource-media/curated-familyTable.jpg', alt: '家人围坐分享旅行时光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-dinner-travel', kind: 'family' },
  themePark: { id: 'hangzhou-theme-park', url: '/generated-media/resource-media/curated-themePark.jpg', alt: '夜色中的游乐园摩天轮与灯光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/theme-park', kind: 'themePark' },
  themeParkDay: { id: 'theme-park-day', url: '/generated-media/resource-media/curated-themeParkDay.jpg', alt: '白天游乐园的家庭旅行场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/amusement-park', kind: 'themePark' },
  entertainment: { id: 'city-entertainment', url: '/generated-media/resource-media/curated-entertainment.jpg', alt: '城市音乐现场与年轻人娱乐氛围', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/live-music', kind: 'entertainment' },
  sport: { id: 'indoor-sport', url: '/generated-media/resource-media/curated-sport.jpg', alt: '室内运动馆的运动体验场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/indoor-sports', kind: 'sport' },
  sportDetail: { id: 'sport-detail', url: '/generated-media/resource-media/curated-sportDetail.jpg', alt: '朋友一起完成运动挑战的细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/sports-friends', kind: 'sport' },
  nightlife: { id: 'hangzhou-nightlife', url: '/generated-media/resource-media/curated-nightlife.jpg', alt: '城市夜色与灯光组成的夜游场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/city-night', kind: 'nightlife' },
  food: { id: 'jiangnan-food', url: '/generated-media/resource-media/curated-food.jpg', alt: '餐桌与江南美食体验氛围', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/restaurant-table', kind: 'food' },
  nature: { id: 'xixi-nature', url: '/generated-media/resource-media/curated-nature.jpg', alt: '湿地与树木组成的自然探索场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/wetland-nature', kind: 'nature' },
  natureDetail: { id: 'nature-detail', url: '/generated-media/resource-media/curated-natureDetail.jpg', alt: '亲子自然观察与植物细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/nature-walk', kind: 'nature' },
  photo: { id: 'city-photo-walk', url: '/generated-media/resource-media/curated-photo.jpg', alt: '城市旅拍中的相机与街景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/city-photography', kind: 'photo' },
  performance: { id: 'city-performance', url: '/generated-media/resource-media/curated-performance.jpg', alt: '城市演出现场的舞台与观众', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/theater-performance', kind: 'performance' },
  kids: { id: 'kids-indoor-play', url: '/generated-media/resource-media/curated-kids.jpg', alt: '儿童在室内游乐空间探索', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/kids-indoor-play', kind: 'kids' },
  couple: { id: 'couple-hangzhou-trip', url: '/generated-media/resource-media/curated-couple.jpg', alt: '情侣旅行中的城市漫游时刻', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/couple-travel', kind: 'couple' },
  themeParkLights: { id: 'theme-park-lights', url: '/generated-media/resource-media/curated-themeParkLights.jpg', alt: '夜间游乐园灯光与摩天轮', source: 'Pexels', source_url: 'https://www.pexels.com/photo/ferris-wheel-under-the-stars-1779487/', kind: 'themePark' },
  kidsDiscovery: { id: 'kids-discovery', url: '/generated-media/resource-media/curated-kidsDiscovery.jpg', alt: '儿童在探索空间中动手体验', source: 'Pexels', source_url: 'https://www.pexels.com/photo/children-playing-inside-a-room-3662667/', kind: 'kids' },
  climbing: { id: 'climbing-wall', url: '/generated-media/resource-media/curated-climbing.jpg', alt: '室内攀岩运动体验', source: 'Pexels', source_url: 'https://www.pexels.com/search/indoor%20climbing/', kind: 'sport' },
  warmFood: { id: 'warm-food-editorial', url: '/generated-media/resource-media/curated-warmFood.jpg', alt: '暖色餐桌与城市美食体验', source: 'Pexels', source_url: 'https://www.pexels.com/photo/restaurant-interior-262978/', kind: 'food' },
  westLake: { id: 'west-lake-hangzhou-2025', url: '/generated-media/resource-media/curated-westLake.jpg', alt: '杭州西湖的湖面与群山', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:West_Lake,_Hangzhou_2025.jpg', kind: 'city', attribution: 'Wikimedia Commons · CC BY 4.0', license: 'CC BY 4.0', location: '杭州 · 西湖' },
  westLakeDawn: { id: 'west-lake-dawn', url: '/generated-media/resource-media/curated-westLakeDawn.jpg', alt: '清晨的杭州西湖', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Hangzhou%60s_West_Lake_scenery_at_dawn.JPG', kind: 'city', attribution: 'Wikimedia Commons · public domain', license: 'Public domain', location: '杭州 · 西湖' },
  gongchen: { id: 'gongchen-bridge', url: '/generated-media/resource-media/curated-gongchen.jpg', alt: '杭州拱宸桥与运河景观', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:20231122_Gongchen_Bridge_02.jpg', kind: 'city', attribution: 'Wikimedia Commons · CC BY-SA 4.0', license: 'CC BY-SA 4.0', location: '杭州 · 拱宸桥' },
  xixi: { id: 'xixi-wetland', url: '/generated-media/resource-media/curated-xixi.jpg', alt: '杭州西溪湿地景观', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Xixi_Wetland_Park,_Hangzhou,%E6%9D%AD%E5%B7%9E%E8%A5%BF%E6%BA%AA%E6%B9%BF%E5%9C%B0_-_panoramio.jpg', kind: 'nature', attribution: 'Wikimedia Commons · CC BY-SA 3.0', license: 'CC BY-SA 3.0', location: '杭州 · 西溪湿地' },
  longjing: { id: 'longjing-tea-garden', url: '/generated-media/resource-media/curated-longjing.jpg', alt: '杭州茶园与山景', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Tea_Garden_Hangzhou.jpg', kind: 'tea', attribution: 'Wikimedia Commons · CC BY 4.0', license: 'CC BY 4.0', location: '杭州 · 龙井茶园' },
  lingyin: { id: 'lingyin-temple', url: '/generated-media/resource-media/curated-lingyin.jpg', alt: '杭州灵隐寺建筑景观', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Lingyin_Buddhist_Temple,_Hangzhou_(3020083374).jpg', kind: 'culture', attribution: 'Wikimedia Commons · CC BY 2.0', license: 'CC BY 2.0', location: '杭州 · 灵隐' },
  silkMuseum: { id: 'china-national-silk-museum-reference', url: '/generated-media/resource-media/curated-silkMuseum.jpg', alt: '杭州博物馆建筑参考图', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Liangzhu_Museum,_2019-07-07_09.jpg', kind: 'culture', attribution: 'Wikimedia Commons · CC BY-SA 4.0', license: 'CC BY-SA 4.0', location: '杭州 · 博物馆' },
  liangzhuCctv: { id: 'liangzhu-museum-public', url: '/generated-media/resource-media/curated-liangzhuCctv.jpg', alt: '杭州良渚博物院建筑参考图', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Liangzhu_Museum,_2019-07-07_09.jpg', kind: 'culture', attribution: 'Wikimedia Commons · CC BY-SA 4.0', license: 'CC BY-SA 4.0', location: '杭州 · 良渚' },
  songcheng: { id: 'theme-park-public-reference', url: '/generated-media/resource-media/curated-songcheng.jpg', alt: '主题乐园夜间氛围参考图', source: 'Pexels', source_url: 'https://www.pexels.com/photo/ferris-wheel-under-the-stars-1779487/', kind: 'themePark', attribution: 'Pexels · 来源页', license: 'Pexels License', location: '杭州主题乐园参考' },
  animationMuseum: { id: 'animation-museum-reference', url: '/generated-media/resource-media/curated-animationMuseum.jpg', alt: '城市展演空间参考图', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/city-entertainment', kind: 'entertainment', attribution: 'Unsplash · 来源页', license: 'Unsplash License', location: '杭州展演空间参考' },
  liangzhuMuseum: { id: 'liangzhu-museum', url: '/generated-media/resource-media/curated-liangzhuMuseum.jpg', alt: '杭州良渚博物院建筑', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Liangzhu_Museum,_2019-07-07_09.jpg', kind: 'culture', attribution: 'Wikimedia Commons · CC BY-SA 4.0', license: 'CC BY-SA 4.0', location: '杭州 · 良渚' }
}

// Curated demo catalog metadata is deliberately explicit.  These are public
// reference images, not hotel/partner supplied photos; production can replace
// individual records with HOTEL_UPLOAD/PARTNER_UPLOAD assets after permission.
const MEDIA_LIBRARY: Record<string, ProductMediaAsset> = Object.fromEntries(Object.entries(MEDIA_LIBRARY_RAW).map(([key, item]) => {
  const sourceType = item.source === 'Wikimedia Commons' ? 'WIKIMEDIA_COMMONS'
    : item.source === 'Pexels' ? 'PEXELS_DEMO'
    : item.source === 'Unsplash' ? 'UNSPLASH_DEMO'
    : item.source === '携程旅行' ? 'TRAVEL_REFERENCE'
    : item.source === '央视网' || item.source === 'Shanghai Daily City News' ? 'EDITORIAL_REFERENCE'
    : 'OFFICIAL_REFERENCE'
  return [key, {
    ...item,
    url: cachedMediaUrl(item.url),
    source_type: sourceType,
    attribution: item.attribution || `${item.source} curated demo image`,
    usage_note: item.usage_note || '公开参考图，不代表酒店或合作商户实拍；正式商用前请按来源页面核验许可。',
    license: item.license || 'Demo reference · verify source license before production',
    tags: [item.kind, key, 'Hangzhou travel', 'StayScape demo'],
    location: item.location || '杭州主题 / 城市文旅氛围参考',
    category: item.kind,
    orientation: key.toLowerCase().includes('poster') ? 'portrait' : 'landscape'
  }] as const
})) as Record<string, ProductMediaAsset>

function includesAny(text: string, words: string[]) { return words.some((word) => text.includes(word)) }

function rotate(items: ProductMediaAsset[], seed: number) {
  if (!items.length) return []
  const offset = Math.abs(seed) % items.length
  return [...items.slice(offset), ...items.slice(0, offset)]
}

function legacyMediaForProduct(product?: Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> | null): ProductMediaAsset[] {
  if (!product) return [MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.rain, MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.tea]
  const text = [product.product_name, product.theme, product.target_crowd, ...product.resources.map((item) => `${item.resource_name} ${item.description || ''}`)].join(' ').toLowerCase()
  const themePark = includesAny(text, ['乐园', '游乐', '主题公园', 'theme park', 'themepark'])
  const kids = includesAny(text, ['儿童', '孩子', '亲子乐园', 'kids'])
  const sport = includesAny(text, ['运动', '攀岩', '卡丁车', '射箭', 'sport'])
  const nightlife = includesAny(text, ['夜游', '夜景', '夜生活', '音乐现场', 'nightlife'])
  const food = includesAny(text, ['美食', '杭帮菜', '甜品', '咖啡', '烘焙', 'food'])
  const nature = includesAny(text, ['自然', '湿地', '动物', '植物', 'nature'])
  const photo = includesAny(text, ['旅拍', '摄影', '拍照', 'photo'])
  const performance = includesAny(text, ['演出', '儿童剧', '剧场', 'performance'])
  const entertainment = includesAny(text, ['娱乐', '陶艺', '桌游', '电玩', 'entertainment'])
  const culture = includesAny(text, ['非遗', '手作', '文化', '工坊', 'craft'])
  const tea = includesAny(text, ['茶', '点茶', '茶器', '茶园', 'tea'])
  const family = includesAny(text, ['亲子', '家庭', 'family']) || product.target_crowd === 'FAMILY'
  const couple = includesAny(text, ['情侣', '夫妻', '旅拍', 'couple']) || product.target_crowd === 'COUPLE'
  const city = includesAny(text, ['西湖', '运河', '城市', '漫游', '摄影', 'city']) || couple
  const seed = Number(product.id || 0)
  const themeSet = themePark ? [MEDIA_LIBRARY.songcheng, MEDIA_LIBRARY.themeParkLights, MEDIA_LIBRARY.themeParkDay, MEDIA_LIBRARY.family] : kids ? [MEDIA_LIBRARY.kids, MEDIA_LIBRARY.family, MEDIA_LIBRARY.familyRoom] : sport ? [MEDIA_LIBRARY.sport, MEDIA_LIBRARY.sportDetail, MEDIA_LIBRARY.hotel] : nightlife ? [MEDIA_LIBRARY.nightlife, MEDIA_LIBRARY.canal, MEDIA_LIBRARY.city] : food ? [MEDIA_LIBRARY.food, MEDIA_LIBRARY.breakfast, MEDIA_LIBRARY.hotel] : nature ? [MEDIA_LIBRARY.nature, MEDIA_LIBRARY.natureDetail, MEDIA_LIBRARY.family] : photo ? [MEDIA_LIBRARY.photo, MEDIA_LIBRARY.city, MEDIA_LIBRARY.couple] : performance ? [MEDIA_LIBRARY.performance, MEDIA_LIBRARY.entertainment, MEDIA_LIBRARY.city] : entertainment ? [MEDIA_LIBRARY.entertainment, MEDIA_LIBRARY.nightlife, MEDIA_LIBRARY.hotel] : tea ? [MEDIA_LIBRARY.tea, MEDIA_LIBRARY.teaSet, MEDIA_LIBRARY.teaGarden] : culture ? [MEDIA_LIBRARY.craft, MEDIA_LIBRARY.craftTable, MEDIA_LIBRARY.craftHands] : city ? [MEDIA_LIBRARY.city, MEDIA_LIBRARY.canal, MEDIA_LIBRARY.lake] : family ? [MEDIA_LIBRARY.family, MEDIA_LIBRARY.familyRoom, MEDIA_LIBRARY.familyTable] : [MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.hotelWindow, MEDIA_LIBRARY.hangzhou]
  const supportSet = family ? [MEDIA_LIBRARY.familyRoom, MEDIA_LIBRARY.breakfast, MEDIA_LIBRARY.hotel] : sport ? [MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.sportDetail, MEDIA_LIBRARY.breakfast] : food ? [MEDIA_LIBRARY.breakfast, MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.city] : tea ? [MEDIA_LIBRARY.tea, MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.hotel] : culture ? [MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.breakfast, MEDIA_LIBRARY.hangzhou] : [MEDIA_LIBRARY.hotelWindow, MEDIA_LIBRARY.breakfast, MEDIA_LIBRARY.hangzhou]
  const contextSet = nightlife ? [MEDIA_LIBRARY.gongchen, MEDIA_LIBRARY.nightlife] : nature ? [MEDIA_LIBRARY.xixi, MEDIA_LIBRARY.nature] : tea ? [MEDIA_LIBRARY.longjing, MEDIA_LIBRARY.hangzhou] : city ? [MEDIA_LIBRARY.westLake, MEDIA_LIBRARY.gongchen] : product.weather === 'RAIN' ? [MEDIA_LIBRARY.rain, MEDIA_LIBRARY.hotel] : [MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.city]
  return [...rotate(themeSet, seed), ...rotate(supportSet, seed + 1), ...rotate(contextSet, seed + 2)].filter((item, index, list) => list.findIndex((candidate) => candidate.id === item.id) === index).slice(0, 8)
}

/** Stable multi-dimensional catalog matching: product id varies the selected
 * hero, while semantic text, crowd, weather and resource metadata determine
 * which visual family is allowed. */
export function mediaForProduct(product?: Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> | null): ProductMediaAsset[] {
  if (!product) return [MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.rain, MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.tea]
  const resourceUploads = product.resources.map((resource) => uploadedMedia(resource)).filter((item): item is ProductMediaAsset => Boolean(item))
  const text = [product.product_name, product.theme, product.target_crowd, ...product.resources.map((item) => `${item.resource_name} ${item.description || ''} ${item.address || ''}`)].join(' ').toLowerCase()
  const tests: Array<[string[], string[]]> = [
    [['博物馆', '良渚', '看展', '美术馆', '科技馆', '展览', '丝绸'], ['silkMuseum', 'liangzhuCctv', 'liangzhuMuseum', 'hotel']],
    [['西湖', '湖滨', '湖畔'], ['westLake', 'westLakeDawn', 'hotel', 'breakfast']],
    [['运河', '拱宸'], ['gongchen', 'canal', 'city', 'photo']],
    [['西溪', '湿地'], ['xixi', 'nature', 'lake', 'family']],
    [['龙井', '茶园'], ['longjing', 'tea', 'teaSet', 'hotel']],
    [['灵隐'], ['lingyin', 'westLake', 'hotel', 'city']],
    [['乐园', '游乐', '主题公园', '宋城', 'theme'], ['songcheng', 'themeParkLights', 'themeParkDay']],
    [['儿童', '亲子', '孩子', 'kids'], ['kids', 'kidsDiscovery', 'family', 'familyRoom']],
    [['攀岩', '卡丁车', '运动', 'sport'], ['sport', 'sportDetail', 'climbing', 'entertainment']],
    [['夜游', '夜景', '音乐', 'night'], ['nightlife', 'canal', 'city', 'performance']],
    [['旅拍', '摄影', '拍照', 'photo'], ['photo', 'couple', 'city', 'lake']],
    [['美食', '杭帮菜', '甜品', '咖啡', '烘焙', 'food'], ['food', 'warmFood', 'breakfast', 'hotel']],
    [['自然', '湿地', '动物', '植物', 'nature'], ['nature', 'natureDetail', 'lake', 'family']],
    [['演出', '儿童剧', '剧场', 'performance'], ['songcheng', 'performance', 'entertainment', 'nightlife']],
    [['动漫', '动画', '二次元'], ['animationMuseum', 'entertainment', 'city', 'nightlife']],
    [['非遗', '手作', '文化', 'craft'], ['craft', 'craftTable', 'craftHands', 'hotel']],
    [['茶', '点茶', '茶园', 'tea'], ['tea', 'teaSet', 'teaGarden', 'hangzhou']],
  ]
  const matched = tests.find(([words]) => words.some((word) => text.includes(word)))
  const fallback = legacyMediaForProduct(product)
  const keys = matched?.[1] || (product.target_crowd === 'COUPLE' ? ['couple', 'photo', 'nightlife', 'lake'] : product.target_crowd === 'FRIENDS' ? ['entertainment', 'sport', 'nightlife', 'city'] : ['hotel', 'hotelWindow', 'hangzhou', 'family'])
  const seed = Math.abs(Number(product.id || 0) * 7)
  const catalogItems = keys.map((key) => MEDIA_LIBRARY[key]).filter(Boolean)
  const rotated = [...catalogItems.slice(seed % Math.max(catalogItems.length, 1)), ...catalogItems.slice(0, seed % Math.max(catalogItems.length, 1))]
  const merged = [...resourceUploads, ...rotated, ...fallback]
  return merged.filter((item, index, list) => list.findIndex((candidate) => candidate.id === item.id) === index).slice(0, 8)
}

export function heroMedia(product?: Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> | null) { return mediaForProduct(product)[0] }
export function experienceLabel(resourceType: string) { return ({ ROOM: '住宿', HOTEL_SERVICE: '酒店服务', PARTNER_RESOURCE: '在地体验' } as Record<string, string>)[resourceType] || '行程内容' }
export function experienceLabelZh(resourceType: string) { return ({ ROOM: '住宿', HOTEL_SERVICE: '贴心服务', PARTNER_RESOURCE: '在地体验' } as Record<string, string>)[resourceType] || '旅居内容' }
export function weatherLabel(weather: string) { return ({ RAIN: 'RAIN FRIENDLY', SUNNY: 'SUNNY DAY', CLOUDY: 'SOFT CLOUDS' } as Record<string, string>)[weather] || weather }


export interface ProductMoment {
  media: ProductMediaAsset
  resource_name: string
  resource_type: string
}

type ProductMediaInput = Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'>
type ProductResource = TravelProduct['resources'][number]

export function automaticNetworkMedia(query: string, kind: ProductMediaAsset['kind'] = 'scene'): ProductMediaAsset {
  const clean = query.trim().slice(0, 160) || '杭州旅行'
  return {
    id: `commons-auto-${clean}`,
    url: `/api/v1/visitor/media/cover?query=${encodeURIComponent(clean)}`,
    alt: `${clean}参考图片`,
    source: '百度/官网检索',
    source_url: '/api/v1/visitor/media/cover',
    source_type: 'OFFICIAL_REFERENCE',
    attribution: '按「地点 + 名称」检索公开图片并核对来源页；可在商户端替换为自有实拍图',
    usage_note: '自动检索的公开参考图；商户上传的实拍图会优先显示。',
    kind,
  }
}

function uploadedMedia(resource: ProductResource): ProductMediaAsset | null {
  if (!resource.image_url) return null
  return {
    id: `resource-upload-${resource.id}`,
    url: resource.image_url,
    alt: resource.resource_name,
    source: resource.image_source || '商户图片',
    source_url: resource.image_attribution || resource.image_url,
    source_type: 'HOTEL_UPLOAD',
    attribution: resource.image_attribution || resource.image_source || '商户提供',
    kind: resource.resource_type === 'ROOM' ? 'room' : resource.resource_type === 'HOTEL_SERVICE' ? 'food' : 'scene',
  }
}

function mediaCandidatesForResource(product: ProductMediaInput | null | undefined, resource: ProductResource | undefined, index = 0) {
  if (!resource) return mediaForProduct(product)
  const upload = uploadedMedia(resource)
  if (upload) return [upload]
  const text = [resource.resource_name, resource.description || '', resource.address || '', product?.product_name || '', product?.theme || ''].join(' ').toLowerCase()
  let keys: string[]
  if (resource.resource_type === 'ROOM') {
    keys = product?.target_crowd === 'FAMILY' ? ['familyRoom', 'hotelWindow', 'hotel'] : ['hotelWindow', 'hotel', 'familyRoom']
  } else if (resource.resource_type === 'HOTEL_SERVICE') {
    keys = includesAny(text, ['早餐', '餐', '美食', '咖啡', '下午茶', 'food']) ? ['breakfast', 'warmFood', 'food'] : includesAny(text, ['茶', 'tea']) ? ['teaSet', 'tea', 'hotelWindow'] : ['hotelWindow', 'breakfast', 'hotel']
  } else if (includesAny(text, ['博物馆', '良渚', '看展', '美术馆', '科技馆', '展览', '丝绸'])) {
    keys = ['silkMuseum', 'liangzhuCctv', 'liangzhuMuseum']
  } else if (includesAny(text, ['西湖', '湖滨', '湖畔'])) {
    keys = ['westLake', 'westLakeDawn', 'lake']
  } else if (includesAny(text, ['运河', '拱宸'])) {
    keys = ['gongchen', 'canal', 'city']
  } else if (includesAny(text, ['西溪', '湿地'])) {
    keys = ['xixi', 'natureDetail', 'nature']
  } else if (includesAny(text, ['龙井', '茶园'])) {
    keys = ['longjing', 'teaGarden', 'teaSet']
  } else if (includesAny(text, ['灵隐'])) {
    keys = ['lingyin', 'westLakeDawn', 'hangzhou']
  } else if (includesAny(text, ['乐园', '游乐', '主题公园', '宋城', 'theme'])) {
    keys = ['songcheng', 'themeParkLights', 'themeParkDay']
  } else if (includesAny(text, ['动漫', '动画', '二次元'])) {
    keys = ['animationMuseum', 'entertainment', 'nightlife']
  } else if (includesAny(text, ['儿童', '亲子', '孩子', 'kids'])) {
    keys = ['kidsDiscovery', 'kids', 'family']
  } else if (includesAny(text, ['攀岩', '卡丁车', '运动', 'sport'])) {
    keys = ['climbing', 'sportDetail', 'sport']
  } else if (includesAny(text, ['夜游', '夜景', '音乐', 'night'])) {
    keys = ['nightlife', 'canal', 'performance']
  } else if (includesAny(text, ['旅拍', '摄影', '拍照', 'photo'])) {
    keys = ['photo', 'couple', 'city']
  } else if (includesAny(text, ['美食', '杭帮菜', '甜品', '咖啡', '烘焙', 'food'])) {
    keys = ['warmFood', 'food', 'breakfast']
  } else if (includesAny(text, ['自然', '动物', '植物', 'nature'])) {
    keys = ['natureDetail', 'nature', 'lake']
  } else if (includesAny(text, ['演出', '儿童剧', '剧场', 'performance'])) {
    keys = ['performance', 'songcheng', 'nightlife']
  } else if (includesAny(text, ['非遗', '手作', '文化', 'craft'])) {
    keys = ['craftHands', 'craftTable', 'craft']
  } else if (includesAny(text, ['茶', '点茶', 'tea'])) {
    keys = ['teaSet', 'teaGarden', 'tea']
  } else {
    keys = mediaForProduct(product).map((item) => item.id === 'hangzhou-water-town' ? 'hangzhou' : Object.entries(MEDIA_LIBRARY).find((entry) => entry[1].id === item.id)?.[0]).filter(Boolean) as string[]
  }
  const assets = keys.map((key) => MEDIA_LIBRARY[key]).filter(Boolean)
  // Curated CDN assets are served through our own cache (see cachedMediaUrl).
  // The on-demand Wikimedia cover lookup is intentionally NOT used any more:
  // it timed out on the deployment host and made operator pages crawl.
  return rotate(assets, Number(product?.id || 0) + index * 3 + Number(resource?.id || 0))
}

export function mediaForResource(product: ProductMediaInput | null | undefined, resource: ProductResource | undefined, index = 0) {
  return mediaCandidatesForResource(product, resource, index)[0] || mediaForProduct(product)[index % Math.max(mediaForProduct(product).length, 1)] || MEDIA_LIBRARY.hangzhou
}

export function experienceMoments(product?: ProductMediaInput | null): ProductMoment[] {
  if (!product) return []
  const chosen: ProductMoment[] = []
  const usedIds = new Set<string>()
  const usedSources = new Set<string>()
  product.resources.forEach((resource, index) => {
    const candidates = mediaCandidatesForResource(product, resource, index)
    const media = candidates.find((candidate) => !usedIds.has(candidate.id) && !usedSources.has(candidate.source)) || candidates.find((candidate) => !usedIds.has(candidate.id)) || candidates[0]
    if (media && chosen.length < 6) {
      chosen.push({ media, resource_name: resource.resource_name, resource_type: resource.resource_type })
      usedIds.add(media.id)
      usedSources.add(media.source)
    }
  })
  const fallbacks = mediaForProduct(product)
  fallbacks.forEach((media) => {
    if (chosen.length < 6 && !usedIds.has(media.id)) {
      chosen.push({ media, resource_name: '杭州漫游', resource_type: 'PARTNER_RESOURCE' })
      usedIds.add(media.id)
    }
  })
  return chosen
}

export { MEDIA_LIBRARY }
