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
  if (!/^https:\/\/(images\.unsplash\.com|images\.pexels\.com|commons\.wikimedia\.org)\//.test(url)) return url
  return `/api/v1/visitor/media/proxy?url=${encodeURIComponent(url)}`
}

// 固定的公开演示素材：这是杭州主题的氛围参考图，不代表酒店或合作商户真实供图。
// 页面只消费 mediaForProduct 的结果，避免把几十个 URL 散落在组件中。
const MEDIA_LIBRARY_RAW: Record<string, ProductMediaAsset> = {
  hangzhou: { id: 'hangzhou-water-town', url: '/generated-media/resource-media/curated-hangzhou.jpg', alt: '江南水乡与山水的旅行氛围图', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/hangzhou-water-town', kind: 'scene' },
  rain: { id: 'hangzhou-rain-window', url: '/generated-media/resource-media/curated-rain.jpg', alt: '雨天窗边的安静旅行场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/rainy-window', kind: 'scene' },
  // 线上旧素材与标注不符（包含熊猫图和带平台水印的客房图）。在商户上传实拍图前，
  // 游客端使用已核对的杭州城市氛围图，不把参考照片伪装成套餐现场实拍。
  hotel: { id: 'hangzhou-city-walk', url: '/generated-media/resource-media/curated-city.jpg', alt: '杭州城市水岸旅行氛围图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-city.jpg', kind: 'city' },
  hotelWindow: { id: 'hangzhou-city-walk', url: '/generated-media/resource-media/curated-city.jpg', alt: '杭州城市水岸旅行氛围图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-city.jpg', kind: 'city' },
  breakfast: { id: 'hangzhou-food-space', url: '/generated-media/resource-media/curated-food.jpg', alt: '城市餐饮空间氛围图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-food.jpg', kind: 'food' },
  craft: { id: 'hangzhou-city-walk', url: '/generated-media/resource-media/curated-city.jpg', alt: '杭州城市水岸旅行氛围图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-city.jpg', kind: 'city' },
  craftTable: { id: 'pottery-finish-detail', url: '/generated-media/resource-media/place-e4da1a7de18e463984e0bd61594afbbf.jpg', alt: '双人陶艺手作杯成品', source: 'StayScape资源档案', source_url: '/generated-media/resource-media/place-e4da1a7de18e463984e0bd61594afbbf.jpg', kind: 'culture', usage_note: '双人陶艺体验的另一张作品参考图', license: '合作资源档案' },
  potteryPeople: { id: 'pottery-workshop-process-943', url: '/generated-media/resource-media/place-943483bbd9c445a19d3eba9407efb930.jpg', alt: '双人陶艺体验中的手作过程', source: 'StayScape资源档案', source_url: '/generated-media/resource-media/place-943483bbd9c445a19d3eba9407efb930.jpg', kind: 'culture', usage_note: '双人陶艺体验的过程实拍', license: '合作资源档案' },
  craftHands: { id: 'hangzhou-city-walk', url: '/generated-media/resource-media/curated-city.jpg', alt: '杭州城市水岸旅行氛围图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-city.jpg', kind: 'city' },
  roomCityView: { id: 'room-city-view-c3237eab', url: '/generated-media/resource-media/place-c3237eab36be40e68331bffdc629d30d.jpg', alt: '城市景观房房型图', source: 'StayScape资源档案', source_url: '/generated-media/resource-media/place-c3237eab36be40e68331bffdc629d30d.jpg', kind: 'room', usage_note: '对应城市景观房的已存档房型图片', license: '酒店资源档案' },
  roomFamilySuite: { id: 'room-family-suite-18d2e111', url: '/generated-media/resource-media/place-18d2e111c192475dadf358fb8d05e279.jpg', alt: '家庭套房房型图', source: 'StayScape资源档案', source_url: '/generated-media/resource-media/place-18d2e111c192475dadf358fb8d05e279.jpg', kind: 'room', usage_note: '对应家庭套房的已存档房型图片', license: '酒店资源档案' },
  potteryWorkshop: { id: 'partner-pottery-982bbc97', url: '/generated-media/resource-media/place-982bbc97e2984cadbeeceb37150ddd83.jpg', alt: '双人陶艺体验参考图', source: 'StayScape资源档案', source_url: '/generated-media/resource-media/place-982bbc97e2984cadbeeceb37150ddd83.jpg', kind: 'culture', usage_note: '对应双人陶艺体验的已存档资源图片', license: '合作资源档案' },
  dessertWorkshop: { id: 'partner-dessert-5cba908b', url: '/generated-media/resource-media/place-5cba908b6b4942b5aa90019a76bd1434.jpg', alt: '江南甜品手作体验参考图', source: 'StayScape资源档案', source_url: '/generated-media/resource-media/place-5cba908b6b4942b5aa90019a76bd1434.jpg', kind: 'food', usage_note: '对应江南甜品制作的已存档资源图片', license: '合作资源档案' },
  tea: { id: 'tea-culture', url: '/generated-media/resource-media/curated-tea.jpg', alt: '茶杯与茶叶组成的茶文化场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/chinese-tea-ceremony', kind: 'tea' },
  teaSet: { id: 'tea-set-table', url: '/generated-media/resource-media/curated-teaSet.jpg', alt: '茶器与茶席的近景细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/tea-set', kind: 'tea' },
  teaGarden: { id: 'tea-garden', url: '/generated-media/resource-media/curated-teaGarden.jpg', alt: '江南茶园与绿色山坡', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/tea-garden', kind: 'tea' },
  city: { id: 'hangzhou-city-walk', url: '/generated-media/resource-media/curated-city.jpg', alt: '杭州城市水岸旅行氛围图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-city.jpg', kind: 'city' },
  qianjiang: { id: 'qianjiang-city-balcony', url: 'https://upload.wikimedia.org/wikipedia/commons/7/78/20201012%E4%BB%8E%E9%92%B1%E5%A1%98%E6%B1%9F%E6%B1%9F%E9%9D%A2%E4%B8%8A%E7%A9%BA%E8%A7%82%E7%9C%8B%E9%92%B1%E6%B1%9F%E6%96%B0%E5%9F%8E_2.jpg', alt: '从钱塘江江面上空观看钱江新城城市阳台', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:20201012从钱塘江江面上空观看钱江新城_2.jpg', kind: 'city', attribution: 'MasaneMiyaPA · Wikimedia Commons · CC BY-SA 4.0', license: 'CC BY-SA 4.0', location: '杭州 · 钱江新城' },
  canal: { id: 'canal-night-lights', url: '/generated-media/resource-media/curated-canal.jpg', alt: '运河夜色与城市灯光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/canal-night', kind: 'city' },
  lake: { id: 'lake-walk', url: '/generated-media/resource-media/curated-lake.jpg', alt: '湖边散步与江南风景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/lake-walk', kind: 'scene' },
  family: { id: 'family-travel', url: '/generated-media/resource-media/curated-family.jpg', alt: '家庭旅行中的亲密陪伴场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-travel', kind: 'family' },
  familyRoom: { id: 'family-table-workshop', url: '/generated-media/resource-media/curated-familyRoom.jpg', alt: '家人在桌边共同创作的体验参考图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-familyRoom.jpg', kind: 'family' },
  familyTable: { id: 'family-table', url: '/generated-media/resource-media/curated-familyTable.jpg', alt: '家人围坐分享旅行时光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/family-dinner-travel', kind: 'family' },
  themePark: { id: 'hangzhou-theme-park', url: '/generated-media/resource-media/curated-themePark.jpg', alt: '夜色中的游乐园摩天轮与灯光', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/theme-park', kind: 'themePark' },
  themeParkDay: { id: 'theme-park-day', url: '/generated-media/resource-media/curated-themeParkDay.jpg', alt: '白天游乐园的家庭旅行场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/amusement-park', kind: 'themePark' },
  entertainment: { id: 'city-entertainment', url: '/generated-media/resource-media/curated-entertainment.jpg', alt: '城市音乐现场与年轻人娱乐氛围', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/live-music', kind: 'entertainment' },
  sport: { id: 'indoor-sport', url: '/generated-media/resource-media/curated-sport.jpg', alt: '室内运动馆的运动体验场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/indoor-sports', kind: 'sport' },
  sportDetail: { id: 'sport-detail', url: '/generated-media/resource-media/curated-sportDetail.jpg', alt: '朋友一起完成运动挑战的细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/sports-friends', kind: 'sport' },
  nightlife: { id: 'hangzhou-nightlife', url: '/generated-media/resource-media/curated-nightlife.jpg', alt: '城市夜色与灯光组成的夜游场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/city-night', kind: 'nightlife' },
  food: { id: 'hangzhou-food-space', url: '/generated-media/resource-media/curated-food.jpg', alt: '城市餐饮空间氛围图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-food.jpg', kind: 'food' },
  nature: { id: 'xixi-nature', url: '/generated-media/resource-media/curated-nature.jpg', alt: '湿地与树木组成的自然探索场景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/wetland-nature', kind: 'nature' },
  natureDetail: { id: 'nature-detail', url: '/generated-media/resource-media/curated-natureDetail.jpg', alt: '亲子自然观察与植物细节', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/nature-walk', kind: 'nature' },
  animalInteractionSheep: { id: 'animal-interaction-sheep', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/A_young_child_reaches_out_to_feed_a_fluffy_sheep_inside_a_cozy_barn.jpg', alt: '儿童与动物互动体验参考图；非套餐商家实拍', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:A_young_child_reaches_out_to_feed_a_fluffy_sheep_inside_a_cozy_barn.jpg', kind: 'nature', attribution: 'Shixart1985 · Wikimedia Commons · CC BY 2.0', license: 'CC BY 2.0', usage_note: '动物互动氛围参考，不代表具体合作场地或动物种类' },
  animalInteractionGiraffe: { id: 'animal-interaction-giraffe', url: 'https://commons.wikimedia.org/wiki/Special:FilePath/People_feeding_a_Masai_giraffe_-_Cleveland_Zoo_%2828357520757%29.jpg', alt: '游客喂食长颈鹿的动物互动参考图；非套餐商家实拍', source: 'Wikimedia Commons', source_url: 'https://commons.wikimedia.org/wiki/File:People_feeding_a_Masai_giraffe_-_Cleveland_Zoo_(28357520757).jpg', kind: 'nature', attribution: 'Tim Evanson · Wikimedia Commons · CC BY-SA 2.0', license: 'CC BY-SA 2.0', usage_note: '动物互动氛围参考，不代表具体合作场地或动物种类' },
  photo: { id: 'city-photo-walk', url: '/generated-media/resource-media/curated-photo.jpg', alt: '城市旅拍中的相机与街景', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/city-photography', kind: 'photo' },
  performance: { id: 'city-performance', url: '/generated-media/resource-media/curated-performance.jpg', alt: '城市演出现场的舞台与观众', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/theater-performance', kind: 'performance' },
  kids: { id: 'kids-indoor-play', url: '/generated-media/resource-media/curated-kids.jpg', alt: '儿童在室内游乐空间探索', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/kids-indoor-play', kind: 'kids' },
  couple: { id: 'couple-hangzhou-trip', url: '/generated-media/resource-media/curated-couple.jpg', alt: '情侣旅行中的城市漫游时刻', source: 'Unsplash', source_url: 'https://unsplash.com/s/photos/couple-travel', kind: 'couple' },
  themeParkLights: { id: 'theme-park-lights', url: '/generated-media/resource-media/curated-themeParkLights.jpg', alt: '夜间游乐园灯光与摩天轮', source: 'Pexels', source_url: 'https://www.pexels.com/photo/ferris-wheel-under-the-stars-1779487/', kind: 'themePark' },
  kidsDiscovery: { id: 'kids-discovery', url: '/generated-media/resource-media/curated-kidsDiscovery.jpg', alt: '儿童在探索空间中动手体验', source: 'Pexels', source_url: 'https://www.pexels.com/photo/children-playing-inside-a-room-3662667/', kind: 'kids' },
  climbing: { id: 'climbing-wall', url: '/generated-media/resource-media/curated-climbing.jpg', alt: '室内攀岩运动体验', source: 'Pexels', source_url: 'https://www.pexels.com/search/indoor%20climbing/', kind: 'sport' },
  warmFood: { id: 'hangzhou-food-space', url: '/generated-media/resource-media/curated-food.jpg', alt: '城市餐饮空间氛围图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-food.jpg', kind: 'food' },
  westLake: { id: 'west-lake-hangzhou-2025', url: '/generated-media/resource-media/curated-westLake.png', alt: '杭州西湖湖面与水岸景观参考图', source: '项目内参考素材', source_url: '/generated-media/resource-media/curated-westLake.png', kind: 'city', location: '杭州 · 西湖' },
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
  const pottery = includesAny(text, ['陶艺', '陶杯', '陶瓷'])
  const dessert = includesAny(text, ['甜品', '烘焙'])
  const tea = includesAny(text, ['茶', '点茶', '茶器', '茶园', 'tea'])
  const family = includesAny(text, ['亲子', '家庭', 'family']) || product.target_crowd === 'FAMILY'
  const couple = includesAny(text, ['情侣', '夫妻', '旅拍', 'couple']) || product.target_crowd === 'COUPLE'
  const city = includesAny(text, ['西湖', '运河', '城市', '漫游', '摄影', 'city']) || couple
  const seed = Number(product.id || 0)
  const themeSet = pottery ? [MEDIA_LIBRARY.potteryWorkshop, MEDIA_LIBRARY.potteryPeople, MEDIA_LIBRARY.craftTable] : dessert ? [MEDIA_LIBRARY.dessertWorkshop, MEDIA_LIBRARY.food] : themePark ? [MEDIA_LIBRARY.themeParkDay, MEDIA_LIBRARY.themeParkLights, MEDIA_LIBRARY.songcheng] : kids ? [MEDIA_LIBRARY.kids, MEDIA_LIBRARY.family, MEDIA_LIBRARY.familyRoom] : sport ? [MEDIA_LIBRARY.sport, MEDIA_LIBRARY.sportDetail, MEDIA_LIBRARY.climbing] : nightlife ? [MEDIA_LIBRARY.nightlife, MEDIA_LIBRARY.city] : food ? [MEDIA_LIBRARY.food, MEDIA_LIBRARY.city] : nature ? [MEDIA_LIBRARY.nature, MEDIA_LIBRARY.natureDetail] : photo ? [MEDIA_LIBRARY.photo, MEDIA_LIBRARY.city] : performance ? [MEDIA_LIBRARY.performance, MEDIA_LIBRARY.entertainment] : entertainment ? [MEDIA_LIBRARY.entertainment, MEDIA_LIBRARY.nightlife] : tea ? [MEDIA_LIBRARY.tea, MEDIA_LIBRARY.teaSet, MEDIA_LIBRARY.teaGarden] : culture ? [MEDIA_LIBRARY.city] : city ? [MEDIA_LIBRARY.westLake, MEDIA_LIBRARY.city] : family ? [MEDIA_LIBRARY.family, MEDIA_LIBRARY.familyRoom] : [MEDIA_LIBRARY.city]
  const supportSet = family ? [MEDIA_LIBRARY.familyRoom] : sport ? [MEDIA_LIBRARY.sportDetail] : food ? [MEDIA_LIBRARY.city] : tea ? [MEDIA_LIBRARY.teaGarden] : culture ? [MEDIA_LIBRARY.city] : [MEDIA_LIBRARY.city]
  const contextSet = nightlife ? [MEDIA_LIBRARY.gongchen, MEDIA_LIBRARY.nightlife] : nature ? [MEDIA_LIBRARY.xixi, MEDIA_LIBRARY.nature] : tea ? [MEDIA_LIBRARY.longjing, MEDIA_LIBRARY.hangzhou] : city ? [MEDIA_LIBRARY.westLake, MEDIA_LIBRARY.gongchen] : product.weather === 'RAIN' ? [MEDIA_LIBRARY.rain, MEDIA_LIBRARY.hotel] : [MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.city]
  return [...rotate(themeSet, seed), ...rotate(supportSet, seed + 1), ...rotate(contextSet, seed + 2)].filter((item, index, list) => list.findIndex((candidate) => candidate.id === item.id || candidate.url === item.url) === index).slice(0, 8)
}

/** Match the hero to the purchased experience, then add only related scene
 * images. Stable ordering keeps the same product image consistent in lists
 * and details. */
export function mediaForProduct(product?: ProductMediaInput | null): ProductMediaAsset[] {
  if (!product) return [MEDIA_LIBRARY.hangzhou, MEDIA_LIBRARY.rain, MEDIA_LIBRARY.hotel, MEDIA_LIBRARY.tea]
  const visualResources = product.resources.filter((resource) => {
    if (resource.resource_type === 'ROOM') return false
    if (resource.resource_type === 'HOTEL_SERVICE' && includesAny(resource.resource_name, ['行李寄存', '办理入住', '办理退房'])) return false
    return true
  })
  const galleryResources = visualResources.length
    ? visualResources
    : product.resources.filter((resource) => resource.resource_type === 'ROOM').slice(0, 1)
  const mappedResources = galleryResources.flatMap((resource, index) => mediaCandidatesForResource(product, resource, index))
  const packageMedia = mappedResources.filter((item, index, list) =>
    item.kind !== 'room' && list.findIndex((candidate) => candidate.id === item.id || candidate.url === item.url) === index,
  )
  if (packageMedia.length) return packageMedia.slice(0, 8)
  // Match photos to the purchased activity first. Addresses and generated copy
  // often contain nearby museums or districts that are not the experience itself.
  const text = [product.product_name, product.theme, product.target_crowd, ...product.resources.map((item) => item.resource_name)].join(' ').toLowerCase()
  const experienceText = product.resources.filter((item) => item.resource_type !== 'ROOM').map((item) => item.resource_name).join(' ').toLowerCase()
  const tests: Array<[string[], string[]]> = [
    [['陶艺', '陶杯', '陶瓷'], ['potteryWorkshop', 'potteryPeople', 'craftTable']],
    [['甜品', '烘焙'], ['dessertWorkshop', 'food']],
    [['美食', '杭帮菜', '咖啡', 'food'], ['food', 'city']],
    [['乐园', '游乐', '主题公园', '宋城', 'theme'], ['themeParkDay', 'themeParkLights', 'songcheng']],
    [['攀岩', '卡丁车', '运动', 'sport'], ['sport', 'sportDetail', 'climbing', 'entertainment']],
    [['博物馆', '良渚', '看展', '美术馆', '科技馆', '展览', '丝绸'], ['silkMuseum', 'liangzhuCctv', 'liangzhuMuseum', 'hotel']],
    [['西湖', '湖滨', '湖畔'], ['westLake', 'westLakeDawn', 'hotel', 'breakfast']],
    [['运河', '拱宸'], ['gongchen', 'canal', 'city', 'photo']],
    [['西溪', '湿地'], ['xixi', 'nature', 'lake', 'family']],
    [['龙井', '茶园'], ['longjing', 'tea', 'teaSet', 'hotel']],
    [['灵隐'], ['lingyin', 'westLake', 'hotel', 'city']],
    [['儿童', '亲子', '孩子', 'kids'], ['kids', 'kidsDiscovery', 'family', 'familyRoom']],
    [['夜游', '夜景', '音乐', 'night'], ['nightlife', 'canal', 'city', 'performance']],
    [['旅拍', '摄影', '拍照', 'photo'], ['photo', 'couple', 'city', 'lake']],
    [['自然', '湿地', '动物', '植物', 'nature'], ['nature', 'natureDetail', 'lake', 'family']],
    [['演出', '儿童剧', '剧场', 'performance'], ['songcheng', 'performance', 'entertainment', 'nightlife']],
    [['动漫', '动画', '二次元'], ['animationMuseum', 'entertainment', 'city', 'nightlife']],
    [['茶', '点茶', '茶园', 'tea'], ['tea', 'teaSet', 'teaGarden', 'hangzhou']],
  ]
  const matched = tests.find(([words]) => words.some((word) => experienceText.includes(word)))
    || tests.find(([words]) => words.some((word) => text.includes(word)))
  const fallback = legacyMediaForProduct(product)
  const keys = matched?.[1] || (product.target_crowd === 'COUPLE' ? ['couple', 'photo', 'nightlife', 'lake'] : product.target_crowd === 'FRIENDS' ? ['entertainment', 'sport', 'nightlife', 'city'] : ['hotel', 'hotelWindow', 'hangzhou', 'family'])
  const catalogItems = keys.map((key) => MEDIA_LIBRARY[key]).filter(Boolean)
  // Keep a matched experience's image order stable. Rotating the first image
  // by product ID made unrelated assets become the public hero image.
  const merged = matched ? catalogItems : fallback
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

type ProductMediaInput = Pick<TravelProduct, 'id' | 'product_name' | 'theme' | 'target_crowd' | 'weather' | 'resources'> & { stay?: { room_type?: string; room_name?: string } | null }
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

export function mediaCandidatesForResource(product: ProductMediaInput | null | undefined, resource: ProductResource | undefined, index = 0) {
  if (!resource) return mediaForProduct(product)
  const upload = uploadedMedia(resource)
  const text = [resource.resource_name, product?.product_name || '', product?.theme || ''].join(' ').toLowerCase()
  const activityName = String(resource.resource_name || '').toLowerCase()
  let keys: string[]
  if (resource.resource_type === 'ROOM') {
    const roomLabel = `${activityName} ${product?.stay?.room_type || ''} ${product?.stay?.room_name || ''}`
    keys = includesAny(roomLabel, ['家庭套房', '家庭房', '亲子']) ? ['roomFamilySuite'] : ['roomCityView']
  } else if (resource.resource_type === 'PUBLIC_REFERENCE') {
    if (includesAny(activityName, ['西湖风景名胜区'])) keys = ['westLakeDawn']
    else if (includesAny(activityName, ['运河杭州段', '京杭大运河'])) keys = ['gongchen']
    else if (includesAny(activityName, ['小河直街'])) keys = ['canal']
    else if (includesAny(activityName, ['湖滨步行街'])) keys = ['lake']
    else if (includesAny(activityName, ['清河坊', '河坊街'])) keys = ['hangzhou']
    else if (includesAny(activityName, ['钱江新城', '城市阳台'])) keys = ['qianjiang']
    else keys = ['city']
  } else if (resource.resource_type === 'HOTEL_SERVICE') {
    const roomLabel = `${product?.stay?.room_type || ''} ${product?.stay?.room_name || ''}`
    const roomKeys = includesAny(roomLabel, ['家庭套房', '家庭房', '亲子']) ? ['roomFamilySuite'] : ['roomCityView']
    keys = includesAny(text, ['行李寄存', '办理入住', '办理退房']) ? roomKeys
      : includesAny(text, ['餐', '美食', '咖啡', '下午茶', 'food']) ? ['food']
        : includesAny(text, ['茶', 'tea']) ? ['teaSet', 'tea'] : ['city']
  } else if (includesAny(activityName, ['动物互动', '动物体验', '动物观察', '喂养动物', '动物', '动物园', '牧场', 'animal'])) {
    keys = ['animalInteractionSheep', 'animalInteractionGiraffe']
  } else if (includesAny(activityName, ['甜品', '美食', '杭帮菜', '咖啡', '烘焙', 'food'])) {
    keys = includesAny(activityName, ['甜品', '烘焙']) ? ['dessertWorkshop'] : ['food']
  } else if (includesAny(activityName, ['陶艺', '陶杯', '陶瓷', '非遗', '手作', '文化', 'craft'])) {
    keys = ['potteryWorkshop', 'craftTable', 'potteryPeople']
  } else if (includesAny(activityName, ['乐园', '游乐', '主题公园', '宋城', 'theme'])) {
    keys = ['themeParkDay', 'themeParkLights', 'songcheng']
  } else if (includesAny(text, ['陶艺', '陶杯', '陶瓷', '非遗', '手作', '文化', 'craft'])) {
    keys = ['potteryWorkshop']
  } else if (includesAny(text, ['甜品', '美食', '杭帮菜', '咖啡', '烘焙', 'food'])) {
    keys = includesAny(text, ['甜品', '烘焙']) ? ['dessertWorkshop'] : ['food']
  } else if (includesAny(text, ['乐园', '游乐', '主题公园', '宋城', 'theme'])) {
    keys = ['themeParkDay', 'themeParkLights', 'songcheng']
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
    keys = ['food']
  } else if (includesAny(text, ['动物互动', '动物体验', '动物观察', '喂养动物', '动物', '动物园', '牧场', 'animal'])) {
    keys = ['animalInteractionSheep', 'animalInteractionGiraffe']
  } else if (includesAny(text, ['自然', '植物', 'nature'])) {
    keys = ['natureDetail', 'nature', 'lake']
  } else if (includesAny(text, ['演出', '儿童剧', '剧场', 'performance'])) {
    keys = ['performance', 'songcheng', 'nightlife']
  } else if (includesAny(text, ['非遗', '手作', '文化', 'craft'])) {
    keys = ['city']
  } else if (includesAny(text, ['茶', '点茶', 'tea'])) {
    keys = ['teaSet', 'teaGarden', 'tea']
  } else {
    keys = legacyMediaForProduct(product).map((item) => item.id === 'hangzhou-water-town' ? 'hangzhou' : Object.entries(MEDIA_LIBRARY).find((entry) => entry[1].id === item.id)?.[0]).filter(Boolean) as string[]
  }
  const assets = keys.map((key) => MEDIA_LIBRARY[key]).filter((item, index, list) => Boolean(item) && list.findIndex((candidate) => candidate?.url === item?.url) === index)
  // Curated CDN assets are served through our own cache (see cachedMediaUrl).
  // The on-demand Wikimedia cover lookup is intentionally NOT used any more:
  // it timed out on the deployment host and made operator pages crawl.
  // Some older demo rows carry a generic photo unrelated to their resource.
  // For animal experiences, do not show an unclassified upload at all: a
  // wrong species/scene is more misleading than a clearly labeled reference.
  const animalExperience = resource.resource_type === 'PARTNER_RESOURCE'
    && includesAny(activityName, ['动物互动', '动物体验', '动物观察', '喂养动物', '动物', '动物园', '牧场', 'animal'])
  const ordered = upload
    ? animalExperience
      ? assets
      : [upload, ...assets.filter((asset) => asset.url !== upload.url)]
    : assets
  return ordered.filter((item, index, list) => list.findIndex((candidate) => candidate.url === item.url) === index)
}

/** Prefer a unique relevant photo; reuse the best matching photo when the
 * catalog has fewer images than itinerary entries, rather than showing a
 * missing-image placeholder. Repeated resources rotate through their own set. */
export function distinctMediaForResources(
  product: ProductMediaInput | null | undefined,
  resources: ProductResource[],
  reservedUrls: string[] = [],
): Array<ProductMediaAsset | null> {
  const used = new Set(reservedUrls.filter(Boolean))
  const appearance = new Map<string, number>()
  return resources.map((resource, index) => {
    const identity = `${resource.resource_type}:${String(resource.resource_name || '').trim().toLowerCase()}`
    const cycle = appearance.get(identity) || 0
    appearance.set(identity, cycle + 1)
    const candidates = mediaCandidatesForResource(product, resource, index)
    // Older products can have a product-level image without a resource mapping.
    // Fall back to the product gallery before rendering an empty image tile.
    const fallback = mediaForProduct(product)
    const available = candidates.length ? candidates : fallback.length ? fallback : [MEDIA_LIBRARY.hangzhou]
    const start = cycle % available.length
    const rotated = [...available.slice(start), ...available.slice(0, start)]
    const media = rotated.find((candidate) => !used.has(candidate.url)) || rotated[0] || null
    if (media) used.add(media.url)
    return media
  })
}

export function mediaForResource(product: ProductMediaInput | null | undefined, resource: ProductResource | undefined, index = 0) {
  const candidates = mediaCandidatesForResource(product, resource, index)
  return candidates[index % Math.max(candidates.length, 1)] || mediaForProduct(product)[index % Math.max(mediaForProduct(product).length, 1)] || MEDIA_LIBRARY.hangzhou
}

/** One canonical image for list cards and the detail hero. */
export function primaryProductMedia(product?: ProductMediaInput | null): ProductMediaAsset {
  const resources = product?.resources || []
  const focus = resources.find((item) => item.resource_type === 'PARTNER_RESOURCE')
    || resources.find((item) => item.resource_type === 'PUBLIC_REFERENCE')
    || resources.find((item) => item.resource_type === 'HOTEL_SERVICE' && !includesAny(item.resource_name, ['行李寄存', '办理入住', '办理退房']))
    || resources.find((item) => item.resource_type === 'ROOM')
  return focus ? mediaForResource(product, focus) : mediaForProduct(product)[0] || MEDIA_LIBRARY.hangzhou
}

/** Use a related second frame in the itinerary when the catalog has one. */
export function highlightMediaForResource(product: ProductMediaInput | null | undefined, resource: ProductResource | undefined, index = 0): ProductMediaAsset {
  const candidates = mediaCandidatesForResource(product, resource, index)
  const primary = primaryProductMedia(product)
  const alternatives = candidates.filter((asset) => asset.id !== primary.id && asset.url !== primary.url)
  return alternatives[index % Math.max(alternatives.length, 1)] || mediaForResource(product, resource, index)
}

export function itineraryMediaForResource(product: ProductMediaInput | null | undefined, resource: ProductResource | undefined, index = 0): ProductMediaAsset {
  const candidates = mediaCandidatesForResource(product, resource, index)
  const primary = mediaForResource(product, resource)
  const alternatives = candidates.filter((asset) => asset.id !== primary.id && asset.url !== primary.url)
  const name = String(resource?.resource_name || '')
  const isPottery = resource?.resource_type === 'PARTNER_RESOURCE' && includesAny(name, ['陶艺', '陶杯', '陶瓷'])
  const variant = isPottery && alternatives.length > 1 ? alternatives.length - 1 : index % Math.max(alternatives.length, 1)
  return alternatives.length ? alternatives[variant] : primary
}

export function experienceMoments(product?: ProductMediaInput | null): ProductMoment[] {
  if (!product) return []
  const chosen: ProductMoment[] = []
  const usedUrls = new Set<string>()
  product.resources.forEach((resource, index) => {
    const candidates = mediaCandidatesForResource(product, resource, index)
    const media = candidates.find((candidate) => !usedUrls.has(candidate.url)) || candidates[0]
    if (media && chosen.length < 6) {
      chosen.push({ media, resource_name: resource.resource_name, resource_type: resource.resource_type })
      usedUrls.add(media.url)
    }
  })
  return chosen
}

export { MEDIA_LIBRARY }
