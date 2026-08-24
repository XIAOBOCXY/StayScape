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

// 固定的公开演示素材：这是杭州主题的氛围参考图，不代表酒店或合作商户真实供图。
// 页面只消费 mediaForProduct 的结果，避免把几十个 URL 散落在组件中。
const MEDIA_LIBRARY_RAW: Record<string, ProductMediaAsset> = {
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
  familyTable: { id: 'family-table', url: 'https://images.unsplash.com/photo-1472162072942-cd5147eb3902?auto=format&fit=crop&w=1400&q=85', alt: '家人围坐分享旅行时光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-dinner-travel', kind: 'family' },
  themePark: { id: 'hangzhou-theme-park', url: 'https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1400&q=85', alt: '夜色中的游乐园摩天轮与灯光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/theme-park', kind: 'themePark' },
  themeParkDay: { id: 'theme-park-day', url: 'https://images.unsplash.com/photo-1513889961551-628c1efc99d7?auto=format&fit=crop&w=1400&q=85', alt: '白天游乐园的家庭旅行场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/amusement-park', kind: 'themePark' },
  entertainment: { id: 'city-entertainment', url: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=1400&q=85', alt: '城市音乐现场与年轻人娱乐氛围', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/live-music', kind: 'entertainment' },
  sport: { id: 'indoor-sport', url: 'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=1400&q=85', alt: '室内运动馆的运动体验场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/indoor-sports', kind: 'sport' },
  sportDetail: { id: 'sport-detail', url: 'https://images.unsplash.com/photo-1517836357463-d25dfeac3438?auto=format&fit=crop&w=1400&q=85', alt: '朋友一起完成运动挑战的细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/sports-friends', kind: 'sport' },
  nightlife: { id: 'hangzhou-nightlife', url: 'https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=1400&q=85', alt: '城市夜色与灯光组成的夜游场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/city-night', kind: 'nightlife' },
  food: { id: 'jiangnan-food', url: 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1400&q=85', alt: '餐桌与江南美食体验氛围', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/restaurant-table', kind: 'food' },
  nature: { id: 'xixi-nature', url: 'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=1400&q=85', alt: '湿地与树木组成的自然探索场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/wetland-nature', kind: 'nature' },
  natureDetail: { id: 'nature-detail', url: 'https://images.unsplash.com/photo-1473445361085-b9a07f55608b?auto=format&fit=crop&w=1400&q=85', alt: '亲子自然观察与植物细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/nature-walk', kind: 'nature' },
  photo: { id: 'city-photo-walk', url: 'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=1400&q=85', alt: '城市旅拍中的相机与街景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/city-photography', kind: 'photo' },
  performance: { id: 'city-performance', url: 'https://images.unsplash.com/photo-1501386761578-eac5c94b800a?auto=format&fit=crop&w=1400&q=85', alt: '城市演出现场的舞台与观众', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/theater-performance', kind: 'performance' },
  kids: { id: 'kids-indoor-play', url: 'https://images.unsplash.com/photo-1503454537195-1dcabb73ffb9?auto=format&fit=crop&w=1400&q=85', alt: '儿童在室内游乐空间探索', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/kids-indoor-play', kind: 'kids' },
  couple: { id: 'couple-hangzhou-trip', url: 'https://images.unsplash.com/photo-1511988617509-a57c8a288659?auto=format&fit=crop&w=1400&q=85', alt: '情侣旅行中的城市漫游时刻', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/couple-travel', kind: 'couple' },
  themeParkLights: { id: 'theme-park-lights', url: 'https://images.pexels.com/photos/1779487/pexels-photo-1779487.jpeg?auto=compress&cs=tinysrgb&w=1400', alt: '夜间游乐园灯光与摩天轮', source: 'Pexels', source_url: 'https://www.pexels.com/photo/ferris-wheel-under-the-stars-1779487/', kind: 'themePark' },
  kidsDiscovery: { id: 'kids-discovery', url: 'https://images.pexels.com/photos/3662667/pexels-photo-3662667.jpeg?auto=compress&cs=tinysrgb&w=1400', alt: '儿童在探索空间中动手体验', source: 'Pexels', source_url: 'https://www.pexels.com/photo/children-playing-inside-a-room-3662667/', kind: 'kids' },
  climbing: { id: 'climbing-wall', url: 'https://images.pexels.com/photos/1699030/pexels-photo-1699030.jpeg?auto=compress&cs=tinysrgb&w=1400', alt: '室内攀岩运动体验', source: 'Pexels', source_url: 'https://www.pexels.com/search/indoor%20climbing/', kind: 'sport' },
  warmFood: { id: 'warm-food-editorial', url: 'https://images.pexels.com/photos/262978/pexels-photo-262978.jpeg?auto=compress&cs=tinysrgb&w=1400', alt: '暖色餐桌与城市美食体验', source: 'Pexels', source_url: 'https://www.pexels.com/photo/restaurant-interior-262978/', kind: 'food' },
  westLake: { id: 'west-lake-hangzhou-2025', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/West%20Lake%2C%20Hangzhou%202025.jpg?width=1800', alt: '杭州西湖的湖面与群山', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:West_Lake,_Hangzhou_2025.jpg', kind: 'city', attribution: 'Wikimedia Commons · CC BY 4.0', license: 'CC BY 4.0', location: '杭州 · 西湖' },
  westLakeDawn: { id: 'west-lake-dawn', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/Hangzhou%60s%20West%20Lake%20scenery%20at%20dawn.JPG?width=1800', alt: '清晨的杭州西湖', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Hangzhou%60s_West_Lake_scenery_at_dawn.JPG', kind: 'city', attribution: 'Wikimedia Commons · public domain', license: 'Public domain', location: '杭州 · 西湖' },
  gongchen: { id: 'gongchen-bridge', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/20231122%20Gongchen%20Bridge%2002.jpg?width=1800', alt: '杭州拱宸桥与运河景观', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:20231122_Gongchen_Bridge_02.jpg', kind: 'city', attribution: 'Wikimedia Commons · CC BY-SA 4.0', license: 'CC BY-SA 4.0', location: '杭州 · 拱宸桥' },
  xixi: { id: 'xixi-wetland', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/Xixi%20Wetland%20Park%2C%20Hangzhou%2C%E6%9D%AD%E5%B7%9E%E8%A5%BF%E6%BA%AA%E6%B9%BF%E5%9C%B0%20-%20panoramio.jpg?width=1800', alt: '杭州西溪湿地景观', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Xixi_Wetland_Park,_Hangzhou,%E6%9D%AD%E5%B7%9E%E8%A5%BF%E6%BA%AA%E6%B9%BF%E5%9C%B0_-_panoramio.jpg', kind: 'nature', attribution: 'Wikimedia Commons · CC BY-SA 3.0', license: 'CC BY-SA 3.0', location: '杭州 · 西溪湿地' },
  longjing: { id: 'longjing-tea-garden', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/Tea%20Garden%20Hangzhou.jpg?width=1800', alt: '杭州茶园与山景', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Tea_Garden_Hangzhou.jpg', kind: 'tea', attribution: 'Wikimedia Commons · CC BY 4.0', license: 'CC BY 4.0', location: '杭州 · 龙井茶园' },
  lingyin: { id: 'lingyin-temple', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/Lingyin%20Buddhist%20Temple%2C%20Hangzhou%20%283020083374%29.jpg?width=1800', alt: '杭州灵隐寺建筑景观', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Lingyin_Buddhist_Temple,_Hangzhou_(3020083374).jpg', kind: 'culture', attribution: 'Wikimedia Commons · CC BY 2.0', license: 'CC BY 2.0', location: '杭州 · 灵隐' },
  silkMuseum: { id: 'china-national-silk-museum', url: 'https://zh.unesco.org/silkroad/sites/default/files/styles/silkroad_colorbox/public/museum_front.jpg?itok=y1whLB1I', alt: '杭州中国丝绸博物馆外观', source: 'UNESCO Silk Roads', source_url: 'https://zh.unesco.org/silkroad/content/zhongguosichoubowuguan', kind: 'culture', attribution: 'UNESCO Silk Roads · 来源页', license: '来源页标注 · 仅作演示参考', location: '杭州 · 中国丝绸博物馆' },
  liangzhuCctv: { id: 'liangzhu-museum-cctv', url: 'https://p2.img.cctvpic.com/photoworkspace/contentimg/2025/02/07/2025020710435689379.jpg', alt: '杭州良渚博物院建筑与园区', source: '央视网', source_url: 'https://caiyi.cctv.com/2025/02/07/ARTIfQRVTDD9Es3ApjildzUc250207.shtml', kind: 'culture', attribution: '央视网 · 来源页', license: '来源页标注 · 仅作演示参考', location: '杭州 · 良渚博物院' },
  songcheng: { id: 'hangzhou-songcheng-night', url: 'https://youimg1.c-ctrip.com/target/100q040000000b7qhD3B1.jpg', alt: '杭州宋城夜间入口与灯光', source: '携程旅行', source_url: 'https://you.ctrip.com/sight/hangzhou14/4081.html', kind: 'themePark', attribution: '携程旅行 · 来源页', license: '来源页标注 · 仅作演示参考', location: '杭州 · 宋城' },
  animationMuseum: { id: 'china-cartoon-animation-museum', url: 'https://obj.shine.cn/files/2021/06/29/78356371-6dde-4ebf-919f-e82b85c43d8a_0.jpg', alt: '杭州中国动漫博物馆建筑', source: 'Shanghai Daily City News', source_url: 'https://www.citynewsservice.cn/shine/814b1dde-b79e-45d5-a3ca-90d49ddf1e29', kind: 'entertainment', attribution: 'Shanghai Daily City News · 来源页', license: '来源页标注 · 仅作演示参考', location: '杭州 · 中国动漫博物馆' },
  liangzhuMuseum: { id: 'liangzhu-museum', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/Liangzhu%20Museum%2C%202019-07-07%2009.jpg?width=1800', alt: '杭州良渚博物院建筑', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:Liangzhu_Museum,_2019-07-07_09.jpg', kind: 'culture', attribution: 'Wikimedia Commons · CC BY-SA 4.0', license: 'CC BY-SA 4.0', location: '杭州 · 良渚' }
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
  const merged = [...rotated, ...fallback]
  return merged.filter((item, index, list) => list.findIndex((candidate) => candidate.id === item.id) === index).slice(0, 8)
}

export function heroMedia(product?: Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> | null) { return mediaForProduct(product)[0] }
export function experienceLabel(resourceType: string) { return ({ ROOM: 'STAY', HOTEL_SERVICE: 'TASTE', PARTNER_RESOURCE: 'EXPERIENCE' } as Record<string, string>)[resourceType] || 'MOMENT' }
export function experienceLabelZh(resourceType: string) { return ({ ROOM: '住宿', HOTEL_SERVICE: '贴心服务', PARTNER_RESOURCE: '在地体验' } as Record<string, string>)[resourceType] || '旅居内容' }
export function weatherLabel(weather: string) { return ({ RAIN: 'RAIN FRIENDLY', SUNNY: 'SUNNY DAY', CLOUDY: 'SOFT CLOUDS' } as Record<string, string>)[weather] || weather }


export interface ProductMoment {
  media: ProductMediaAsset
  resource_name: string
  resource_type: string
}

type ProductMediaInput = Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'>
type ProductResource = TravelProduct['resources'][number]

function mediaCandidatesForResource(product: ProductMediaInput | null | undefined, resource: ProductResource | undefined, index = 0) {
  if (!resource) return mediaForProduct(product)
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
  return rotate(assets, Number(product?.id || 0) + index * 3)
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
    if (media && chosen.length < 3) {
      chosen.push({ media, resource_name: resource.resource_name, resource_type: resource.resource_type })
      usedIds.add(media.id)
      usedSources.add(media.source)
    }
  })
  const fallbacks = mediaForProduct(product)
  fallbacks.forEach((media) => {
    if (chosen.length < 3 && !usedIds.has(media.id)) {
      chosen.push({ media, resource_name: '杭州漫游', resource_type: 'PARTNER_RESOURCE' })
      usedIds.add(media.id)
    }
  })
  return chosen
}

export { MEDIA_LIBRARY }
