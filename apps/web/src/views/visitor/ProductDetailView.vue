<script setup lang="ts">
import { posterSvgDataUri } from '../../utils/posterSvg'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { hotelApi, visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import MediaImage from '../../components/MediaImage.vue'
import ProductCard from '../../components/ProductCard.vue'
import VisitorAssistant from '../../components/VisitorAssistant.vue'
import type { MarketingAsset, TravelProduct } from '../../types'
import { experienceLabelZh, experienceMoments, heroMedia, mediaForProduct, mediaForResource } from '../../utils/productMedia'
import { publicTravelCopy } from '../../utils/publicTravelCopy'
import { loadVisitorProfile, saveVisitorProfile, type VisitorProfile, visitorConversationId } from '../../utils/visitorProfile'
import { useCountdown } from '../../utils/countdown'

const route = useRoute()
const router = useRouter()
const previewMode = computed(() => route.query.preview === '1')
const embeddedMode = computed(() => route.query.embedded === '1')
const product = ref<TravelProduct | null>(null)
const loading = ref(true)
const question = ref('')
const chats = ref<Array<{ user?: string; answer?: string; suggestions?: TravelProduct[]; follow_up_questions?: string[] }>>([])
const consultLoading = ref(false)
const intentDialog = ref(false)
const intentLoading = ref(false)
const posterDialog = ref(false)
const assistantOpen = ref(false)
const assistantMinimized = ref(false)
const targetDateLabel = computed(() => {
  const value = String(product.value?.target_date || '')
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${Number(match[2])}月${Number(match[3])}日` : '日期待选'
})
const favorite = ref(false)
const guides = ref<Array<Record<string, any>>>([])
const form = reactive({ natural_language: '', contact_name: '', contact_phone: '' })
const intentParsed = ref(false)
const intentNeeds = reactive<VisitorProfile>({
  natural_language: '', target_date: null, weather: 'RAIN', target_crowd: 'FAMILY', adult_count: 2,
  child_count: 0, child_ages: [], budget: '700', interests: [], negative_interests: [], activity_level: 'MEDIUM',
  requested_places: [], dietary_restrictions: [], allergy_information: '', arrival_time: null,
  preferred_experience_time: null, other_requirements: ''
})

const gallery = computed(() => experienceMoments(product.value))
const resourceCount = computed(() => product.value?.resources.length || 0)
// The length of stay belongs to the product itself, so the page only reports
// the bound stay instead of letting a visitor re-schedule it.
const nights = ref(1)
const stay = computed(() => product.value?.stay || null)
const stayLabel = computed(() => stay.value?.label || '2天1晚')
const stayPrice = computed(() => String(stay.value?.price || product.value?.suggested_price || ''))
const stayOptions = computed(() => stay.value?.options || [])
const dayPlan = computed(() => product.value?.day_plan || [])
const alternatives = ref<{ room_types: Array<Record<string, any>>; same_room_packages: Array<Record<string, any>> }>({ room_types: [], same_room_packages: [] })
const roomOptions = ref<Array<Record<string, any>>>([])
const dateOptions = ref<Array<Record<string, any>>>([])
const selectedRoomId = ref<number | null>(null)
// 支持用 ?room=<room_inventory_id> 直接打开某个房型（分享链接 / 刷新后保持）。
if (route.query.room) {
  const roomFromQuery = Number(route.query.room)
  if (Number.isFinite(roomFromQuery) && roomFromQuery > 0) selectedRoomId.value = roomFromQuery
}
const roomSwitching = ref(false)
const soldOut = computed(() => !previewMode.value && Number(product.value?.sale_quantity || 0) <= 0)
const roomFeatures = computed(() => {
  const room = product.value?.resources.find((item) => item.resource_type === 'ROOM')
  return String(room?.description || '')
})
const photoResource = computed(() => product.value?.resources.find((item) => /旅拍|摄影|拍照/.test(`${item.resource_name} ${item.description || ''}`)))
const related = ref<TravelProduct[]>([])
const countdown = useCountdown(() => product.value?.target_date)
const routePlan = computed(() => product.value?.route_plan || [])
const activeRouteDay = ref(1)
watch(routePlan, (value) => {
  if (value.length && !value.some((day) => day.day_index === activeRouteDay.value)) {
    activeRouteDay.value = value[0].day_index
  }
})
// A dense paragraph is hard to read on a phone, so the story is split into
// sentence-sized paragraphs.
const storyParagraphs = computed(() =>
  String(story.value || '')
    .split(/(?<=。)/)
    .map((part) => part.trim())
    .filter((part) => part.length > 4),
)
const stayRange = computed(() => {
  const plan = stay.value
  if (!plan?.check_in || !plan?.check_out) return String(product.value?.target_date || '')
  return `${plan.check_in} 入住 · ${plan.check_out} 退房`
})
const crowdLabel = computed(() => ({ FAMILY: '亲子出行', COUPLE: '双人同游', FRIENDS: '好友相聚', SOLO: '一个人慢游' } as Record<string, string>)[String(product.value?.target_crowd || '')] || '城市旅行')
const socialLines = computed(() => String(social.value?.content || '').split('\n').map((line) => line.trim()).filter(Boolean).slice(0, 6))
const poster = computed(() => product.value?.marketing_assets?.find((asset) => asset.asset_type === 'POSTER'))
const social = computed(() => product.value?.marketing_assets?.find((asset) => asset.asset_type === 'SOCIAL_POST'))
const heroIndex = ref(0)
// 当前房型的实拍主图排在最前：切换房型时第一张图会立刻换成该房型，
// 图库与亮点内容也随 product 一起刷新，不需要整页重载。
const heroMediaList = computed(() => {
  const list = mediaForProduct(product.value)
  const room = product.value?.resources.find((item) => item.resource_type === 'ROOM')
  if (!room) return list
  const roomMedia = mediaForResource(product.value, room)
  return [roomMedia, ...list.filter((item) => item.id !== roomMedia.id)]
})
const hero = computed(() => heroMediaList.value[heroIndex.value] || heroMediaList.value[0] || heroMedia(product.value))
const heroTotal = computed(() => Math.max(1, heroMediaList.value.length))
function moveHero(delta: number) {
  heroIndex.value = (heroIndex.value + delta + heroTotal.value) % heroTotal.value
}
// 触摸左右滑动切图（保留两侧箭头按钮）。
let touchStartX = 0
let touchStartY = 0
let touchStartAt = 0
function onSwipeStart(event: TouchEvent) {
  const point = event.changedTouches[0]
  touchStartX = point.clientX
  touchStartY = point.clientY
  touchStartAt = Date.now()
}
function onSwipeEnd(event: TouchEvent) {
  if (!touchStartAt) return
  const point = event.changedTouches[0]
  const dx = point.clientX - touchStartX
  const dy = point.clientY - touchStartY
  touchStartAt = 0
  if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return
  moveHero(dx < 0 ? 1 : -1)
}
// 顶部章节导航：滚动时高亮当前所在的板块（scroll-spy），而不是固定高亮第一个。
const anchorSections = [
  { id: 'highlights', label: '特色' },
  { id: 'itinerary', label: '行程' },
  { id: 'fees', label: '费用' },
  { id: 'notice', label: '须知' },
  { id: 'guides', label: '参考路线' },
  { id: 'reviews', label: '评价' },
]
const activeSection = ref('highlights')
function updateAnchorFromScroll() {
  if (!product.value) return
  let current = anchorSections[0].id
  for (const { id } of anchorSections) {
    const element = document.getElementById(id)
    if (!element) continue
    // 顶部固定条（页头 62px + 章节条约 44px）大约占用 120px。
    if (element.getBoundingClientRect().top - 120 <= 0) current = id
  }
  activeSection.value = current
}
function setupAnchorSpy() {
  window.removeEventListener('scroll', updateAnchorFromScroll)
  window.addEventListener('scroll', updateAnchorFromScroll, { passive: true })
  updateAnchorFromScroll()
}
function scrollToSection(id: string) {
  const element = document.getElementById(id)
  if (!element) return
  activeSection.value = id
  const top = element.getBoundingClientRect().top + window.scrollY - 104
  window.scrollTo({ top, behavior: 'smooth' })
}

// 可住人数取自客房本身（max_guests），不再用同行人数，避免「最多 2 人」和房型「可住 3 人」打架。
const roomMaxGuests = computed(() => {
  const current = roomOptions.value.find((item) => item.room_inventory_id === (product.value?.room_inventory_id || null))
  return Number(current?.max_guests || product.value?.party_size || 2)
})
// The formatted SVG is the share asset: it reserves dedicated space for the
// route and title.  A Wan image remains the product hero, not a substitute
// that can hide text in a sharing preview.
const posterVisual = computed(() => poster.value?.poster_svg ? posterSvgDataUri(poster.value.poster_svg) : (poster.value?.image_url || ''))
const FILLER_COPY = /不用把一天排满|把这段体验慢慢安排进你的杭州行程|把杭州的一段时光留给今天|把这段杭州时光留给周末|住进杭州，慢慢体验这座城市的另一面/i

function usefulCopy(value: unknown, fallback = '') {
  const text = publicTravelCopy(value, '')
  if (!text) return fallback
  const segments = text.match(/[^。！？!?]+[。！？!?]?/g) || []
  const useful = segments.filter((segment) => !FILLER_COPY.test(segment)).join('').trim()
  return useful.length >= 6 ? useful : fallback
}

const roomResource = computed(() => product.value?.resources.find((item) => item.resource_type === 'ROOM'))
// 影音会员这类是房型特色，不计入「体验」，也不算进行程安排。
const ROOM_FEATURE_WORDS = ['影音', '会员', '电影', '投影', '桌游', '迷你吧']
function isRoomFeature(name?: string | null) {
  return ROOM_FEATURE_WORDS.some((word) => String(name || '').includes(word))
}
const experienceResources = computed(
  () => product.value?.resources.filter((item) => item.resource_type !== 'ROOM' && !isRoomFeature(item.resource_name)) || [],
)
const roomFeatureNames = computed(() => {
  const names = (product.value?.resources || [])
    .filter((item) => item.resource_type === 'HOTEL_SERVICE' && isRoomFeature(item.resource_name))
    .map((item) => item.resource_name)
  return names.length ? [...new Set(names)].join('、') + '（房型自带，晚上回房使用）' : ''
})
const addressList = computed(() => {
  const values = product.value?.resources.map((item) => item.address).filter(Boolean) || []
  return [...new Set(values.map((item) => String(item)))]
})
const addressSummary = computed(() => addressList.value.join('、') || String(stay.value?.hotel_address || '酒店地址待补充'))
const packageItems = computed(() => product.value?.resources.map((item) => item.resource_name).filter(Boolean).join('、') || '住宿与在地体验')
// The stay is listed separately with its night count, so the fee list shows
// only the experience and hotel-service lines to avoid duplicating the room.
const feeResources = computed(() => (product.value?.resources || []).filter((item) => item.resource_type !== 'ROOM'))
const earliestExperience = computed(() => {
  const item = [...experienceResources.value].filter((resource) => resource.start_time).sort((a, b) => String(a.start_time).localeCompare(String(b.start_time)))[0]
  return item?.start_time ? item.start_time.slice(0, 5) : ''
})
const transportHint = computed(() => {
  const address = addressSummary.value
  if (/西湖|湖滨/.test(address)) return `建议导航至“${address}”，周末从龙翔桥站方向前往，至少预留 30 分钟。`
  if (/运河|拱宸桥/.test(address)) return `建议导航至“${address}”，可从拱宸桥东站换乘步行或打车抵达。`
  if (/良渚/.test(address)) return `建议导航至“${address}”，地铁 2 号线良渚站方向更方便。`
  if (/湘湖/.test(address)) return `建议导航至“${address}”，地铁 1 号线湘湖站方向更方便。`
  return `直接导航至“${address}”，按页面行程顺序抵达各体验点。`
})
const guideQuery = computed(() => {
  if (!product.value) return '杭州旅行'
  // 参考路线跟着这套产品实际的体验地点走，而不是泛泛地搜「杭州」。
  const names = experienceResources.value.slice(0, 3).map((item) => item.resource_name).filter(Boolean)
  const places = addressList.value.slice(0, 2)
  return [product.value.theme, ...names, ...places].filter(Boolean).join(' ').slice(0, 110)
})
const publicTitle = computed(() => {
  const theme = product.value?.theme || '杭州周末体验'
  const names = experienceResources.value.slice(0, 2).map((item) => item.resource_name).filter(Boolean).join('、')
  return usefulCopy(product.value?.marketing_title || product.value?.marketing_content, `${crowdLabel.value} · ${names || theme}，含住宿与现场服务。`)
})
const story = computed(() => {
  const theme = product.value?.theme || '杭州周末体验'
  const room = roomResource.value?.resource_name || '舒适客房'
  const names = experienceResources.value.slice(0, 3).map((item) => item.resource_name).filter(Boolean).join('、') || '在地体验'
  const place = addressList.value[0] || '杭州城内'
  const fallback = `以“${theme}”为主线，住进${room}，前往${place}完成${names}。套餐把住宿、到店时间和体验地点排在一起，到了杭州照着顺序走即可。`
  return usefulCopy(product.value?.marketing_content, fallback)
})
// Ratings and review text are stored per product; an unreviewed line shows no
// score instead of a fixed marketing number.
const reviews = computed(() => product.value?.reviews || [])
const ratingAverage = computed(() => {
  const value = product.value?.rating_average
  return value === undefined || value === null || value === '' ? '—' : Number(value).toFixed(1)
})
const ratingCount = computed(() => Number(product.value?.rating_count || 0))
const recommendationNote = computed(() => {
  const time = earliestExperience.value ? `首个体验安排在 ${earliestExperience.value}` : '体验时间按行程卡片安排'
  return `${time}；集合地点为${addressSummary.value}。${crowdLabel.value}可按页面路线前往。`
})
const reviewEntries = computed(() => {
  const first = experienceResources.value[0]?.resource_name || '核心体验'
  const second = experienceResources.value[1]?.resource_name || '酒店服务'
  const place = addressList.value[0] || '酒店内'
  return [
    { title: '行程顺，信息很清楚', meta: `${crowdLabel.value} · 近期评价`, content: `从${place}开始，${first}的时间和地址都写得很具体，抵达后按顺序体验即可。` },
    { title: '内容和住宿一次安排', meta: `套餐体验 · 5.0 分`, content: `${second}和住宿放在同一组商品里，沟通成本低；建议提前确认停车、集合入口和儿童需求。` },
  ]
})

function resourceSummary(item: TravelProduct['resources'][number]) {
  const description = usefulCopy(item.description, '')
  if (description) return description
  const place = item.address || (item.resource_type === 'ROOM' || item.resource_type === 'HOTEL_SERVICE' ? '酒店内' : '杭州')
  const time = item.start_time && item.end_time ? `，${item.start_time.slice(0, 5)}–${item.end_time.slice(0, 5)}` : ''
  if (item.resource_type === 'ROOM') return `${item.resource_name}含一晚住宿，${item.quantity_per_package}间；早到时先在前台寄存行李，再按行程参加体验。`
  if (item.resource_type === 'HOTEL_SERVICE') return `${item.resource_name}在酒店内使用${time || '，按当天行程安排'}，到店后向前台报商品名称即可。`
  return `${item.resource_name}位于${place}${time}，现场由工作人员引导完成，建议提前 10 分钟抵达。`
}

function resourceMeta(item: TravelProduct['resources'][number]) {
  const place = item.address || (item.resource_type === 'ROOM' || item.resource_type === 'HOTEL_SERVICE' ? '酒店内' : '杭州')
  const time = item.start_time && item.end_time ? item.start_time.slice(0, 5) + ' – ' + item.end_time.slice(0, 5) : '按当日行程安排'
  return place + ' · ' + time
}

function itineraryTime(item: TravelProduct['resources'][number], index: number) {
  if (item.start_time && item.end_time) return `${item.start_time.slice(0, 5)} – ${item.end_time.slice(0, 5)}`
  if (item.resource_type === 'ROOM') return index === 0 ? '15:00 后办理入住' : '次日 12:00 前退房'
  if (item.resource_type === 'HOTEL_SERVICE') return '按当天行程在酒店内使用'
  return '按行程顺序参加体验'
}

function itineraryAction(item: TravelProduct['resources'][number]) {
  if (item.resource_type === 'ROOM') return `办理入住 · ${item.resource_name}含一晚住宿`
  if (item.resource_type === 'HOTEL_SERVICE') return `酒店内使用 · 向前台报${item.resource_name}`
  return item.address ? `抵达 ${item.address} · 提前 10 分钟签到` : '按行程卡片中的地址抵达体验点'
}

async function load() {
  loading.value = true
  try { product.value = (previewMode.value
      ? await hotelApi.product(Number(route.params.id))
      : await visitorApi.product(Number(route.params.id), nights.value, selectedRoomId.value)).data
    guides.value = (await visitorApi.guides(guideQuery.value, addressList.value.join(' '))).data
    if (!previewMode.value) {
      alternatives.value = (await visitorApi.productAlternatives(Number(route.params.id))).data
      const sameDay = await visitorApi.products({ target_date: product.value?.target_date, compact: true })
      related.value = sameDay.data.filter((item) => item.id !== product.value?.id).slice(0, 4)
      roomOptions.value = (await visitorApi.productRooms(Number(route.params.id))).data.rooms
      try { dateOptions.value = (await visitorApi.productDates(Number(route.params.id))).data.dates } catch { dateOptions.value = [] }
    } else {
      alternatives.value = { room_types: [], same_room_packages: [] }
      related.value = []
      roomOptions.value = []
      dateOptions.value = []
    }
  }
  catch (e) { showToast(errorMessage(e)) }
  finally { loading.value = false }
}

async function chooseRoom(option: Record<string, any>) {
  if (!option.available) { showToast('该房型当天已售完，请选择其他房型'); return }
  if (option.room_inventory_id === (product.value?.room_inventory_id || null)) return
  selectedRoomId.value = Number(option.room_inventory_id)
  roomSwitching.value = true
  try {
    // Only the product payload is replaced, so the page keeps its scroll
    // position and never flashes the loading state.
    product.value = (await visitorApi.product(Number(route.params.id), nights.value, selectedRoomId.value)).data
    // 主图回到第一张，正好是刚切换到的房型实拍图。
    heroIndex.value = 0
    void router.replace({ query: { ...route.query, room: String(option.room_inventory_id) } })
    showToast(`已切换到${option.room_type}，房型、行程、费用与须知已同步更新`)
  } catch (e) { showToast(errorMessage(e)) }
  finally { roomSwitching.value = false }
}

function chooseDate(option: Record<string, any>) {
  if (option.id === product.value?.id) return
  selectedRoomId.value = null
  void router.push(`/visitor/products/${option.id}`)
}

function openProduct(id: number) {
  void router.push(`/visitor/products/${id}`)
}

function selectNights(value: number) {
  const option = stayOptions.value.find((item) => item.nights === value)
  if (option && !option.available) { showToast(`该房型连续 ${value} 晚房态不足，已按可售晚数展示`); return }
  if (nights.value === value) return
  nights.value = value
  void load()
}

async function consult() {
  if (!question.value.trim() || !product.value) return
  const text = question.value.trim(); question.value = ''; chats.value.push({ user: text }); consultLoading.value = true
  try {
    const response = await visitorApi.consult({ product_id: product.value.id, question: text, weather: product.value.weather, conversation_id: visitorConversationId() })
    chats.value.push({ answer: String(response.data.answer || ''), suggestions: (response.data.suggestions as TravelProduct[]) || [], follow_up_questions: (response.data.follow_up_questions as string[]) || [] })
  } catch (e) { showToast(errorMessage(e)) }
  finally { consultLoading.value = false }
}

async function copySocial() {
  if (!social.value?.content) return
  try { await navigator.clipboard.writeText(social.value.content); showToast('旅行灵感文案已复制') }
  catch { showToast('复制失败，请手动选择文案') }
}

function downloadPoster(asset?: MarketingAsset) {
  if (!asset?.poster_svg) return
  const url = URL.createObjectURL(new Blob([asset.poster_svg], { type: 'image/svg+xml;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = `${asset.title || product.value?.product_name || 'stayscape-poster'}.svg`; link.click(); URL.revokeObjectURL(url)
}

function syncIntentAges() {
  const count = Math.max(0, Number(intentNeeds.child_count) || 0)
  intentNeeds.child_ages = intentNeeds.child_ages.slice(0, count)
  while (intentNeeds.child_ages.length < count) intentNeeds.child_ages.push(6)
}

function applyIntentNeeds(data: Record<string, any>) {
  const arrayFields = ['interests', 'negative_interests', 'requested_places', 'dietary_restrictions']
  Object.keys(intentNeeds).forEach((key) => {
    if (key === 'natural_language' || data[key] === undefined) return
    ;(intentNeeds as any)[key] = arrayFields.includes(key) ? (Array.isArray(data[key]) ? data[key].map(String) : []) : data[key]
  })
  intentNeeds.target_date = product.value?.target_date || intentNeeds.target_date
  intentNeeds.weather = product.value?.weather || intentNeeds.weather
  intentNeeds.target_crowd = product.value?.target_crowd || intentNeeds.target_crowd
  syncIntentAges()
}

async function parseIntent() {
  if (!form.natural_language.trim()) { showToast('先写一句同行与注意事项，例如“一家四口，孩子6岁和9岁”'); return false }
  try {
    const response = await visitorApi.interpret({ natural_language: form.natural_language.trim() })
    applyIntentNeeds(response.data.interpreted_needs)
    intentNeeds.natural_language = form.natural_language.trim()
    intentParsed.value = true
    return true
  } catch (e) { showToast(errorMessage(e)); return false }
}

function openIntent() {
  intentDialog.value = true
}

async function submitIntent() {
  if (!product.value) return
  if (!form.contact_name.trim() || !form.contact_phone.trim()) { showToast('请填写联系人和联系电话'); return }
  intentLoading.value = true
  try {
    const partySize = Number(product.value.party_size || 2)
    const response = await visitorApi.intent({
      product_id: product.value.id,
      room_inventory_id: product.value.room_inventory_id,
      natural_language: form.natural_language.trim(),
      structured_confirmed: true,
      adult_count: partySize,
      child_count: 0,
      child_ages: [],
      budget: product.value.suggested_price,
      interests: [],
      negative_interests: [],
      activity_level: 'MEDIUM',
      dietary_restrictions: [],
      allergy_information: '',
      other_requirements: form.natural_language.trim(),
      contact_name: form.contact_name.trim(),
      contact_phone: form.contact_phone.trim(),
      conversation_id: visitorConversationId(),
    })
    product.value.sale_quantity = Number(response.data.remaining_quantity ?? Math.max(product.value.sale_quantity - 1, 0))
    product.value.status = String(response.data.product_status || product.value.status)
    showToast('订单已提交，酒店会尽快与你联系确认。')
    intentDialog.value = false
  } catch (e) { showToast(errorMessage(e)) }
  finally { intentLoading.value = false }
}

onMounted(load)
watch(product, (value, previous) => {
  if (value && (value.id !== previous?.id || value.room_inventory_id !== previous?.room_inventory_id)) {
    void nextTick(setupAnchorSpy)
  }
})
watch(() => String(route.params.id || ''), (id, previous) => {
  if (id && id !== previous) { heroIndex.value = 0; void load() }
})
// 从旅居助手的「可换房型」链接进来（或同一页只改 ?room=）时切换房型。
watch(() => String(route.query.room || ''), async (value) => {
  const roomId = Number(value)
  if (!Number.isFinite(roomId) || roomId <= 0) return
  if (!product.value || roomId === product.value.room_inventory_id) return
  selectedRoomId.value = roomId
  roomSwitching.value = true
  try {
    product.value = (await visitorApi.product(Number(route.params.id), nights.value, roomId)).data
    heroIndex.value = 0
  } catch (e) { showToast(errorMessage(e)) }
  finally { roomSwitching.value = false }
})
onBeforeUnmount(() => window.removeEventListener('scroll', updateAnchorFromScroll))
</script>

<template>
  <div v-if="loading" class="detail-loading"><span /> 正在打开这段杭州体验…</div>
  <div v-else-if="product" class="visitor-product-detail" :class="{ 'is-embedded-preview': embeddedMode }">
    <div v-if="previewMode && !embeddedMode" class="preview-mode-banner"><b>游客端效果预览</b><router-link to="/hotel/products/generate">返回产品方案</router-link></div>
    <section class="product-detail-hero" @touchstart.passive="onSwipeStart" @touchend.passive="onSwipeEnd">
      <MediaImage :media="hero" aspect="hero" eager />
      <div class="product-detail-hero__veil" />
      <router-link v-if="!embeddedMode" :to="previewMode ? '/hotel/products/generate' : '/visitor/products'" class="back-to-list">{{ previewMode ? '← 返回方案' : '← 返回体验列表' }}</router-link>
      <div v-if="!previewMode" class="hero-actions" aria-label="商品操作">
        <button type="button" :aria-label="favorite ? '取消收藏' : '收藏商品'" @click.stop="favorite = !favorite">{{ favorite ? '♥' : '♡' }}</button>
        <button type="button" aria-label="分享商品" @click.stop="posterDialog = true">分享</button>
      </div>
      <span class="hero-counter">{{ heroIndex + 1 }} / {{ heroTotal }}</span>
      <button v-if="heroTotal > 1" type="button" class="hero-nav hero-nav--prev" aria-label="上一张图片" @click.stop="moveHero(-1)">‹</button>
      <button v-if="heroTotal > 1" type="button" class="hero-nav hero-nav--next" aria-label="下一张图片" @click.stop="moveHero(1)">›</button>
      <div v-if="heroTotal > 1" class="hero-dots" aria-label="选择图片"><button v-for="(_, index) in heroMediaList" :key="index" type="button" :class="{ active: heroIndex === index }" :aria-label="`第 ${index + 1} 张图片`" @click.stop="heroIndex = index"></button></div>
      <div class="product-detail-hero__content">
        <div class="hero-kicker"><span>{{ product.theme || '杭州周末提案' }}</span><i /> <span>{{ crowdLabel }}</span></div>
        <h1>{{ product.product_name }}</h1>
        <p>{{ publicTitle }}</p>
      </div>
      <div class="hero-price"><strong>¥{{ stayPrice }}</strong><span>起 / 套 · {{ stayLabel }} · 可选不同房型</span></div>
    </section>

    <section class="commerce-summary">
      <div class="commerce-head"><div class="commerce-title"><h2>{{ product.product_name }}</h2><p>{{ publicTitle }}</p><div class="commerce-tags"><span>杭州旅居套餐</span><span>{{ crowdLabel }}</span><span>{{ stayLabel }}</span><span>含住宿</span><span>{{ experienceResources.length }}项体验</span></div></div>
      <div class="commerce-price"><strong>¥{{ stayPrice }}</strong><span>起 / 套 · {{ stayLabel }}</span><em>已售 {{ product.sold_quantity ?? 0 }} 套</em></div>
      </div>
      <div class="date-picker-row"><b>出行日期</b><span v-for="d in dateOptions" :key="d.id" :class="['date-chip', { active: d.id === product.id }]" @click="chooseDate(d)"><strong>{{ d.target_date.slice(5) }} {{ d.weekday }}</strong><small>{{ d.sale_quantity > 0 ? `余 ${d.sale_quantity} 席` : '售罄' }}</small></span><span v-if="!dateOptions.length" class="date-chip active"><strong>{{ targetDateLabel }}</strong><small>{{ previewMode ? '预览中' : product.sale_quantity > 0 ? `余 ${product.sale_quantity} 席` : '售罄' }}</small></span><span class="date-note">{{ stayLabel }} · {{ stayRange }}</span></div>
      <div class="date-picker-row"><b>销售倒计时</b><span class="date-note">{{ countdown.expired() ? '本团期已截止销售' : `距结束 ${countdown.remaining()}` }}（{{ product.target_date }} 00:00 截止）</span></div>
    </section>

    <section v-if="soldOut" class="soldout-banner">
      <div><strong>该房型当天已售完</strong><span>同一天还有以下可选房型与搭配，可直接切换。</span></div>
      <div class="soldout-banner__actions">
        <button v-for="item in [...alternatives.room_types, ...alternatives.same_room_packages].filter((row) => row.sale_quantity > 0).slice(0, 3)" :key="item.id" type="button" @click="openProduct(item.id)">
          <b>{{ item.room_type }}</b><span>¥{{ item.price }} · 余 {{ item.sale_quantity }}</span>
        </button>
      </div>
    </section>

    <section v-if="alternatives.room_types.length || alternatives.same_room_packages.length" class="room-choice">
      <div class="room-choice__block" v-if="roomOptions.length">
        <span class="section-kicker">选择房型（同一套餐可换房型）</span>
        <div class="room-choice__options">
          <button v-for="item in roomOptions" :key="item.room_inventory_id" type="button" :class="{ disabled: !item.available, active: item.room_inventory_id === product.room_inventory_id }" @click="chooseRoom(item)">
            <b>{{ item.room_type }}</b><small>{{ item.features || `最多 ${item.max_guests} 人` }}</small>
            <em>¥{{ item.price }}{{ item.available ? ` · 余 ${item.sale_quantity}` : ' · 已售完' }}</em>
          </button>
        </div>
      </div>
      <div class="room-choice__block" v-if="alternatives.same_room_packages.length">
        <span class="section-kicker">同一房型的其他搭配</span>
        <div class="room-choice__options">
          <button v-for="item in alternatives.same_room_packages" :key="item.id" type="button" :class="{ disabled: item.sale_quantity <= 0 }" @click="item.sale_quantity > 0 && openProduct(item.id)">
            <b>{{ item.experiences.slice(0, 2).join('、') || item.theme }}</b><small>{{ item.room_type }} · {{ item.stay_label }}</small>
            <em>¥{{ item.price }}{{ item.sale_quantity > 0 ? ` · 余 ${item.sale_quantity}` : ' · 已售完' }}</em>
          </button>
        </div>
      </div>
    </section>
    <nav class="detail-anchor-nav" aria-label="商品章节导航"><button v-for="item in anchorSections" :key="item.id" type="button" :class="{ active: activeSection === item.id }" @click="scrollToSection(item.id)">{{ item.label }}</button></nav>
    <section class="trip-strip">
      <div><span>入住 / 退房</span><strong>{{ stayRange }}</strong></div>
        <div><span>适合谁去</span><strong>{{ crowdLabel }} · {{ product.party_size }} 人</strong></div>
      <div><span>套餐包含</span><strong>{{ stayLabel }} · {{ resourceCount }} 项内容</strong></div>
    </section>

    <main class="detail-content" :key="`detail-${product.id}-${product.room_inventory_id}`">
      <section id="highlights" class="commerce-highlight"><div class="section-heading"><div><span class="section-kicker">特色</span><h2>这趟体验包含什么</h2></div></div><div class="highlight-grid"><article v-for="(item,index) in product.resources.slice(0,6)" :key="item.id"><MediaImage :media="mediaForResource(product,item,index)" aspect="card"/><h3>{{ item.resource_name }}</h3><p>{{ resourceSummary(item) }}</p></article></div></section><section class="compact-story">
        <div class="section-heading">
          <div><span class="section-kicker">这趟的亮点</span><h2>{{ product.theme || '一段刚刚好的杭州时光' }}</h2></div>
          <span class="section-count">01</span>
        </div>
        <p v-for="(paragraph, index) in storyParagraphs" :key="index" class="story-lead">{{ paragraph }}</p>
        <div class="story-tags"><span>{{ crowdLabel }}</span><span>{{ product.target_date }}</span><span>杭州周末</span></div>
        <template v-if="product.detail_sections">
          <div v-if="product.detail_sections.experience_details.length" class="experience-details">
            <article v-for="item in product.detail_sections.experience_details" :key="item.name">
              <header><strong>{{ item.name }}</strong><span>{{ item.time }}<template v-if="item.duration"> · {{ item.duration }}</template></span></header>
              <p>{{ item.feature }}</p>
              <ul>
                <li><b>地点</b>{{ item.address }}</li>
                <li><b>费用</b>{{ item.included }}；{{ item.extra_cost }}</li>
                <li><b>注意</b>{{ item.tips }}</li>
                <li v-if="item.source_note"><b>参考</b>{{ item.source_note }}</li>
              </ul>
            </article>
          </div>
          <div class="detail-extra">
            <div>
              <span class="section-kicker">花费</span>
              <p v-for="(line, index) in product.detail_sections.spend_notes" :key="index">{{ line }}</p>
            </div>
            <div>
              <span class="section-kicker">出行建议</span>
              <p v-for="(line, index) in product.detail_sections.tips" :key="index">{{ line }}</p>
            </div>
          </div>
        </template>
      </section>

      <section id="itinerary" class="itinerary-section">
        <div class="section-heading">
          <div><span class="section-kicker">行程</span><h2>{{ stayLabel }}行程安排</h2></div>
          <span class="section-count">02</span>
        </div>
        <div v-if="dayPlan.length" class="day-plan-list">
          <article v-for="day in dayPlan" :key="day.day_index" class="day-plan">
            <header class="day-plan__head">
              <div><span class="day-plan__label">{{ day.label }}</span><strong>{{ day.title }}</strong></div>
              <small>{{ day.date || product.target_date }}</small>
            </header>
            <p class="day-plan__summary">{{ day.summary }}</p>
            <ol class="day-plan__items">
              <li v-for="(entry, index) in day.items" :key="index">
                <span class="day-plan__time"><b>{{ entry.slot_label || '行程安排' }}</b>{{ entry.time || '按行程顺序体验' }}</span>
                <div>
                  <b>{{ entry.title }}</b>
                  <p>{{ entry.description }}</p>
                  <div class="day-plan__meta">
                    <span v-if="entry.duration_text">{{ entry.duration_text }}</span>
                    <span v-if="entry.address">{{ entry.address }}</span>
                    <span v-if="entry.notes" class="day-plan__note">注意：{{ entry.notes }}</span>
                  </div>
                </div>
              </li>
            </ol>
          </article>
        </div>
        <div v-else class="itinerary-list">
          <article v-for="(item, index) in product.resources" :key="item.id" class="itinerary-card">
            <div class="itinerary-card__image"><MediaImage :media="mediaForResource(product, item, index)" aspect="card" /></div>
            <div class="itinerary-card__body">
              <div class="itinerary-card__top"><span>{{ experienceLabelZh(item.resource_type) }}</span><b>第 {{ index + 1 }} 段</b></div>
              <h3>{{ item.resource_name }}</h3>
              <p>{{ resourceSummary(item) }}</p>
              <strong class="itinerary-card__time">{{ itineraryTime(item, index) }}</strong>
              <small>{{ itineraryAction(item) }} · {{ resourceMeta(item) }}</small>
            </div>
            <strong class="itinerary-card__quantity">×{{ item.quantity_per_package }}</strong>
          </article>
        </div>
      </section>

      <section id="fees" class="fee-section"><div class="section-heading"><div><span class="section-kicker">费用</span><h2>费用说明</h2></div></div><div class="fee-columns"><div><h3>费用包含</h3><p>✓ {{ stay?.room_name || '酒店住宿' }} × {{ stay?.nights || 1 }} 晚<small>{{ stayRange }}</small></p><p v-for="item in feeResources" :key="'in'+item.id">✓ {{ item.resource_name }} ×{{ item.quantity_per_package }}<small>{{ resourceMeta(item) }}</small></p><p>✓ 酒店服务与现场引导</p></div><div><h3>费用不含</h3><p>× 往返交通与停车费用</p><p>× 套餐外的餐饮和个人消费</p><p>× 超出套餐数量的加购项目</p></div></div></section><section id="notice" class="notice-section"><div class="section-heading"><div><span class="section-kicker">须知</span><h2>购买须知</h2></div></div><div class="notice-list"><p>适合人群：{{ crowdLabel }}；套餐包含 {{ packageItems }}。</p><p>入住与退房：{{ stayRange }}；{{ stay?.check_in_time || '15:00' }} 后可办理入住，{{ stay?.check_out_time || '12:00' }} 前退房。</p><p>行程天数：{{ stayLabel }}，含 {{ stay?.nights || 1 }} 晚酒店住宿，不提供当天往返的一日游。</p><p>出行日期：{{ product.target_date }}；{{ earliestExperience ? '首项体验 ' + earliestExperience + ' 前抵达' : '按行程卡片安排' }}。</p><p>集合地址：{{ addressSummary }}。</p><p>如何前往：{{ transportHint }}</p><p>天气与改期：户外项目遇雨会调整安排，出发前会再次确认。</p><p>取消规则：出发前 48 小时可申请取消，临近出发的取消申请按平台规则处理。</p></div></section><section class="detail-facts-section"><div class="section-heading"><div><span class="section-kicker">出行信息</span><h2>地址、交通与细节</h2></div><span class="section-count">03</span></div><div class="detail-facts-grid"><div><b>费用包含</b><p>{{ packageItems }}；价格已含页面列出的住宿、体验和现场引导。</p></div><div><b>详细地址</b><p>{{ addressSummary }}。</p></div><div><b>如何前往</b><p>{{ transportHint }}</p></div><div><b>注意事项</b><p>{{ crowdLabel }}出行建议提前确认集合入口，并提前 10 分钟抵达。</p></div></div></section>
      <section class="hotel-detail-section">
        <div class="section-heading"><div><span class="section-kicker">住宿</span><h2>酒店与房型</h2></div></div>
        <div class="hotel-detail-grid">
          <div><span>房型</span><strong>{{ roomResource?.resource_name || '酒店客房' }}</strong></div>
          <div><span>可住人数</span><strong>最多 {{ roomMaxGuests }} 人</strong></div>
          <div class="full"><span>房型细节</span><strong>{{ roomFeatures || '入住标准客房，具体设施见房型介绍' }}</strong></div>
          <div v-if="roomFeatureNames" class="full"><span>房型特色</span><strong>{{ roomFeatureNames }}</strong></div>
          <div><span>入住 / 退房</span><strong>{{ stayRange }}</strong></div>
          <div><span>入住时间</span><strong>{{ stay?.check_in_time || '15:00' }} 后入住 · {{ stay?.check_out_time || '12:00' }} 前退房</strong></div>
        </div>
      </section>

      <section v-if="photoResource" class="photo-detail-section">
        <div class="section-heading"><div><span class="section-kicker">旅拍</span><h2>拍摄安排</h2></div></div>
        <p class="photo-detail-lead">{{ photoResource.description }}</p>
        <ul class="photo-detail-list">
          <li v-for="line in String(photoResource.booking_notice || '').split('；').filter(Boolean)" :key="line">{{ line }}</li>
          <li v-if="!photoResource.booking_notice">拍摄时长、精修张数与机位可在出发前联系商家预约。</li>
        </ul>
      </section>

      <section v-if="guides.length" id="guides" class="guide-source-section">
        <div class="section-heading"><div><span class="section-kicker">公开攻略</span><h2>参考路线与评价</h2></div></div>
        <div class="guide-list">
          <article v-for="guide in guides" :key="guide.source + guide.title">
            <header>
              <strong>{{ guide.title }}</strong>
              <em v-if="guide.duration_minutes">建议停留 {{ guide.duration_minutes }} 分钟</em>
            </header>
            <span class="guide-source-line">{{ guide.source }}<template v-if="guide.area"> · {{ guide.area }}</template><template v-if="guide.category_label"> · {{ guide.category_label }}</template></span>
            <p class="guide-content">{{ guide.content || guide.summary }}</p>
            <ul class="guide-facts">
              <li v-if="guide.address"><b>地址</b>{{ guide.address }}</li>
              <li v-if="guide.opening_hours"><b>开放时间</b>{{ guide.opening_hours }}</li>
              <li v-if="guide.best_time"><b>推荐时段</b>{{ guide.best_time }}</li>
              <li v-if="guide.crowds_label"><b>适合人群</b>{{ guide.crowds_label }}</li>
              <li v-if="guide.reservation_notice"><b>预约提示</b>{{ guide.reservation_notice }}</li>
              <li v-if="guide.transport"><b>怎么去</b>{{ guide.transport }}</li>
            </ul>
            <small v-if="guide.verified_at" class="guide-verified">资料核验时间：{{ String(guide.verified_at).slice(0, 10) }}</small>
          </article>
        </div>
      </section>

      <section id="reviews" class="review-section">
        <div class="section-heading"><div><span class="section-kicker">游客评价</span><h2>真实出行反馈</h2></div><span v-if="ratingCount" class="review-rating">{{ ratingAverage }} 分 · {{ ratingCount }} 条</span></div>
        <div v-if="reviews.length" class="review-list">
          <article v-for="(review, index) in reviews" :key="review.id || index" class="review-card">
            <header><strong>{{ review.author_name || '游客评价' }}</strong><span>{{ review.rating }} 分<template v-if="review.stayed_on"> · 出行日期 {{ review.stayed_on }}</template></span></header>
            <p>{{ review.content || '暂无评价内容' }}</p>
            <div v-if="review.highlights?.length" class="review-highlights"><span v-for="item in review.highlights" :key="item">{{ item }}</span></div>
          </article>
        </div>
        <p v-else class="review-empty">这款产品还没有游客评价。</p>
      </section>

      <section v-if="gallery.length" class="moments-section">
        <div class="section-heading">
          <div><span class="section-kicker">照片</span><h2>现场照片</h2></div>
          <span class="section-count">03</span>
        </div>
        <div class="moments-grid">
          <figure v-for="(moment, index) in gallery" :key="moment.media.id">
            <MediaImage :media="moment.media" aspect="card" />
            <figcaption><span>第 {{ index + 1 }} 段 · {{ experienceLabelZh(moment.resource_type) }}</span><strong>{{ moment.resource_name }}</strong></figcaption>
          </figure>
        </div>
      </section>

      <section v-if="related.length" class="related-section">
        <div class="section-heading"><div><span class="section-kicker">相关推荐</span><h2>同一天的其他方案</h2></div></div>
        <div class="related-grid"><ProductCard v-for="item in related" :key="item.id" :product="item" public-view horizontal /></div>
      </section>

    </main>

    <section v-if="!previewMode" class="booking-bar">
      <div><span class="section-kicker">购买</span><p>提交后等待酒店确认。</p></div>
      <div class="booking-bar__right"><button class="assistant-action" @click="router.push({ path: '/visitor/assistant', query: { product: String(product.id) } })">旅居助手</button><strong>¥{{ stayPrice }}</strong><span>/ 套 · {{ stayLabel }}</span><el-button type="primary" :disabled="product.sale_quantity <= 0" @click="openIntent">立即购买</el-button></div>
    </section>

    <el-dialog v-model="posterDialog" title="分享这段杭州体验" width="min(92vw, 560px)" class="poster-dialog"><img v-if="posterVisual" class="poster-dialog__image" :src="posterVisual" :alt="poster?.title" /><template #footer><el-button @click="posterDialog = false">关闭</el-button><el-button v-if="poster?.poster_svg" type="primary" @click="downloadPoster(poster)">下载 SVG 海报</el-button></template></el-dialog>
    <el-dialog v-model="intentDialog" title="购买信息" width="min(94vw, 520px)"><el-form label-position="top"><el-form-item label="联系人" required><el-input v-model="form.contact_name" placeholder="怎么称呼" /></el-form-item><el-form-item label="联系电话" required><el-input v-model="form.contact_phone" placeholder="便于酒店联系确认" /></el-form-item><el-form-item label="备注"><el-input v-model="form.natural_language" type="textarea" :rows="3" maxlength="300" show-word-limit placeholder="到店时间、同行人或其他需要说明的情况，可以不填" /></el-form-item></el-form><div class="intent-summary"><span>{{ product.product_name }}</span><span>{{ stayLabel }}</span><span>¥{{ stayPrice }}</span></div><template #footer><el-button @click="intentDialog = false">取消</el-button><el-button type="primary" :loading="intentLoading" @click="submitIntent">提交购买</el-button></template></el-dialog>

  </div>
  <div v-else class="home-empty">
    <div class="empty-mark" aria-hidden="true"><svg viewBox="0 0 48 48"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></div>
    <h3>该房型当天已售完</h3>
    <p>同一天的其他房型或体验搭配还有余量，回到列表可以按主题筛选。</p>
    <el-button type="primary" @click="$router.push('/visitor/products')">查看同一天的其他方案</el-button>
  </div>
</template>

<style scoped>
.visitor-product-detail{padding-bottom:86px}.detail-loading{min-height:300px;display:grid;place-items:center;color:var(--muted);font-size:14px}.detail-loading span{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--teal);box-shadow:14px 0 var(--gold),28px 0 var(--teal);margin-right:38px;animation:stay-breathe 1.2s infinite alternate}.product-detail-hero{position:relative;min-height:318px;border-radius:16px;overflow:hidden;background:#173b35;color:#fff}.product-detail-hero>.media-image{position:absolute;inset:0;min-height:100%;border-radius:inherit}.product-detail-hero__veil{position:absolute;inset:0;background:linear-gradient(90deg,rgba(12,39,34,.82),rgba(12,39,34,.2) 75%),linear-gradient(0deg,rgba(12,39,34,.65),transparent 52%)}.back-to-list{position:absolute;z-index:2;top:14px;left:14px;padding:6px 9px;border:1px solid rgba(255,255,255,.42);border-radius:999px;background:rgba(0,0,0,.16);color:#fff;font-size:11px}.product-detail-hero__content{position:absolute;z-index:2;left:5%;right:18%;bottom:30px;max-width:700px}.hero-kicker,.section-kicker{display:inline-flex;align-items:center;gap:8px;color:#23796c;font-size:11px;font-weight:700;letter-spacing:.08em}.hero-kicker{color:rgba(255,255,255,.9)}.hero-kicker i{width:3px;height:3px;border-radius:50%;background:currentColor}.product-detail-hero h1{margin:9px 0 7px;font-size:clamp(27px,3.3vw,40px);line-height:1.13;letter-spacing:-.8px}.product-detail-hero p{max-width:600px;margin:0;color:rgba(255,255,255,.88);font-size:13px;line-height:1.62}.hero-price{position:absolute;z-index:2;right:5%;bottom:29px;text-align:right}.hero-price strong{display:block;font-size:27px;line-height:1;color:#fff}.hero-price span{display:block;margin-top:5px;color:rgba(255,255,255,.78);font-size:10px}.trip-strip{display:grid;grid-template-columns:repeat(3,1fr);margin:10px 0 0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}.trip-strip>div{min-width:0;padding:11px 14px;border-right:1px solid var(--line)}.trip-strip>div:last-child{border-right:0}.trip-strip span{display:block;margin-bottom:4px;color:var(--muted);font-size:10px}.trip-strip strong{display:block;overflow:hidden;color:var(--ink);font-size:13px;text-overflow:ellipsis;white-space:nowrap}.detail-content{max-width:960px;margin:0 auto;padding:26px 3% 14px}.compact-story,.itinerary-section,.moments-section{margin-bottom:26px}.section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:12px}.section-heading h2,.travel-note-heading h2,.share-copy h2,.concierge-header h2{margin:5px 0 0;color:var(--ink);font-family:var(--font-sans);font-size:21px;font-weight:680;line-height:1.22}.section-count{color:#aac8be;font-family:var(--font-mono);font-size:18px;line-height:1}.story-lead{max-width:760px;margin:0;color:var(--ink);font-size:14px;line-height:1.72}.story-note{max-width:720px;margin:8px 0 0;color:var(--muted);font-size:12px;line-height:1.62}.story-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.story-tags span{padding:5px 8px;border-radius:999px;background:#eff7f3;color:#2b7569;font-size:10px}.itinerary-list{display:grid;gap:7px}.itinerary-card{position:relative;display:grid;grid-template-columns:118px minmax(0,1fr) auto;gap:11px;align-items:stretch;min-height:112px;padding:7px;border:1px solid var(--line);border-radius:12px;background:#fff;box-shadow:0 4px 13px rgba(35,64,55,.03)}.itinerary-card__image,.itinerary-card__image .media-image{height:96px;border-radius:8px;overflow:hidden}.itinerary-card__body{min-width:0;padding:1px 0}.itinerary-card__top{display:flex;align-items:center;justify-content:space-between;gap:8px}.itinerary-card__top span{padding:3px 6px;border-radius:999px;background:#edf7f2;color:#287567;font-size:9px;font-weight:700}.itinerary-card__top b{color:#9aafa7;font-size:9px;font-weight:500}.itinerary-card h3{overflow:hidden;margin:5px 0 3px;color:var(--ink);font-size:14px;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}.itinerary-card p{display:-webkit-box;overflow:hidden;margin:0;color:#576963;font-size:11px;line-height:1.48;-webkit-box-orient:vertical;-webkit-line-clamp:2}.itinerary-card small{display:block;overflow:hidden;margin-top:5px;color:#93a19b;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.itinerary-card__quantity{align-self:start;padding:4px 3px 0 0;color:#597a70;font-size:11px}.moments-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.moments-grid figure{margin:0;overflow:hidden;border:1px solid var(--line);border-radius:11px;background:#fff}.moments-grid .media-image{height:148px}.moments-grid figcaption{padding:8px}.moments-grid figcaption span{display:block;overflow:hidden;color:#7e9690;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.moments-grid figcaption strong{display:block;overflow:hidden;margin-top:3px;color:var(--ink);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.travel-note-section{display:grid;grid-template-columns:170px minmax(0,1fr);gap:22px;margin:0 0 24px;padding:17px 18px;border-radius:13px;background:#f0f7f3}.travel-note-heading h2{font-size:19px}.travel-note-heading button{margin-top:9px;padding:0 0 3px;border:0;border-bottom:1px solid #438b7c;background:transparent;color:#317a6d;font-size:11px;cursor:pointer}.travel-note-copy{padding-top:1px}.travel-note-copy p{margin:0;color:#40544d;font-size:12px;line-height:1.6}.travel-note-copy p.first{margin-bottom:5px;color:var(--ink);font-size:14px;font-weight:650}.travel-note-copy p.hashtag{color:#338070;font-size:10px}.share-section{display:grid;grid-template-columns:108px minmax(0,1fr);gap:16px;align-items:center;margin:0 0 24px;padding:12px 14px;border:1px solid var(--line);border-radius:13px;background:#fff}.poster-preview{padding:5px;border:0;border-radius:8px;background:#163d36;box-shadow:0 6px 14px rgba(24,61,54,.16);cursor:pointer}.poster-preview img{display:block;width:100%;height:auto;border-radius:4px}.share-copy h2{font-size:20px}.share-copy p{max-width:560px;margin:7px 0 0;color:var(--muted);font-size:11px;line-height:1.55}.share-actions{display:flex;gap:7px;margin-top:9px}.concierge-section{padding:17px 18px;border:1px solid #d9ebe3;border-radius:13px;background:linear-gradient(135deg,#f5faf7,#eef7f2)}.concierge-header h2{font-size:20px}.concierge-header p{margin:6px 0 0;color:var(--muted);font-size:11px;line-height:1.55}.concierge-quick{display:flex;gap:6px;flex-wrap:wrap;margin:11px 0}.concierge-quick button,.chat-followups button{padding:6px 8px;border:1px solid #cfe4db;border-radius:999px;background:#fff;color:#3a7166;font-size:10px;cursor:pointer}.concierge-chat{display:grid;gap:7px;max-height:230px;overflow:auto;margin:10px 0}.concierge-bubble{max-width:83%;padding:9px 10px;border-radius:5px 11px 11px;background:#fff;color:#3e534c;font-size:11px;line-height:1.55;box-shadow:0 3px 9px rgba(27,77,63,.05)}.concierge-bubble.is-user{justify-self:end;border-radius:11px 5px 11px 11px;background:#dceee7;color:#1f4e43}.chat-suggestions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));margin-top:8px}.chat-suggestions .product-card{background:#fff}.chat-followups{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}.concierge-input{display:flex;gap:7px}.booking-bar{position:sticky;bottom:10px;z-index:11;display:flex;align-items:center;justify-content:space-between;gap:12px;max-width:960px;margin:0 auto;padding:11px 14px;border:1px solid #dce8e2;border-radius:12px;background:rgba(255,255,255,.96);box-shadow:0 8px 24px rgba(33,67,57,.13);backdrop-filter:blur(10px)}.booking-bar p{margin:3px 0 0;color:var(--muted);font-size:11px}.booking-bar__right{display:flex;align-items:center;gap:6px;white-space:nowrap}.booking-bar__right strong{color:#1c685a;font-family:var(--font-mono);font-size:20px}.booking-bar__right span{margin-right:3px;color:var(--muted);font-size:10px}.poster-dialog__image{display:block;width:100%;max-height:72vh;object-fit:contain;margin:0 auto;border-radius:6px;background:#edf4f0}.form-tip{margin-top:7px;color:var(--muted);font-size:12px;line-height:1.6}.intent-summary{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}.intent-summary span{padding:7px 10px;border-radius:999px;background:#edf7f2;color:var(--teal-dark);font-size:12px}.age-row{display:flex;gap:8px;flex-wrap:wrap}.age-row :deep(.el-input-number){width:92px}.safety-callout{margin-top:12px;padding:11px 13px;border-radius:10px;background:#fff8eb;color:#8b6a36;font-size:12px;line-height:1.6}.home-empty{text-align:center;padding:75px 24px;border:1px solid var(--line);background:#fff}.empty-mark{display:grid;place-items:center;width:42px;height:42px;margin:0 auto 14px;border-radius:14px;background:var(--teal);color:#fff;font-family:Georgia,serif;font-size:25px}.home-empty h3{margin:10px 0;color:var(--ink);font-family:Georgia,serif;font-size:24px;font-weight:500}.home-empty p{color:var(--muted);font-size:13px;line-height:1.8}.home-empty .el-button{margin-top:12px}@keyframes stay-breathe{to{transform:translateX(7px);opacity:.5}}@media(max-width:800px){.visitor-product-detail{padding-bottom:76px}.product-detail-hero{min-height:260px;border-radius:12px}.back-to-list{top:10px;left:10px;font-size:10px}.product-detail-hero__content{right:14px;bottom:15px;left:14px}.product-detail-hero h1{margin:7px 0 5px;font-size:25px;letter-spacing:-.5px}.product-detail-hero p{font-size:11px;line-height:1.45}.hero-price{right:13px;bottom:15px}.hero-price strong{font-size:20px}.trip-strip{margin-top:8px;border-radius:10px}.trip-strip>div{padding:8px 7px}.trip-strip span{font-size:9px}.trip-strip strong{font-size:10px}.detail-content{padding:20px 0 10px}.compact-story,.itinerary-section,.moments-section{margin-bottom:22px}.section-heading{margin-bottom:10px}.section-heading h2,.travel-note-heading h2,.share-copy h2,.concierge-header h2{font-size:19px}.section-count{font-size:16px}.story-lead{font-size:13px;line-height:1.62}.story-note{font-size:11px;line-height:1.52}.story-tags{margin-top:8px}.itinerary-list{gap:6px}.itinerary-card{grid-template-columns:86px minmax(0,1fr) 18px;gap:7px;min-height:92px;padding:5px;border-radius:10px}.itinerary-card__image,.itinerary-card__image .media-image{height:80px;border-radius:7px}.itinerary-card__body{padding:1px 0}.itinerary-card__top span{padding:2px 5px;font-size:8px}.itinerary-card h3{margin:4px 0 2px;font-size:13px}.itinerary-card p{font-size:10px;line-height:1.38}.itinerary-card small{margin-top:4px;font-size:8px}.itinerary-card__quantity{padding-top:4px;font-size:10px}.moments-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.moments-grid .media-image{height:110px}.moments-grid figure{border-radius:8px}.moments-grid figcaption{padding:6px}.moments-grid figcaption span{font-size:7px}.moments-grid figcaption strong{margin-top:2px;font-size:9px}.travel-note-section{grid-template-columns:1fr;gap:9px;margin-bottom:20px;padding:13px;border-radius:11px}.travel-note-heading h2{font-size:18px}.travel-note-heading button{margin-top:6px}.travel-note-copy p{font-size:11px;line-height:1.5}.travel-note-copy p.first{font-size:13px}.share-section{grid-template-columns:76px minmax(0,1fr);gap:10px;margin-bottom:20px;padding:10px;border-radius:11px}.share-copy h2{font-size:18px}.share-copy p{font-size:10px;line-height:1.45}.share-actions{gap:5px;margin-top:7px}.share-actions :deep(.el-button){padding:6px 7px;font-size:10px}.concierge-section{padding:13px;border-radius:11px}.concierge-header h2{font-size:18px}.concierge-quick{margin:9px 0}.concierge-quick button{padding:5px 7px;font-size:9px}.concierge-input :deep(.el-input__wrapper){min-height:30px}.concierge-input :deep(.el-button){padding:7px 9px}.booking-bar{position:fixed;right:9px;bottom:9px;left:9px;width:auto;padding:9px 10px;border-radius:10px}.booking-bar p{display:none}.booking-bar__right{gap:4px}.booking-bar__right strong{font-size:16px}.booking-bar__right span{display:none}.booking-bar__right :deep(.el-button){padding:7px 8px;font-size:10px}.poster-dialog__image{max-height:67vh}}@media(max-width:390px){.product-detail-hero h1{font-size:23px}.moments-grid .media-image{height:96px}.itinerary-card{grid-template-columns:80px minmax(0,1fr) 16px}.itinerary-card__image,.itinerary-card__image .media-image{height:74px}.booking-bar__right strong{font-size:14px}}
.product-detail-hero__ai{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.itinerary-card__time{display:block;margin-top:6px;color:var(--teal-dark);font-size:11px;font-weight:650}.chat-suggestions{grid-template-columns:1fr!important;gap:7px}.chat-suggestions .product-card--compact{width:100%}
</style>
<style scoped>
.detail-facts-section,.guide-source-section{margin:0 0 26px}.detail-facts-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.detail-facts-grid>div{padding:14px 16px;background:#fff;border:1px solid var(--line);border-radius:10px}.detail-facts-grid b{font-size:13px;color:var(--teal-dark)}.detail-facts-grid p{margin:7px 0 0;color:#576963;font-size:12px;line-height:1.65}.guide-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.guide-list a{display:grid;gap:6px;padding:13px 14px;background:#f6faf7;border:1px solid #dcebe4;border-radius:10px;color:var(--ink);text-decoration:none}.guide-list a strong{font-size:12px}.guide-list a span{color:var(--muted);font-size:10px;line-height:1.5}
</style>
<style scoped>
.product-detail-hero,.trip-strip,.detail-content,.booking-bar{width:min(960px,100%);max-width:960px;margin-left:auto;margin-right:auto}.product-detail-hero{margin-top:0}.detail-content{box-sizing:border-box}.booking-bar{box-sizing:border-box}.guide-list article{display:grid;gap:6px;padding:13px 14px;background:#f6faf7;border:1px solid #dcebe4;border-radius:10px}.guide-list article p{margin:0;color:#4d625b;font-size:11px;line-height:1.6}.assistant-dialog :deep(.el-dialog__body){padding:0 18px 18px}.assistant-dialog .concierge-section{border:0;background:transparent;padding:0}.assistant-minimize{position:absolute;right:48px;top:18px;border:0;background:transparent;color:#26796a;font-size:12px;cursor:pointer}.chat-suggestions{grid-template-columns:1fr!important}.chat-suggestions .product-card--compact{display:grid;grid-template-columns:96px minmax(0,1fr);width:100%}
</style>
<style scoped>
.commerce-summary{max-width:960px;margin:12px auto 0;padding:16px;background:#fff}.commerce-title h2{margin:0;font-size:22px}.commerce-title p{margin:6px 0;color:var(--muted);font-size:12px}.commerce-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.commerce-tags span{padding:4px 8px;background:#fff3e6;color:#9a6427;font-size:10px}.commerce-stats{display:flex;gap:28px;margin-top:16px}.commerce-stats div{display:grid;gap:3px}.commerce-stats strong{font-size:20px;color:#d56835}.commerce-stats small{color:var(--muted);font-size:10px}.date-picker-row{display:flex;align-items:center;gap:8px;overflow:auto;margin-top:16px;padding-top:12px;border-top:1px solid var(--line)}.date-picker-row>b{white-space:nowrap;font-size:12px}.date-chip{display:grid;min-width:64px;padding:7px 9px;border:1px solid var(--line);text-align:center;cursor:pointer}.date-chip.active{border-color:#1e806d;background:#eaf7f1}.date-chip strong{font-size:12px}.date-chip small{margin-top:3px;color:var(--muted);font-size:9px}.detail-anchor-nav{position:sticky;top:0;z-index:9;display:flex;justify-content:center;gap:34px;max-width:960px;margin:0 auto;padding:12px;background:#fff;border-bottom:1px solid var(--line)}.detail-anchor-nav a{color:var(--muted);font-size:12px;text-decoration:none}.commerce-highlight{margin-bottom:26px}.highlight-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.highlight-grid article{overflow:hidden;background:#fff;border:1px solid var(--line)}.highlight-grid .media-image{height:150px}.highlight-grid h3{margin:10px 12px 4px;font-size:14px}.highlight-grid p{margin:0 12px 12px;color:var(--muted);font-size:11px;line-height:1.55}.fee-section,.notice-section,.review-section{margin-bottom:26px}.fee-columns{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fee-columns>div{padding:14px 16px;background:#fff;border:1px solid var(--line)}.fee-columns h3{margin:0 0 8px;font-size:13px}.fee-columns p,.notice-list p{margin:6px 0;color:#586a63;font-size:12px;line-height:1.6}.notice-list{padding:12px 16px;background:#fff;border:1px solid var(--line)}.review-card{margin-bottom:8px;padding:14px 16px;background:#fff;border:1px solid var(--line)}.review-card div{display:flex;justify-content:space-between;gap:8px}.review-card span{color:#dc8a38;font-size:11px}.review-card p{margin:8px 0 0;color:#586a63;font-size:12px;line-height:1.6}@media(max-width:700px){.commerce-summary,.detail-anchor-nav{width:100%;box-sizing:border-box}.detail-anchor-nav{justify-content:space-around;gap:0}.highlight-grid{grid-template-columns:1fr 1fr}.highlight-grid article:last-child{grid-column:1/-1}.fee-columns{grid-template-columns:1fr}.commerce-stats{gap:18px}}
</style>

<style scoped>
.visitor-product-detail{max-width:960px;margin:0 auto;background:#f6f7f5}.product-detail-hero{border-radius:0 0 14px 14px}.commerce-summary{border-radius:14px;margin-top:8px;box-shadow:0 4px 16px rgba(40,60,50,.06)}.detail-anchor-nav{border-radius:0;box-shadow:0 2px 8px rgba(30,50,40,.04)}.booking-bar{position:fixed;left:50%;bottom:12px;transform:translateX(-50%);width:min(960px,calc(100% - 24px));z-index:30;background:rgba(255,255,255,.97);border-radius:14px;box-shadow:0 8px 28px rgba(25,55,43,.2)}.assistant-action{border:1px solid #1e806d;background:#eaf7f1;color:#1e6b5d;border-radius:8px;padding:8px 11px;font-size:12px;cursor:pointer;white-space:nowrap}.assistant-dialog :deep(.el-dialog){max-width:760px;margin-top:8vh!important}.assistant-dialog :deep(.el-dialog__body){max-height:68vh;overflow:auto}.assistant-dialog .concierge-section{min-height:320px}.chat-suggestions,.chat-suggestions .product-card--compact{display:grid!important;grid-template-columns:96px minmax(0,1fr)!important;width:100%!important;min-width:0}.chat-suggestions .product-card--compact>.media-image{width:96px;min-width:96px;height:100%;min-height:110px}.chat-suggestions .product-card--compact .product-card__body{min-width:0;overflow:hidden}.chat-suggestions .product-card--compact h3,.chat-suggestions .product-card--compact .product-card__hook{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:700px){.visitor-product-detail{width:100%}.commerce-summary{margin-top:6px;padding:13px}.commerce-title h2{font-size:19px}.commerce-stats{gap:16px}.date-picker-row{margin-left:-2px;margin-right:-2px}.detail-anchor-nav{position:sticky;top:0}.detail-content{padding:20px 12px 110px!important}.booking-bar{left:8px;right:8px;bottom:8px;transform:none;width:auto}.assistant-action{padding:7px 8px;font-size:11px}.booking-bar__right strong{font-size:17px}.assistant-dialog :deep(.el-dialog){width:calc(100% - 20px)!important;margin:10vh auto 0!important}.assistant-dialog :deep(.el-dialog__body){max-height:65vh;padding:12px}.assistant-dialog .concierge-section{min-height:0}.chat-suggestions,.chat-suggestions .product-card--compact{grid-template-columns:82px minmax(0,1fr)!important}.chat-suggestions .product-card--compact>.media-image{width:82px;min-width:82px;min-height:96px}}
</style>


<style scoped>
/* Visitor storefront layer: visual hierarchy follows a conventional travel-commerce product page. */
.visitor-product-detail {
  --shop-orange: #ff6a00;
  --shop-orange-soft: #fff4ec;
  --shop-line: #eee9e4;
  --shop-canvas: #f5f5f5;
  width: min(960px, 100%);
  max-width: 960px;
  margin: 0 auto;
  padding-bottom: 124px;
  overflow: hidden;
  background: var(--shop-canvas);
  color: #222;
}

.product-detail-hero {
  width: 100%;
  height: clamp(300px, 42vw, 440px);
  min-height: 300px;
  margin: 0;
  border-radius: 0;
  background: #171717;
}
.product-detail-hero > .media-image,
.product-detail-hero > .product-detail-hero__ai {
  border-radius: 0;
}
.product-detail-hero__veil {
  background: linear-gradient(180deg, rgba(0,0,0,.14), transparent 38%, rgba(0,0,0,.36));
}
.product-detail-hero__content,
.hero-price {
  display: none;
}
.back-to-list {
  top: 16px;
  left: 16px;
  padding: 7px 11px;
  border: 0;
  border-radius: 999px;
  background: rgba(0,0,0,.42);
  color: #fff;
  font-size: 12px;
  backdrop-filter: blur(4px);
}
.hero-actions {
  position: absolute;
  z-index: 3;
  top: 14px;
  right: 16px;
  display: flex;
  gap: 8px;
}
.hero-actions button {
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(0,0,0,.42);
  color: #fff;
  font-size: 18px;
  line-height: 36px;
  cursor: pointer;
  backdrop-filter: blur(4px);
}
.hero-actions button:last-child {
  width: auto;
  padding: 0 12px;
  border-radius: 18px;
  font-size: 12px;
}
.hero-actions button:hover { background: rgba(255,106,0,.88); }
.hero-counter {
  position: absolute;
  z-index: 3;
  right: 16px;
  bottom: 14px;
  padding: 4px 9px;
  border-radius: 12px;
  background: rgba(0,0,0,.42);
  color: #fff;
  font-size: 11px;
  line-height: 1;
}

.commerce-summary {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
  margin: 0;
  padding: 18px 20px 16px;
  border: 0;
  border-radius: 0;
  background: #fff;
  box-shadow: none;
}
.commerce-title h2 {
  margin: 0;
  color: #222;
  font-size: 22px;
  font-weight: 700;
  line-height: 1.35;
}
.commerce-title p {
  margin: 6px 0 0;
  color: #777;
  font-size: 13px;
  line-height: 1.55;
}
.commerce-price {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin: 14px 0 12px;
}
.commerce-price strong {
  color: var(--shop-orange);
  font-family: var(--font-mono);
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
}
.commerce-price span {
  color: #999;
  font-size: 12px;
}
.commerce-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  margin-top: 11px;
}
.commerce-tags span {
  position: relative;
  padding: 0 12px 0 0;
  border: 0;
  border-radius: 0;
  background: none;
  color: #8b817a;
  font-size: 11px;
  line-height: 1.4;
}
.commerce-tags span + span { padding-left: 12px; }
.commerce-tags span + span::before {
  position: absolute;
  top: 3px;
  left: 0;
  width: 1px;
  height: 10px;
  background: #ddd6d0;
  content: '';
}
.commerce-stats {
  display: flex;
  align-items: stretch;
  gap: 0;
  margin: 0;
  padding: 13px 0;
  border-top: 1px solid var(--shop-line);
  border-bottom: 1px solid var(--shop-line);
}
.commerce-stats div {
  flex: 1;
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 0 14px;
  border-right: 1px solid var(--shop-line);
  text-align: center;
}
.commerce-stats div:first-child { padding-left: 0; text-align: left; }
.commerce-stats div:last-child { padding-right: 0; border-right: 0; text-align: right; }
.commerce-stats strong {
  color: var(--shop-orange);
  font-family: var(--font-mono);
  font-size: 20px;
  line-height: 1.1;
}
.commerce-stats small { color: #999; font-size: 11px; }
.date-picker-row {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  margin: 14px 0 0;
  padding: 0 0 2px;
  border: 0;
  scrollbar-width: none;
}
.date-picker-row::-webkit-scrollbar { display: none; }
.date-picker-row > b {
  flex: 0 0 auto;
  margin-right: 2px;
  color: #333;
  font-size: 13px;
}
.date-chip {
  display: grid;
  flex: 0 0 70px;
  min-width: 70px;
  gap: 2px;
  padding: 8px 6px;
  border: 1px solid #e2ddd8;
  border-radius: 8px;
  background: #fff;
  color: #555;
  text-align: center;
  cursor: pointer;
}
.date-chip.active {
  border-color: var(--shop-orange);
  background: var(--shop-orange-soft);
  color: var(--shop-orange);
  box-shadow: inset 0 -2px 0 var(--shop-orange);
}
.date-chip strong { font-size: 13px; }
.date-chip small { margin-top: 2px; color: #999; font-size: 10px; }
.date-chip.active small { color: var(--shop-orange); }

.trip-strip {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  width: 100%;
  max-width: none;
  box-sizing: border-box;
  margin: 0;
  border: 0;
  border-radius: 0;
  background: #fff;
}
.trip-strip > div {
  min-width: 0;
  padding: 14px 20px;
  border-right: 1px solid var(--shop-line);
}
.trip-strip > div:last-child { border-right: 0; }
.trip-strip span { margin-bottom: 5px; color: #999; font-size: 11px; }
.trip-strip strong {
  color: #333;
  font-size: 13px;
  font-weight: 600;
}

.detail-anchor-nav {
  display: flex;
  justify-content: space-around;
  gap: 0;
  width: 100%;
  max-width: none;
  box-sizing: border-box;
  margin: 8px 0 0;
  padding: 0;
  border: 0;
  border-top: 1px solid var(--shop-line);
  border-bottom: 1px solid var(--shop-line);
  border-radius: 0;
  background: #fff;
  box-shadow: none;
}
.detail-anchor-nav a {
  position: relative;
  padding: 14px 8px 12px;
  color: #666;
  font-size: 13px;
  text-decoration: none;
}
.detail-anchor-nav a:first-child { color: var(--shop-orange); font-weight: 700; }
.detail-anchor-nav a:first-child::after {
  position: absolute;
  right: 8px;
  bottom: -1px;
  left: 8px;
  height: 2px;
  background: var(--shop-orange);
  content: '';
}
.detail-anchor-nav a:hover { color: var(--shop-orange); }

.detail-content {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
  margin: 0;
  padding: 0 0 6px;
  background: #fff;
}
.detail-content > .commerce-highlight,
.detail-content > .compact-story,
.detail-content > .itinerary-section,
.detail-content > .fee-section,
.detail-content > .notice-section,
.detail-content > .review-section,
.detail-content > .detail-facts-section,
.detail-content > .guide-source-section,
.detail-content > .moments-section,
.detail-content > .travel-note-section,
.detail-content > .share-section {
  box-sizing: border-box;
  margin: 0;
  padding: 22px 20px 24px;
  border: 0;
  border-top: 8px solid var(--shop-canvas);
  border-radius: 0;
  background: #fff;
}
.detail-content > .commerce-highlight { border-top: 0; }
.section-heading {
  align-items: center;
  margin: 0 0 14px;
}
.section-heading .section-kicker,
.section-heading .section-count { display: none; }
.section-heading h2 {
  position: relative;
  margin: 0;
  padding-left: 10px;
  color: #222;
  font-size: 19px;
  font-weight: 700;
  line-height: 1.4;
}
.section-heading h2::before {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 0;
  width: 3px;
  border-radius: 2px;
  background: var(--shop-orange);
  content: '';
}
.section-heading > strong { color: var(--shop-orange); font-size: 14px; }
.story-lead { max-width: none; color: #333; font-size: 14px; line-height: 1.8; }
.story-note { max-width: none; margin-top: 8px; color: #888; font-size: 12px; line-height: 1.65; }
.story-tags { gap: 0; margin-top: 12px; }
.story-tags span {
  padding: 0 11px 0 0;
  border-radius: 0;
  background: none;
  color: #999;
  font-size: 11px;
}
.story-tags span + span { padding-left: 11px; border-left: 1px solid #ddd6d0; }

.highlight-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.highlight-grid article {
  overflow: hidden;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.highlight-grid article + article { padding-left: 14px; border-left: 1px solid var(--shop-line); }
.highlight-grid .media-image { height: 178px; border-radius: 6px; }
.highlight-grid h3 { margin: 10px 0 4px; color: #2b2b2b; font-size: 14px; }
.highlight-grid p { margin: 0; color: #888; font-size: 12px; line-height: 1.6; }

.itinerary-list { gap: 0; }
.itinerary-card {
  grid-template-columns: 112px minmax(0, 1fr) auto;
  min-height: 108px;
  padding: 14px 0;
  border: 0;
  border-bottom: 1px solid var(--shop-line);
  border-radius: 0;
  background: #fff;
  box-shadow: none;
}
.itinerary-card:first-child { border-top: 1px solid var(--shop-line); }
.itinerary-card__image,
.itinerary-card__image .media-image {
  height: 108px;
  min-height: 108px;
  border-radius: 6px;
}
.itinerary-card__top span { padding: 0; border-radius: 0; background: none; color: var(--shop-orange); }
.itinerary-card__top b { color: #aaa; }
.itinerary-card h3 { margin: 5px 0 4px; color: #2b2b2b; font-size: 15px; }
.itinerary-card p { color: #777; font-size: 12px; line-height: 1.55; }
.itinerary-card__time { color: var(--shop-orange); }
.itinerary-card small { color: #aaa; }
.itinerary-card__quantity { color: #999; }

.fee-columns { grid-template-columns: 1fr 1fr; gap: 28px; }
.fee-columns > div { padding: 0; border: 0; background: transparent; }
.fee-columns h3 {
  margin: 0 0 4px;
  padding: 0 0 9px;
  border-bottom: 2px solid var(--shop-orange-soft);
  color: var(--shop-orange);
  font-size: 14px;
}
.fee-columns p {
  margin: 0;
  padding: 9px 0;
  border-bottom: 1px solid var(--shop-line);
  color: #666;
  font-size: 12px;
  line-height: 1.55;
}
.notice-list { padding: 0; border: 0; background: transparent; }
.notice-list p {
  margin: 0;
  padding: 10px 0;
  border-bottom: 1px solid var(--shop-line);
  color: #666;
  font-size: 12px;
  line-height: 1.65;
}
.review-card {
  margin: 0;
  padding: 15px 0;
  border: 0;
  border-bottom: 1px solid var(--shop-line);
  background: transparent;
}
.review-card div { align-items: baseline; }
.review-card div b { color: #333; font-size: 13px; }
.review-card span { color: var(--shop-orange); }
.review-card p { margin: 7px 0 0; color: #666; font-size: 12px; line-height: 1.7; }
.detail-facts-grid { gap: 0; }
.detail-facts-grid > div {
  padding: 13px 0;
  border: 0;
  border-bottom: 1px solid var(--shop-line);
  border-radius: 0;
  background: #fff;
}
.detail-facts-grid b { color: #333; font-size: 13px; }
.detail-facts-grid p { margin: 6px 0 0; color: #777; font-size: 12px; line-height: 1.65; }
.guide-list { grid-template-columns: 1fr; gap: 0; }
.guide-list article {
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 5px 12px;
  padding: 13px 0;
  border: 0;
  border-bottom: 1px solid var(--shop-line);
  border-radius: 0;
  background: #fff;
}
.guide-list article strong { color: #333; font-size: 13px; }
.guide-list article span { color: #999; font-size: 11px; }
.guide-list article p { grid-column: 1 / -1; color: #666; }
.moments-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.moments-grid figure { border: 0; border-radius: 0; background: transparent; }
.moments-grid .media-image { height: 166px; border-radius: 6px; }
.moments-grid figcaption { padding: 8px 0 0; }
.moments-grid figcaption span { color: #999; }
.moments-grid figcaption strong { color: #333; }
.travel-note-section { background: #fff; }
.travel-note-heading > .section-kicker,
.share-copy > .section-kicker { display: none; }
.travel-note-heading h2,
.share-copy h2 { margin: 0; color: #222; font-size: 19px; }
.travel-note-heading button { border: 0; border-bottom: 1px solid var(--shop-orange); color: var(--shop-orange); }
.travel-note-copy p { color: #666; }
.travel-note-copy p.first { color: #333; }
.share-section { align-items: center; }
.poster-preview { background: #f7f3ef; box-shadow: none; }

.booking-bar {
  position: fixed !important;
  right: auto;
  bottom: 0;
  left: 50%;
  z-index: 40;
  display: flex;
  width: min(960px, 100%);
  max-width: 960px;
  box-sizing: border-box;
  margin: 0;
  padding: 10px 16px calc(10px + env(safe-area-inset-bottom, 0px));
  transform: translateX(-50%);
  border: 0;
  border-top: 1px solid var(--shop-line);
  border-radius: 0;
  background: rgba(255,255,255,.98);
  box-shadow: 0 -5px 20px rgba(35,30,25,.10);
  backdrop-filter: none;
}
.booking-bar > div:first-child { display: none; }
.booking-bar__right {
  width: 100%;
  justify-content: flex-end;
  gap: 10px;
}
.booking-bar__right strong {
  color: var(--shop-orange);
  font-family: var(--font-mono);
  font-size: 21px;
}
.booking-bar__right span { color: #999; }
.assistant-action {
  height: 40px;
  padding: 0 15px;
  border: 1px solid #ffb17f;
  border-radius: 20px;
  background: #fff;
  color: var(--shop-orange);
  font-size: 13px;
  cursor: pointer;
}
.assistant-action::before { content: '✦ '; font-size: 11px; }
.assistant-action:hover { background: var(--shop-orange-soft); }
.booking-bar :deep(.el-button--primary) {
  min-width: 128px;
  height: 40px;
  padding: 0 24px;
  border: 0;
  border-radius: 20px;
  background: var(--shop-orange) !important;
  border-color: var(--shop-orange) !important;
  box-shadow: none !important;
  font-size: 15px;
  font-weight: 700;
}
.booking-bar :deep(.el-button--primary:hover),
.booking-bar :deep(.el-button--primary:focus) { background: #f45f00 !important; }

.assistant-dialog :deep(.el-dialog) {
  width: min(760px, calc(100% - 32px)) !important;
  max-width: 760px;
  overflow: hidden;
  border-radius: 14px;
}
.assistant-dialog :deep(.el-dialog__header) {
  margin: 0;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--shop-line);
}
.assistant-dialog :deep(.el-dialog__body) {
  max-height: 70vh;
  padding: 0;
  overflow: auto;
}
.assistant-dialog .concierge-section {
  min-height: 0;
  padding: 18px 20px 20px;
  border: 0;
  border-radius: 0;
  background: #fff;
}
.assistant-dialog .concierge-header h2 { color: #222; font-size: 19px; }
.assistant-dialog .concierge-header p { color: #888; }
.concierge-quick button,
.chat-followups button {
  padding: 5px 0;
  border: 0;
  border-bottom: 1px solid #ffc5a1;
  border-radius: 0;
  background: transparent;
  color: var(--shop-orange);
}
.concierge-bubble {
  max-width: 88%;
  border: 1px solid var(--shop-line);
  border-radius: 10px;
  background: #faf9f7;
  box-shadow: none;
}
.concierge-bubble.is-user { border: 0; background: var(--shop-orange-soft); color: #74401f; }
.chat-suggestions {
  display: grid !important;
  grid-template-columns: 1fr !important;
  gap: 10px;
  margin-top: 10px;
}
.chat-suggestions :deep(.product-card--compact) {
  display: grid !important;
  grid-template-columns: 108px minmax(0, 1fr) !important;
  grid-template-rows: 112px;
  width: 100% !important;
  height: 112px;
  min-width: 0;
  min-height: 112px;
  box-sizing: border-box;
  overflow: hidden;
  padding: 0 !important;
  border: 1px solid var(--shop-line);
  border-radius: 8px;
  background: #fff;
  box-shadow: none;
  cursor: pointer;
}
.chat-suggestions :deep(.product-card--compact) > .media-image {
  grid-column: 1;
  grid-row: 1;
  width: 108px !important;
  min-width: 108px;
  height: 112px !important;
  min-height: 112px !important;
  aspect-ratio: auto !important;
  border-radius: 0;
}
.chat-suggestions :deep(.product-card--compact) > .media-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.chat-suggestions :deep(.product-card--compact) .product-card__body {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  padding: 10px 12px !important;
}
.chat-suggestions :deep(.product-card--compact) .product-card__top { display: block; min-width: 0; }
.chat-suggestions :deep(.product-card--compact) .product-card__eyebrow,
.chat-suggestions :deep(.product-card--compact) .product-card__resources { display: none; }
.chat-suggestions :deep(.product-card--compact) h3 {
  margin: 0;
  overflow: hidden;
  color: #333;
  font-size: 14px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chat-suggestions :deep(.product-card--compact) .product-card__hook {
  min-height: 0;
  margin: 5px 0 0;
  overflow: hidden;
  color: #888;
  font-size: 11px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chat-suggestions :deep(.product-card--compact) .product-card__bottom {
  margin-top: auto;
  padding-top: 6px;
  border-top: 0;
}
.chat-suggestions :deep(.product-card--compact) .product-card__bottom strong {
  color: var(--shop-orange);
  font-size: 16px;
}
.chat-suggestions :deep(.product-card--compact) .product-card__bottom .muted { color: #aaa; font-size: 10px; }
.assistant-minimize { color: var(--shop-orange); }

@media (max-width: 700px) {
  .visitor-product-detail { width: 100%; padding-bottom: 116px; }
  .product-detail-hero { height: 300px; min-height: 300px; }
  .back-to-list { top: 12px; left: 12px; }
  .hero-actions { top: 10px; right: 12px; }
  .hero-actions button { width: 32px; height: 32px; line-height: 32px; }
  .hero-actions button:last-child { width: auto; padding: 0 10px; }
  .hero-counter { right: 12px; bottom: 11px; }
  .commerce-summary { padding: 16px 14px 14px; }
  .commerce-title h2 { font-size: 19px; }
  .commerce-price strong { font-size: 28px; }
  .commerce-stats div { padding: 0 10px; }
  .commerce-stats div:first-child { padding-left: 0; }
  .commerce-stats div:last-child { padding-right: 0; }
  .trip-strip > div { padding: 12px 10px; }
  .trip-strip span { font-size: 10px; }
  .trip-strip strong { font-size: 11px; }
  .detail-anchor-nav { margin-top: 6px; }
  .detail-anchor-nav a { padding: 13px 5px 11px; font-size: 12px; }
  .detail-content > .commerce-highlight,
  .detail-content > .compact-story,
  .detail-content > .itinerary-section,
  .detail-content > .fee-section,
  .detail-content > .notice-section,
  .detail-content > .review-section,
  .detail-content > .detail-facts-section,
  .detail-content > .guide-source-section,
  .detail-content > .moments-section,
  .detail-content > .travel-note-section,
  .detail-content > .share-section { padding: 18px 14px 21px; }
  .section-heading h2 { font-size: 18px; }
  .highlight-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .highlight-grid article + article { padding-left: 0; border-left: 0; }
  .highlight-grid .media-image { height: 145px; }
  .highlight-grid article:last-child { grid-column: 1 / -1; }
  .itinerary-card { grid-template-columns: 88px minmax(0, 1fr) 16px; min-height: 88px; padding: 12px 0; gap: 8px; }
  .itinerary-card__image,
  .itinerary-card__image .media-image { height: 88px; min-height: 88px; }
  .itinerary-card h3 { font-size: 13px; }
  .itinerary-card p { font-size: 11px; }
  .fee-columns { grid-template-columns: 1fr; gap: 20px; }
  .detail-facts-grid { grid-template-columns: 1fr; }
  .guide-list article { grid-template-columns: 1fr; gap: 4px; }
  .moments-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .moments-grid .media-image { height: 145px; }
  .travel-note-section { grid-template-columns: 1fr; gap: 9px; }
  .share-section { grid-template-columns: 76px minmax(0, 1fr); gap: 10px; }
  .booking-bar {
    right: 0;
    bottom: 0;
    left: 0;
    width: 100%;
    padding: 8px 10px calc(8px + env(safe-area-inset-bottom, 0px));
    transform: none;
  }
  .booking-bar__right { gap: 7px; }
  .booking-bar__right strong { font-size: 17px; }
  .booking-bar :deep(.el-button--primary) { min-width: 112px; height: 40px; padding: 0 16px; font-size: 14px; }
  .assistant-action { height: 40px; min-width: 78px; padding: 0 10px; font-size: 12px; }
  .assistant-dialog :deep(.el-dialog) { width: calc(100% - 20px) !important; margin: 8vh auto 0 !important; }
  .assistant-dialog .concierge-section { padding: 16px 14px 18px; }
  .chat-suggestions :deep(.product-card--compact) { grid-template-columns: 88px minmax(0, 1fr) !important; height: 104px; min-height: 104px; grid-template-rows: 104px; }
  .chat-suggestions :deep(.product-card--compact) > .media-image { width: 88px !important; min-width: 88px; height: 104px !important; min-height: 104px !important; }
}
@media (max-width: 390px) {
  .booking-bar__right { gap: 5px; }
  .booking-bar__right strong { font-size: 15px; }
  .assistant-action { min-width: 70px; padding: 0 8px; font-size: 11px; }
  .booking-bar :deep(.el-button--primary) { min-width: 100px; padding: 0 12px; font-size: 13px; }
}
</style>


<style scoped>
.date-note { flex: 0 0 auto; color: #999; font-size: 10px; }
@media (max-width: 700px) { .date-note { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } }
</style>


<style scoped>
.hero-nav { position: absolute; z-index: 3; top: 50%; display: grid; width: 34px; height: 34px; place-items: center; margin-top: -17px; padding: 0; border: 0; border-radius: 50%; background: rgba(0,0,0,.34); color: #fff; font-size: 28px; line-height: 1; cursor: pointer; backdrop-filter: blur(4px); }
.hero-nav:hover { background: rgba(255,106,0,.88); }
.hero-nav--prev { left: 16px; }
.hero-nav--next { right: 16px; }
.hero-dots { position: absolute; z-index: 3; bottom: 17px; left: 50%; display: flex; gap: 5px; transform: translateX(-50%); }
.hero-dots button { width: 5px; height: 5px; padding: 0; border: 0; border-radius: 50%; background: rgba(255,255,255,.55); cursor: pointer; }
.hero-dots button.active { width: 16px; border-radius: 3px; background: #fff; }
@media (max-width: 700px) { .hero-nav { width: 30px; height: 30px; margin-top: -15px; font-size: 24px; } .hero-nav--prev { left: 10px; } .hero-nav--next { right: 10px; } .hero-dots { bottom: 13px; } }
</style>


<style scoped>
/* Day-by-day itinerary: the package is sold per hotel night, so the plan is
   grouped into days with a time rail instead of a flat resource list. */
.date-chip.disabled { cursor: not-allowed; opacity: .45; }
.date-chip small { white-space: nowrap; }
.day-plan-list { display: grid; gap: 14px; }
.day-plan { padding: 16px 18px; border: 1px solid #eee3da; border-radius: 12px; background: #fffdfb; }
.day-plan__head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding-bottom: 10px; border-bottom: 1px dashed #f0e2d6; }
.day-plan__head strong { display: block; margin-top: 6px; color: #2b2b2b; font-size: 17px; }
.day-plan__head small { color: #a4968b; font-size: 11px; }
.day-plan__label { display: inline-block; padding: 3px 9px; border-radius: 999px; background: #fff1e4; color: #d56835; font-size: 11px; font-weight: 700; }
.day-plan__summary { margin: 10px 0 12px; color: #7d6f66; font-size: 12px; line-height: 1.65; }
.day-plan__items { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.day-plan__items li { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 12px; align-items: start; }
.day-plan__time { padding-top: 2px; color: #d56835; font-family: var(--font-mono); font-size: 11px; }
.day-plan__time b { display: block; margin-bottom: 3px; color: #2b2b2b; font-family: var(--font-sans); font-size: 11px; }
.day-plan__meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.day-plan__meta span { padding: 3px 7px; border-radius: 999px; background: #f6f1ec; color: #8a7c72; font-size: 10px; }
.day-plan__meta .day-plan__note { background: #fff5e6; color: #a4703a; }
.day-plan__items b { display: block; color: #33302e; font-size: 13px; }
.day-plan__items p { margin: 4px 0 0; color: #7a6f68; font-size: 11px; line-height: 1.6; }
@media (max-width: 700px) {
  .day-plan { padding: 13px; }
  .day-plan__items li { grid-template-columns: 78px minmax(0, 1fr); gap: 8px; }
  .day-plan__items b { font-size: 12px; }
}
</style>

<style scoped>
.soldout-banner { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; max-width: 960px; margin: 12px auto 0; padding: 14px 16px; border: 1px solid #f2d4bb; border-radius: 12px; background: #fff7ef; }
.soldout-banner strong { display: block; color: #9a5b2a; font-size: 14px; }
.soldout-banner span { display: block; margin-top: 4px; color: #a5876f; font-size: 11px; }
.soldout-banner__actions { display: flex; flex-wrap: wrap; gap: 8px; }
.soldout-banner__actions button { padding: 8px 12px; border: 1px solid #f0d6c0; border-radius: 9px; background: #fff; text-align: left; cursor: pointer; }
.soldout-banner__actions b { display: block; color: #7b4a22; font-size: 12px; }
.soldout-banner__actions span { display: block; margin-top: 3px; color: #a5876f; font-size: 10px; }
.room-choice { display: grid; gap: 14px; max-width: 960px; margin: 16px auto 0; }
.room-choice__options { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; margin-top: 8px; }
.room-choice__options button { display: grid; gap: 4px; padding: 12px 13px; border: 1px solid #e8e2dc; border-radius: 10px; background: #fff; text-align: left; cursor: pointer; }
.room-choice__options button:hover { border-color: #d56835; }
.room-choice__options button.active { border-color: #d56835; background: #fff7f1; }
.room-choice__options button.disabled { opacity: .55; cursor: not-allowed; }
.room-choice__options b { color: #33302e; font-size: 13px; }
.room-choice__options small { color: #8b8078; font-size: 11px; }
.room-choice__options em { color: #d56835; font-size: 11px; font-style: normal; }
.chat-suggestions { grid-template-columns: 1fr !important; gap: 8px; }
.chat-suggestions .product-card--compact { grid-template-columns: 132px minmax(0, 1fr); min-height: 148px; border: 1px solid #eee3da; border-radius: 10px; }
.chat-suggestions .product-card--compact > .media-image { height: 100%; min-height: 148px; }
.chat-suggestions .product-card--compact .product-card__body { display: grid; gap: 6px; padding: 12px 13px; }
.chat-suggestions .product-card--compact h3 { margin: 0; font-size: 14px; line-height: 1.35; white-space: normal; }
.chat-suggestions .product-card--compact .product-card__hook {
  min-height: 0;
  margin: 0;
  -webkit-line-clamp: 3;
  color: #6f6a66;
  font-size: 11px;
  line-height: 1.7;
}
.chat-suggestions .product-card--compact .product-card__facts { display: flex; flex-wrap: wrap; gap: 4px 8px; font-size: 10px; }
.chat-suggestions .product-card--compact .product-card__bottom { padding-top: 8px; }
.chat-suggestions .product-card--compact .product-card__bottom strong { font-size: 16px; }
.review-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.review-card { padding: 14px 16px; border: 1px solid #eee9e4; border-radius: 10px; background: #fff; }
.review-card__head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
.review-card__head b { color: #33302e; font-size: 13px; }
.review-card__head span { color: #ff6a00; font-size: 12px; }
.review-card__head small { margin-left: auto; color: #a9a09a; font-size: 10px; }
.review-highlights { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.review-highlights span { padding: 3px 7px; border-radius: 999px; background: #f5f1ec; color: #8b8078; font-size: 10px; }
.review-source { display: block; margin-top: 8px; color: #b6ada7; font-size: 10px; }
.review-empty { margin: 0; padding: 18px; border: 1px dashed #eee9e4; border-radius: 10px; color: #a9a09a; font-size: 12px; }
@media (max-width: 820px) { .review-list { grid-template-columns: 1fr; } }
</style>


<style scoped>
.hotel-detail-section, .photo-detail-section { margin-bottom: 24px; }
.hotel-detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.hotel-detail-grid > div { padding: 12px 14px; border: 1px solid #eee9e4; border-radius: 10px; background: #fff; }
.hotel-detail-grid > div.full { grid-column: 1 / -1; }
.hotel-detail-grid span { display: block; color: #a9a09a; font-size: 10px; }
.hotel-detail-grid strong { display: block; margin-top: 6px; color: #33302e; font-size: 13px; line-height: 1.6; }
.photo-detail-lead { margin: 0 0 10px; color: #5f6a66; font-size: 12px; line-height: 1.7; }
.photo-detail-list { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.photo-detail-list li { padding: 9px 12px; border-left: 2px solid #ff6a00; background: #fff7f1; color: #7a6b62; font-size: 12px; line-height: 1.6; }
@media (max-width: 700px) { .hotel-detail-grid { grid-template-columns: 1fr; } }
</style>


<style scoped>
.empty-mark svg { width: 26px; height: 26px; }
.media-fallback__mark svg { width: 24px; height: 24px; }
</style>


<style scoped>
/* 锚点导航固定在顶部，滚动时也能快速切换 */
.detail-anchor-nav {
  position: sticky;
  top: 0;
  z-index: 40;
  background: rgba(255, 255, 255, .97);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid #f0ebe6;
}
/* 特色区块：卡片等高、图文对齐，不再用竖向分割线 */
.highlight-grid { align-items: stretch; }
.highlight-grid article {
  display: flex;
  flex-direction: column;
  padding: 0 0 12px;
  border: 1px solid #eee9e4;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.highlight-grid article + article { padding-left: 0; border-left: 1px solid #eee9e4; }
.highlight-grid .media-image { height: 178px; border-radius: 0; }
.highlight-grid h3 { margin: 12px 14px 6px; font-size: 14px; line-height: 1.4; }
.highlight-grid p { margin: 0 14px; font-size: 12px; line-height: 1.7; }
/* 介绍文案分段 */
.story-lead { margin: 0 0 10px; }
.story-lead:last-of-type { margin-bottom: 0; }
/* 路线图 */
.guide-list { display: grid; grid-template-columns: 1fr; gap: 12px; width: 100%; }
.guide-list article { padding: 14px 16px; border: 1px solid #eee9e4; border-radius: 12px; background: #fff; }
.guide-list header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.guide-list header strong { color: #2b2b2b; font-size: 15px; }
.guide-list header em { color: #d56835; font-size: 11px; font-style: normal; }
.guide-source-line { display: block; margin-top: 5px; color: #a9a09a; font-size: 10px; }
.guide-content { width: 100%; margin: 9px 0 0; color: #4f5b57; font-size: 13px; line-height: 1.8; }
.guide-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px 18px; width: 100%; margin: 10px 0 0; padding: 10px 0 0; border-top: 1px dashed #f0e8e0; list-style: none; }
.guide-facts li { color: #6f6660; font-size: 11px; line-height: 1.65; }
.guide-facts b { display: inline-block; min-width: 62px; margin-right: 6px; color: #9a9089; font-weight: 500; }
.guide-verified { display: block; margin-top: 8px; color: #b3aaa3; font-size: 10px; }
.route-section { margin-bottom: 26px; }
.route-tabs { display: flex; gap: 6px; }
.route-tabs button { padding: 6px 12px; border: 1px solid #e8e2dc; border-radius: 999px; background: #fff; color: #7a6f68; font-size: 11px; cursor: pointer; }
.route-tabs button.active { border-color: #d56835; background: #fff4ec; color: #d56835; }
.route-summary { margin: 0 0 10px; color: #8b8078; font-size: 12px; }
.route-stops { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.route-stops li { display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 10px; align-items: start; }
.route-index { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: #ff6a00; color: #fff; font-size: 12px; }
.route-stop__body { min-width: 0; padding-bottom: 8px; border-bottom: 1px dashed #f0e6dd; }
.route-stop__body strong { display: block; color: #33302e; font-size: 13px; }
.route-stop__body small { display: block; margin-top: 3px; color: #8b8078; font-size: 11px; }
.route-stop__body a { display: inline-block; margin-top: 5px; color: #d56835; font-size: 11px; text-decoration: none; }
.route-legs { display: grid; gap: 8px; margin-top: 12px; }
.route-leg { padding: 9px 12px; border-radius: 9px; background: #f7f3ef; }
.route-leg header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.route-leg b { color: #57514c; font-size: 12px; }
.route-leg span { color: #a89c93; font-size: 10px; }
.route-leg p { margin: 4px 0 0; color: #6f6660; font-size: 11px; }
.route-leg small { display: block; margin-top: 3px; color: #9a8f87; font-size: 10px; line-height: 1.55; }
@media (max-width: 700px) { .highlight-grid { grid-template-columns: 1fr; } .highlight-grid .media-image { height: 150px; } }
</style>


<style scoped>
.detail-intro p { margin: 0 0 9px; color: #3f4a46; font-size: 13px; line-height: 1.85; }
.experience-details { display: grid; gap: 12px; margin: 16px 0 18px; }
.experience-details article { padding: 13px 15px; border: 1px solid #eee9e4; border-radius: 11px; background: #fff; }
.experience-details header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.experience-details header strong { color: #2b2b2b; font-size: 14px; }
.experience-details header span { color: #d56835; font-size: 11px; }
.experience-details > article > p { margin: 8px 0 0; color: #6f6a66; font-size: 12px; line-height: 1.7; }
.experience-details ul { display: grid; gap: 5px; margin: 9px 0 0; padding: 9px 0 0; border-top: 1px dashed #f0e8e0; list-style: none; }
.experience-details li { color: #6f6660; font-size: 11px; line-height: 1.65; }
.experience-details b { display: inline-block; min-width: 34px; margin-right: 8px; color: #9a9089; font-weight: 500; }
.detail-extra { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.detail-extra > div { padding: 13px 15px; border-radius: 11px; background: #f7f4f0; }
.detail-extra p { margin: 7px 0 0; color: #6f6660; font-size: 11px; line-height: 1.7; }
.related-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
.related-grid :deep(.product-card) { display: grid; grid-template-columns: 180px minmax(0, 1fr); }
.related-grid :deep(.product-card > .media-image),
.related-grid :deep(.product-card > .product-card__media),
.related-grid :deep(.product-card > .product-card__media > .media-image) { height: 100%; min-height: 150px; aspect-ratio: auto; }
@media (max-width: 900px) { .detail-extra { grid-template-columns: 1fr; } .related-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>

<style scoped>
/* 价格移到标题右侧，已售在价格下方：大价格、小已售。 */
.commerce-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.commerce-head .commerce-title { flex: 1 1 auto; min-width: 0; }
.commerce-head .commerce-price { flex: 0 0 auto; display: grid; justify-items: end; align-content: start; margin: 0; text-align: right; }
.commerce-head .commerce-price strong { font-size: 32px; }
.commerce-head .commerce-price em { display: block; margin-top: 4px; color: #999; font-size: 12px; font-style: normal; }
@media (max-width: 700px) {
  .commerce-head { gap: 10px; }
  .commerce-head .commerce-price strong { font-size: 24px; }
  .commerce-head .commerce-price em { font-size: 11px; }
}

/* 住宿 / 拍摄 / 同一天的其他方案：与上方板块统一留白与橙色竖线。 */
.detail-content > .hotel-detail-section,
.detail-content > .photo-detail-section,
.detail-content > .related-section {
  box-sizing: border-box;
  margin: 0;
  padding: 22px 20px 24px;
  border: 0;
  border-top: 8px solid var(--shop-canvas, #f5f5f5);
  border-radius: 0;
  background: #fff;
}

/* 章节导航：保留原来的文字 + 橙色下划线样式，只把「固定方式」改成贴在顶部导航条
   （visitor-header，62px）下方，避免压住页头。 */
.room-choice { margin-bottom: 18px; }
.detail-anchor-nav {
  position: sticky !important;
  top: 62px !important;
  z-index: 4 !important;
  display: flex !important;
  flex-wrap: nowrap;
  justify-content: space-around;
  gap: 0;
  width: 100% !important;
  max-width: none !important;
  box-sizing: border-box;
  margin: 16px 0 0 !important;
  padding: 0 !important;
  border: 0 !important;
  border-top: 1px solid #eee9e4 !important;
  border-bottom: 1px solid #eee9e4 !important;
  border-radius: 0 !important;
  background: rgba(255, 255, 255, .97);
  backdrop-filter: blur(8px);
  box-shadow: 0 2px 8px rgba(30, 50, 40, .05);
}
.detail-anchor-nav button {
  position: relative;
  flex: 1 1 0;
  padding: 14px 8px 12px;
  border: 0;
  background: transparent;
  color: #666;
  font-size: 13px;
  cursor: pointer;
}
.detail-anchor-nav button:hover { color: #ff6a00; }
.detail-anchor-nav button.active { color: #ff6a00; font-weight: 700; }
.detail-anchor-nav button.active::after {
  position: absolute;
  right: 8px;
  bottom: -1px;
  left: 8px;
  height: 2px;
  background: #ff6a00;
  content: '';
}
@media (max-width: 700px) {
  .detail-anchor-nav { margin-top: 12px !important; }
  .detail-anchor-nav button { padding: 12px 4px 10px; font-size: 12px; }
}
@media (max-width: 520px) {
  .detail-anchor-nav { top: 56px !important; }
}

/* 地址、交通与细节：两列之间用竖线隔开。 */
.detail-facts-grid > div { position: relative; }
.detail-facts-grid > div:nth-child(even)::before {
  position: absolute;
  top: 14px;
  bottom: 14px;
  left: 0;
  width: 1px;
  background: #e7e1db;
  content: '';
}
@media (max-width: 700px) {
  .detail-facts-grid > div:nth-child(even)::before { display: none; }
}

/* 参考路线与评价：单列整宽铺排，三段式（标题 / 来源 / 正文 + 事实）。 */
.guide-source-section .guide-list {
  display: grid !important;
  grid-template-columns: minmax(0, 1fr) !important;
  gap: 12px !important;
}
.guide-source-section .guide-list > article {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 9px;
  width: 100%;
  padding: 16px 18px;
  border: 1px solid var(--shop-line, #e7e1db);
  border-radius: 10px;
  background: #f8fbf9;
}
.guide-source-section .guide-list > article > header {
  display: block;
}
.guide-source-section .guide-list > article > header strong { color: #1f3a33; font-size: 16px; font-weight: 700; line-height: 1.4; }
.guide-source-section .guide-list > article > header em { display: block; margin-top: 4px; color: #b07a33; font-size: 12px; font-style: normal; }
.guide-source-section .guide-source-line { color: #8a9a94; font-size: 12px; }
.guide-source-section .guide-content { margin: 0; color: #45564f; font-size: 13px; line-height: 1.8; }
.guide-source-section .guide-facts {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 6px;
  margin: 2px 0 0;
  padding: 0;
  list-style: none;
}
.guide-source-section .guide-facts li { color: #54655e; font-size: 12px; line-height: 1.65; overflow-wrap: anywhere; }
.guide-source-section .guide-facts b { display: inline-block; min-width: 60px; margin-right: 10px; color: #2f6f60; font-weight: 600; }
.guide-source-section .guide-verified { color: #9aa8a2; font-size: 11px; }

/* 让 sticky 生效（祖先不能是 overflow:hidden）；具体偏移见上方章节导航规则。 */
.visitor-product-detail { overflow: visible !important; }
.visitor-product-detail.is-embedded-preview { padding-bottom: 0; }
.preview-mode-banner { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 0 10px; padding:10px 14px; border:1px solid #d8e9e0; border-radius:10px; background:#f0f8f4; color:#315f52; font-size:12px; }
.preview-mode-banner a { color:#236e5e; font-weight:650; text-decoration:none; }
.review-section { margin:0 0 24px; }
.review-rating { color:#88703a; font-size:12px; }
.review-list { display:grid; gap:8px; }
.review-card { padding:12px 14px; border:1px solid var(--line); border-radius:10px; background:#fff; }
.review-card header { display:flex; justify-content:space-between; gap:12px; color:var(--ink); font-size:12px; }
.review-card header span { color:var(--muted); font-size:10px; }
.review-card p,.review-empty { margin:7px 0 0; color:#53645d; font-size:12px; line-height:1.7; }
.review-highlights { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; }
.review-highlights span { padding:3px 7px; border-radius:999px; background:#edf7f2; color:#36796b; font-size:10px; }
@media (max-width: 700px) {
  .preview-mode-banner { margin:0 0 8px; padding:9px 11px; }
  .review-card header { align-items:flex-start; flex-direction:column; gap:3px; }
  .guide-source-section .guide-facts { grid-template-columns: 1fr; }
}
</style>
