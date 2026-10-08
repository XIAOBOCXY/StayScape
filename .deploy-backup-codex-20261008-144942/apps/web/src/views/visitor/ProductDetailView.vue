<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { hotelApi, visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import MediaImage from '../../components/MediaImage.vue'
import ProductCard from '../../components/ProductCard.vue'
import VisitorAssistant from '../../components/VisitorAssistant.vue'
import type { IncludedPublicPlace, TravelProduct } from '../../types'
import { distinctMediaForResources, experienceLabelZh, experienceMoments, mediaCandidatesForResource, mediaForProduct, primaryProductMedia, type ProductMediaAsset } from '../../utils/productMedia'
import { publicTravelCopy } from '../../utils/publicTravelCopy'
import { loadVisitorProfile, saveVisitorProfile, type VisitorProfile, visitorConversationId } from '../../utils/visitorProfile'

const route = useRoute()
const router = useRouter()
// 经营端预览（/hotel/products/:id）与游客端预览（?preview=1）共用同一套实现：
// 两者只有取数接口和提示文案不同，避免两份 1700 行的详情页各自漂移。
const hotelContext = computed(() => route.path.startsWith('/hotel/products/') || route.query.hotelPreview === '1')
const previewMode = computed(() => hotelContext.value || route.query.preview === '1')
const embeddedMode = computed(() => route.query.embedded === '1')
const product = ref<TravelProduct | null>(null)
const loading = ref(true)
const question = ref('')
const chats = ref<Array<{ user?: string; answer?: string; suggestions?: TravelProduct[]; follow_up_questions?: string[] }>>([])
const consultLoading = ref(false)
const intentDialog = ref(false)
const intentLoading = ref(false)
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

const gallerySource = computed(() => experienceMoments(product.value))
// The length of stay belongs to the product itself, so the page only reports
// the bound stay instead of letting a visitor re-schedule it.
const nights = ref(1)
const stay = computed(() => product.value?.stay || null)
const stayLabel = computed(() => stay.value?.label || '2天1晚')
const stayPrice = computed(() => String(stay.value?.price || product.value?.suggested_price || ''))
const stayOptions = computed(() => stay.value?.options || [])
function guideOpenDuring(guide: Record<string, any>, date: string, start: number, end: number) {
  const hours = String(guide.opening_hours || '')
  if (!hours) return false
  const ranges = [...hours.matchAll(/(\d{1,2}):(\d{2})\s*(?:-|–|—|~|～|至|到)\s*(\d{1,2}):(\d{2})/g)]
  if (!ranges.length) return false
  const [year, month, day] = date.split('-').map(Number)
  const weekday = year && month && day ? new Date(Date.UTC(year, month - 1, day)).getUTCDay() : null
  const dayName = weekday === null ? '' : '周' + ['日', '一', '二', '三', '四', '五', '六'][weekday]
  if (dayName && (hours.includes(dayName + '闭馆') || hours.includes(dayName + '休馆'))) return false
  return ranges.some((match) => {
    const open = Number(match[1]) * 60 + Number(match[2])
    const close = Number(match[3]) * 60 + Number(match[4])
    return open < end && close > start
  })
}
function freeTimeSuggestions(date: string, start: number, end: number, crowd: string) {
  const group = ({ FAMILY: '亲子家庭', COUPLE: '双人同行', FRIENDS: '朋友同行', SOLO: '独自出行' } as Record<string, string>)[crowd] || '同行游客'
  return guides.value
    .filter((guide) => guideOpenDuring(guide, date, start, end))
    .filter((guide) => !['COUPLE', 'FRIENDS', 'SOLO'].includes(crowd) || !/亲子|孩子|儿童|少儿|4[–-]12岁/.test(String(guide.title || '') + String(guide.content || guide.summary || '')))
    .slice(0, 2)
    .map((guide) => {
      const title = String(guide.title || guide.name || '附近地点')
      const category = String(guide.category_label || '')
      const reason = String(guide.content || guide.summary || '').split(/[。！？!?；;]/)[0].trim()
      return { title: title + (category ? '｜' + category : ''), detail: [guideDurationLabel(guide) ? '约 ' + guideDurationLabel(guide) : '', reason, '适合' + group].filter(Boolean).join(' · ') }
    })
}
function formatScheduleClock(minutes: number) {
  return String(Math.floor(minutes / 60)).padStart(2, '0') + ':' + String(minutes % 60).padStart(2, '0')
}
function cleanHotelAddress(value: unknown) {
  return String(value || '').replace(/StayScape\s*杭州测试酒店|杭州测试酒店|StayScape\s*测试酒店/gi, '').replace(/^[\s,，·｜|]+|[\s,，·｜|]+$/g, '').trim()
}
const dayPlan = computed(() => {
  const current = product.value
  if (!current) return []
  const plan = stay.value
  const nightsCount = Math.max(1, Number(plan?.nights || 1))
  const startDate = String(plan?.check_in || current.target_date || '').slice(0, 10)
  const dateStamp = (value: string) => {
    const [year, month, day] = value.split('-').map(Number)
    return year && month && day ? Date.UTC(year, month - 1, day) : 0
  }
  const startMs = startDate ? dateStamp(startDate) : 0
  const days: Array<Record<string, any>> = Array.from({ length: nightsCount + 1 }, (_, index) => {
    const date = startMs ? new Date(startMs + index * 86400000).toISOString().slice(0, 10) : ''
    return { day_index: index + 1, label: '第 ' + (index + 1) + ' 天', date, title: index === 0 ? '入住与体验安排' : index === nightsCount ? '继续体验 · 退房返程' : '继续体验与自由活动', summary: '', items: [] }
  })
  // Hotel benefits are listed in the package details, not as itinerary stops.
  const resources = current.resources.filter((r) => ['ROOM', 'PARTNER_RESOURCE'].includes(r.resource_type))
  for (const r of resources) {
    if (r.resource_type === 'ROOM') continue
    const resourceDate = String((r as any).available_date || startDate).slice(0, 10)
    const resourceMs = resourceDate ? dateStamp(resourceDate) : startMs
    const dayIndex = startMs && resourceMs ? Math.floor((resourceMs - startMs) / 86400000) + 1 : 1
    if (dayIndex < 1 || dayIndex > days.length) continue
    const time = r.start_time ? String(r.start_time).slice(0, 5) + (r.end_time ? '–' + String(r.end_time).slice(0, 5) : '') : ''
    const hour = Number(String(r.start_time || '').slice(0, 2))
    const slot = !time ? '体验' : hour < 12 ? '上午' : hour < 18 ? '下午' : '晚间'
    days[dayIndex - 1].items.push({
      kind: r.resource_type, title: r.resource_name, time, slot_label: slot,
      description: usefulCopy(r.description, r.resource_name + '。'), address: r.address || '',
      duration_text: '', notes: r.booking_notice || '',
      included: true, route_only: false, schedule_conflict: false,
      sort_time: r.start_time ? Number(String(r.start_time).slice(0, 2)) * 60 + Number(String(r.start_time).slice(3, 5)) : 1440,
    })
  }
  for (const stop of (current.included_public_places || [])) {
    const stopDate = String(stop.available_date || '').slice(0, 10)
    const stopMs = stopDate ? dateStamp(stopDate) : startMs
    const dayIndex = Number(stop.day_index || (startMs && stopMs ? Math.floor((stopMs - startMs) / 86400000) + 1 : 1))
    if (dayIndex < 1 || dayIndex > days.length) continue
    const start = String(stop.start_time || '').slice(0, 5)
    const end = String(stop.end_time || '').slice(0, 5)
    days[dayIndex - 1].items.push({
      kind: 'PUBLIC_REFERENCE',
      title: stop.resource_name,
      time: start && end ? start + '–' + end : stop.time,
      slot_label: stop.slot_label,
      description: stop.description,
      address: stop.address,
      duration_text: stop.duration_text,
      notes: '',
      included: true,
      route_only: false,
      schedule_conflict: false,
      media_resource: stop,
      sort_time: start ? Number(start.slice(0, 2)) * 60 + Number(start.slice(3, 5)) : 1440,
    })
  }
  const room = resources.find((r) => r.resource_type === 'ROOM')
  if (room) {
    const hotelAddress = cleanHotelAddress(plan?.hotel_address || room.address || '')
    const clockMinutes = (value: unknown) => {
      const match = String(value || '').match(/^(\d{1,2}):(\d{2})/)
      return match ? Number(match[1]) * 60 + Number(match[2]) : null
    }
    const formatClock = (value: number) => String(Math.floor(value / 60)).padStart(2, '0') + ':' + String(value % 60).padStart(2, '0')
    const firstDay = days[0]
    const firstStops = firstDay.items.filter((item: Record<string, any>) => ['PARTNER_RESOURCE', 'PUBLIC_REFERENCE'].includes(item.kind))
    const earliest = [...firstStops].sort((a: Record<string, any>, b: Record<string, any>) => (clockMinutes(a.time) ?? 1440) - (clockMinutes(b.time) ?? 1440))[0]
    const lastStop = [...firstStops].filter((item: Record<string, any>) => clockMinutes(String(item.time).split('–')[1]) !== null)
      .sort((a: Record<string, any>, b: Record<string, any>) => (clockMinutes(String(b.time).split('–')[1]) ?? 0) - (clockMinutes(String(a.time).split('–')[1]) ?? 0))[0]
    const activityEnd = lastStop ? clockMinutes(String(lastStop.time).split('–')[1]) : null
    const leg = lastStop ? (current.route_plan || []).find((day) => Number(day.day_index) === 1)?.legs?.find((item) => item.from_stop.includes(String(lastStop.title)) && /入住|酒店/.test(item.to_stop)) : null
    const travel = Math.max(0, Number(leg?.minutes || 0))
    if (lastStop && activityEnd !== null && travel > 0) {
      firstDay.items.push({ kind: 'TRANSFER', title: '返回酒店', time: formatClock(activityEnd) + '–' + formatClock(activityEnd + travel), slot_label: '返程', description: '从' + lastStop.title + '返回酒店办理入住。', address: hotelAddress, duration_text: '约 ' + travel + ' 分钟', notes: String(leg?.mode || leg?.distance_label || ''), included: false, route_only: true, sort_time: activityEnd })
    }
    const checkIn = Math.max(clockMinutes(plan?.check_in_time || '13:00') ?? 13 * 60, (activityEnd ?? 0) + travel)
    const roomCopy = String(room.description || '').split(/[；。]/).map((part) => part.trim()).filter((part) => part && !/入住|退房|行李寄存|含\d+晚住宿/.test(part)).slice(0, 1).join('')
    const details = [room.resource_name + '，含 ' + (plan?.nights || 1) + ' 晚住宿', roomCopy, '当天体验结束后返回酒店办理入住。'].filter(Boolean).join('。')
    firstDay.items.push({ id: room.id, resource_id: room.resource_id, kind: 'ROOM', title: '入住 · ' + room.resource_name, time: activityEnd === null ? formatClock(checkIn) + ' 后' : formatClock(checkIn), slot_label: '酒店入住', description: details, address: hotelAddress, quantity_text: '', included: true, route_only: false, sort_time: checkIn })
    const last = days[days.length - 1]
    const checkout = clockMinutes(plan?.check_out_time || '13:00') ?? 13 * 60
    last.items.push({ id: room.id, resource_id: room.resource_id, kind: 'ROOM', title: '办理退房', time: formatClock(checkout) + ' 前', slot_label: '酒店退房', description: '结束本次入住。', address: hotelAddress, quantity_text: '', included: true, route_only: false, sort_time: checkout })
  }
  let freePeriodUsed = false
  for (const day of days) {
    const scheduled = day.items
      .filter((item: Record<string, any>) => ['PARTNER_RESOURCE', 'PUBLIC_REFERENCE'].includes(item.kind))
      .map((item: Record<string, any>) => {
        const match = String(item.time || '').match(/^(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})$/)
        if (!match) return null
        return { item, start: Number(match[1]) * 60 + Number(match[2]), end: Number(match[3]) * 60 + Number(match[4]) }
      })
      .filter((entry: Record<string, any> | null): entry is Record<string, any> => Boolean(entry))
      .sort((a: Record<string, any>, b: Record<string, any>) => a.start - b.start)
    if (!freePeriodUsed && scheduled.length && scheduled[0].start >= 14 * 60) {
      const first = scheduled[0]
      const dayRoute = (current.route_plan || []).find((routeDay) => Number(routeDay.day_index) === Number(day.day_index))
      const inbound = dayRoute?.legs?.find((leg) =>
        String(leg.to_stop || '').includes(String(first.item.title)) && /酒店|住宿|前台/.test(String(leg.from_stop || '')),
      )
      const travel = Math.max(0, Number(inbound?.minutes || 0))
      const freeStart = 12 * 60
      const freeEnd = first.start - travel
      if (freeEnd - freeStart >= 120) {
        const suggestions = freeTimeSuggestions(day.date, freeStart, freeEnd, String(current.target_crowd || ''))
        day.items.push({
          kind: 'FREE_TIME',
          title: '午餐与体验前安排',
          time: formatScheduleClock(freeStart) + '–' + formatScheduleClock(freeEnd),
          slot_label: '午间',
          description: '午餐自行安排；可从下方附近地点中择一短游，并为前往首项体验预留时间。',
          suggestions,
          included: false,
          route_only: true,
          sort_time: freeStart,
        })
        if (travel > 0) {
          day.items.push({
            kind: 'TRANSFER',
            title: '前往' + first.item.title,
            time: formatScheduleClock(freeEnd) + '–' + formatScheduleClock(first.start),
            slot_label: '前往体验',
            description: '从酒店前往' + first.item.title + '。',
            address: first.item.address || '',
            duration_text: '约 ' + travel + ' 分钟',
            notes: String(inbound?.mode || inbound?.distance_label || ''),
            included: false,
            route_only: true,
            sort_time: freeEnd,
          })
        }
        freePeriodUsed = true
      }
    }
    for (let index = 0; index < scheduled.length - 1; index += 1) {
      const previous = scheduled[index]
      const next = scheduled[index + 1]
      const gap = next.start - previous.end
      const dayRoute = (current.route_plan || []).find((routeDay) => Number(routeDay.day_index) === Number(day.day_index))
      const leg = dayRoute?.legs?.find((item) =>
        String(item.from_stop || '').includes(String(previous.item.title)) && String(item.to_stop || '').includes(String(next.item.title)),
      )
      const travel = Math.max(0, Number(leg?.minutes || 0))
      const hasTransfer = travel > 0 && travel < gap
      const freeEnd = hasTransfer ? next.start - travel : next.start
      if (hasTransfer) {
        day.items.push({
          kind: 'TRANSFER',
          title: '前往' + next.item.title,
          time: formatScheduleClock(freeEnd) + '–' + formatScheduleClock(next.start),
          slot_label: '前往下一项',
          description: '从' + previous.item.title + '前往' + next.item.title + '。',
          address: next.item.address || '',
          duration_text: '约 ' + travel + ' 分钟',
          notes: String(leg?.mode || leg?.distance_label || ''),
          included: false,
          route_only: true,
          sort_time: freeEnd,
        })
      }
      if (freePeriodUsed || freeEnd - previous.end < 120) continue
      const suggestions = freeTimeSuggestions(day.date, previous.end, freeEnd, String(current.target_crowd || ''))
      day.items.push({
        kind: 'FREE_TIME',
        title: previous.end < 12 * 60 && next.start > 12 * 60 ? '午餐与自由活动' : '自由活动',
        time: formatScheduleClock(previous.end) + '–' + formatScheduleClock(freeEnd),
        slot_label: '自由活动',
        description: suggestions.length
          ? '午餐自行安排，午餐后可从附近地点中择一短游，并为下一项体验预留路程时间。'
          : '午餐与休息自行安排，可按兴趣短途漫游；请预留前往下一项体验地点的时间。',
        suggestions,
        included: false,
        route_only: true,
        sort_time: previous.end,
      })
      freePeriodUsed = true
    }
    day.items.sort((a: Record<string, any>, b: Record<string, any>) => a.sort_time - b.sort_time)
    day.items.forEach((item: Record<string, any>) => delete item.sort_time)
    day.summary = ''
  }
  return days
})
const highlightResources = computed(() => [
  ...(product.value?.resources || []),
  ...(product.value?.included_public_places || []),
])
function itineraryMediaResource(entry: Record<string, any>) {
  if (entry.media_resource) return entry.media_resource
  const resourceType = String(entry.kind || entry.resource_type || 'PARTNER_RESOURCE')
  const resourceId = Number(entry.resource_id || 0)
  const resourceName = String(entry.title || entry.resource_name || '').trim()
  const linkedResource = product.value?.resources.find((resource) => {
    if (resourceId > 0 && [Number(resource.resource_id || 0), Number(resource.id || 0)].includes(resourceId)) return true
    return resource.resource_type === resourceType
      && resource.resource_name.trim().toLocaleLowerCase() === resourceName.toLocaleLowerCase()
  })
  if (linkedResource) {
    return {
      ...linkedResource,
      image_url: entry.image_url || linkedResource.image_url || '',
      image_source: entry.image_source || linkedResource.image_source || '',
      image_attribution: entry.image_attribution || linkedResource.image_attribution || '',
    }
  }
  return {
    id: entry.id || entry.resource_id || 0,
    resource_id: resourceId,
    resource_type: resourceType,
    resource_name: resourceName || '行程体验',
    description: entry.description || '',
    image_url: entry.image_url || '',
    image_source: entry.image_source || '',
    image_attribution: entry.image_attribution || '',
  }
}
const itineraryMediaRefs = computed(() => {
  const refs: Array<{ dayIndex: number; itemIndex: number; resource: TravelProduct['resources'][number] }> = []
  dayPlan.value.forEach((day) => {
    day.items.forEach((entry: Record<string, any>, itemIndex: number) => {
      if (!['PARTNER_RESOURCE', 'PUBLIC_REFERENCE'].includes(String(entry.kind))) return
      refs.push({ dayIndex: Number(day.day_index), itemIndex, resource: itineraryMediaResource(entry) as TravelProduct['resources'][number] })
    })
  })
  return refs
})
const pageMediaPlan = computed(() => {
  const current = product.value
  if (!current) return { highlights: [] as Array<ProductMediaAsset | null>, itinerary: [] as Array<ProductMediaAsset | null>, gallery: [] as Array<ProductMediaAsset | null>, fallback: [] as Array<ProductMediaAsset | null> }
  const highlights = highlightResources.value as Array<TravelProduct['resources'][number]>
  const itinerary = itineraryMediaRefs.value.map((item) => item.resource)
  const galleryResources = gallerySource.value.map((moment) =>
    current.resources.find((item) => item.resource_type === moment.resource_type && item.resource_name === moment.resource_name),
  ).filter((item): item is TravelProduct['resources'][number] => Boolean(item))
  const fallback = current.resources
  return {
    highlights: distinctMediaForResources(current, highlights, [], 3),
    itinerary: distinctMediaForResources(current, itinerary, [], 3),
    gallery: distinctMediaForResources(current, galleryResources, [], 3),
    fallback: distinctMediaForResources(current, fallback, [], 3),
  }
})
function highlightMedia(_item: TravelProduct['resources'][number] | IncludedPublicPlace, index: number) {
  return pageMediaPlan.value.highlights[index] || null
}
function plannedItineraryMedia(dayIndex: number, itemIndex: number) {
  const refIndex = itineraryMediaRefs.value.findIndex((item) => item.dayIndex === dayIndex && item.itemIndex === itemIndex)
  return refIndex >= 0 ? pageMediaPlan.value.itinerary[refIndex] || null : null
}
function plannedFallbackMedia(index: number) {
  return pageMediaPlan.value.fallback[index] || null
}
const gallery = computed(() => gallerySource.value
  .map((moment, index) => ({ ...moment, media: pageMediaPlan.value.gallery[index] || null }))
  .filter((moment): moment is typeof moment & { media: ProductMediaAsset } => Boolean(moment.media)))
const alternatives = ref<{ room_types: Array<Record<string, any>>; same_room_packages: Array<Record<string, any>> }>({ room_types: [], same_room_packages: [] })
const roomOptions = ref<Array<Record<string, any>>>([])
const roomOptionTrack = ref<HTMLElement | null>(null)
const roomCanScrollLeft = ref(false)
const roomCanScrollRight = ref(false)
const dateOptions = ref<Array<Record<string, any>>>([])
const selectedRoomId = ref<number | null>(null)
// 支持用 ?room=<room_inventory_id> 直接打开某个房型（分享链接 / 刷新后保持）。
if (route.query.room) {
  const roomFromQuery = Number(route.query.room)
  if (Number.isFinite(roomFromQuery) && roomFromQuery > 0) selectedRoomId.value = roomFromQuery
}
const roomSwitching = ref(false)
const soldOut = computed(() => !previewMode.value && Number(product.value?.sale_quantity || 0) <= 0)
const soldOutDateLabel = computed(() => `${targetDateLabel.value}已售罄`)
const hasAvailableOtherDate = computed(() => dateOptions.value.some((item) => Number(item.sale_quantity || 0) > 0 && item.id !== product.value?.id))
const hasAvailableAlternatives = computed(() =>
  hasAvailableOtherDate.value || [...alternatives.value.room_types, ...alternatives.value.same_room_packages].some((item) => Number(item.sale_quantity || 0) > 0),
)
const roomFeatures = computed(() => {
  const room = product.value?.resources.find((item) => item.resource_type === 'ROOM')
  return String(room?.description || '')
})
const photoResource = computed(() => product.value?.resources.find((item) => /旅拍|摄影|拍照/.test(`${item.resource_name} ${item.description || ''}`)))
const related = ref<TravelProduct[]>([])
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
const heroIndex = ref(0)
// 当前房型的实拍主图排在最前：切换房型时第一张图会立刻换成该房型，
// 图库与亮点内容也随 product 一起刷新，不需要整页重载。
const heroMediaList = computed(() => {
  const current = product.value
  if (!current) return mediaForProduct(null)
  const focus = current.resources.find((item) => item.resource_type === 'PARTNER_RESOURCE')
    || current.resources.find((item) => item.resource_type === 'PUBLIC_REFERENCE')
    || current.resources.find((item) => item.resource_type === 'ROOM')
  const matched = focus ? mediaCandidatesForResource(current, focus) : []
  const candidates = matched.length ? matched : [primaryProductMedia(current)]
  return candidates
    .filter((item, index, rows) => rows.findIndex((candidate) => candidate.url === item.url) === index)
    .slice(0, 6)
})
const hero = computed(() => heroMediaList.value[heroIndex.value] || heroMediaList.value[0] || primaryProductMedia(product.value))
const heroTotal = computed(() => Math.max(1, heroMediaList.value.length))
const heroRef = ref<HTMLElement | null>(null)
const heroVisible = ref(true)
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
  { id: 'guides', label: '附近可选' },
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
  window.removeEventListener('scroll', updatePurchaseBarVisibility)
  window.addEventListener('scroll', updateAnchorFromScroll, { passive: true })
  window.addEventListener('scroll', updatePurchaseBarVisibility, { passive: true })
  updateAnchorFromScroll()
  updatePurchaseBarVisibility()
}
function scrollToSection(id: string) {
  const element = document.getElementById(id)
  if (!element) return
  activeSection.value = id
  const top = element.getBoundingClientRect().top + window.scrollY - 104
  window.scrollTo({ top, behavior: 'smooth' })
}
function scrollToAlternatives() {
  document.getElementById('purchase-options')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
function updateRoomScrollButtons() {
  const track = roomOptionTrack.value
  if (!track) {
    roomCanScrollLeft.value = false
    roomCanScrollRight.value = false
    return
  }
  const maxScroll = Math.max(0, track.scrollWidth - track.clientWidth)
  roomCanScrollLeft.value = track.scrollLeft > 2
  roomCanScrollRight.value = track.scrollLeft < maxScroll - 2
}
function scrollRoomOptions(direction: -1 | 1) {
  const track = roomOptionTrack.value
  if (!track) return
  const card = track.querySelector<HTMLElement>('.room-choice__options button')
  const gap = Number.parseFloat(window.getComputedStyle(track).columnGap || '10') || 10
  const distance = card ? card.getBoundingClientRect().width + gap : track.clientWidth * 0.8
  track.scrollBy({ left: direction * distance, behavior: 'smooth' })
  window.setTimeout(updateRoomScrollButtons, 240)
}
function updatePurchaseBarVisibility() {
  const heroBounds = heroRef.value?.getBoundingClientRect()
  // Keep the fixed purchase bar out of the first screen; show it only after
  // the complete product summary has scrolled above the visitor header.
  heroVisible.value = !heroBounds || heroBounds.bottom > 78
}

// 可住人数取自客房本身（max_guests），不再用同行人数，避免「最多 2 人」和房型「可住 3 人」打架。
const roomMaxGuests = computed(() => {
  const current = roomOptions.value.find((item) => item.room_inventory_id === (product.value?.room_inventory_id || null))
  return Number(current?.max_guests || product.value?.party_size || 2)
})
const FILLER_COPY = /不用把一天排满|把这段体验慢慢安排进你的杭州行程|把杭州的一段时光留给今天|把这段杭州时光留给周末|住进杭州，慢慢体验这座城市的另一面/i

function usefulCopy(value: unknown, fallback = '') {
  const text = publicTravelCopy(value, '')
  if (!text) return fallback
  const segments = text.match(/[^。！？!?]+[。！？!?]?/g) || []
  const useful = segments.filter((segment) => !FILLER_COPY.test(segment)).join('').trim()
  return useful.length >= 6 ? useful : fallback
}

const roomResource = computed(() => product.value?.resources.find((item) => item.resource_type === 'ROOM'))
const hotelAddressLabel = computed(() => cleanHotelAddress(stay.value?.hotel_address || roomResource.value?.address || ''))
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
const purchaseIncludes = computed(() => {
  const nightsCount = stay.value?.nights || 1
  const room = roomResource.value?.resource_name || stay.value?.room_name || '酒店住宿'
  const experiences = experienceResources.value.slice(0, 2).map((item) => item.resource_name).filter(Boolean)
  return [`${room} ${nightsCount}晚`, ...experiences].join(' · ')
})
// Show paid package entitlements separately from included free public routes.
const feeResources = computed(() => (product.value?.resources || []).filter((item) => item.resource_type === 'PARTNER_RESOURCE'))
const feeHotelServices = computed(() => (product.value?.resources || []).filter((item) => item.resource_type === 'HOTEL_SERVICE'))
const feePublicStops = computed(() => product.value?.included_public_places || [])
const earliestExperience = computed(() => {
  const times = [
    ...experienceResources.value.map((resource) => resource.start_time),
    ...(product.value?.included_public_places || []).map((stop) => stop.start_time),
  ].filter(Boolean).map((time) => String(time).slice(0, 5)).sort()
  return times[0] || ''
})
function guideDurationLabel(guide: Record<string, any>) {
  const minutes = Number(guide.suggested_duration_minutes || 0)
  if (!minutes) return ''
  if (minutes % 60 === 0) return String(minutes / 60) + ' 小时'
  if (minutes < 60) return String(minutes) + ' 分钟'
  return String(Math.floor(minutes / 60)) + ' 小时 ' + String(minutes % 60) + ' 分钟'
}

function guideRecommendedTime(guide: Record<string, any>) {
  const explicit = String(guide.best_time || '').trim()
  if (explicit) return explicit
  const notes = String(guide.reservation_notice || '') + ' ' + String(guide.content || guide.summary || '')
  const hint = notes.match(/(?:建议|推荐)(?:在)?(?:开馆后|开门后|上午|下午|傍晚|晚间)[^。；;]*/)
  if (hint?.[0]) return hint[0]
  const duration = guideDurationLabel(guide)
  if (guide.opening_hours && duration) return `建议在开放时段前段到访，预留约 ${duration}，避免临近停止入场时赶行程。`
  if (guide.opening_hours) return '建议在开放时段前段到访，并预留充足游览时间。'
  return '出发前查看地点当日开放安排，再选择合适时段。'
}

function guideHowToGo(guide: Record<string, any>) {
  const transport = String(guide.transport || '').trim()
  if (transport) return transport
  const address = String(guide.address || '').trim()
  return address
    ? `按此地址导航至${address}；公交、驾车或步行路线可根据你的出发位置实时规划。`
    : '在地图中搜索地点名称，并按你的出发位置规划路线。'
}

function guideMapUrl(guide: Record<string, any>) {
  const keyword = [guide.title, guide.address].filter(Boolean).join(' ')
  return `https://uri.amap.com/search?keyword=${encodeURIComponent(keyword)}&city=${encodeURIComponent('杭州')}`
}

const guideQuery = computed(() => {
  if (!product.value) return '杭州旅行'
  // 参考路线跟着这套产品实际的体验地点走，而不是泛泛地搜「杭州」。
  const names = experienceResources.value.slice(0, 3).map((item) => item.resource_name).filter(Boolean)
  const places = addressList.value.slice(0, 2)
  // The API validates query <= 80 and near <= 120. Longer composed metadata
  // used to fail the nearby-knowledge request with a 422 response.
  return [product.value.theme, ...names, ...places].filter(Boolean).join(' ').slice(0, 80)
})
async function loadNearbyGuides() {
  const includedNames = new Set([
    ...(product.value?.resources || []).map((resource) => String(resource.resource_name || '')),
    ...(product.value?.included_public_places || []).map((stop) => String(stop.resource_name || '')),
  ].map((name) => name.replace(/[\s·｜|]/g, '').toLowerCase()).filter(Boolean))
  const near = addressList.value.slice(0, 2).join(' ').slice(0, 120)
  const queries = [...new Set([guideQuery.value, '杭州 博物馆 公园 城市漫步 展览 亲子体验'])]
  const fetched: Array<Record<string, any>> = []
  const uniqueGuides = () => {
    const byTitle = new Map<string, Record<string, any>>()
    fetched.forEach((row) => { if (row.title) byTitle.set(String(row.title), row) })
    return [...byTitle.values()]
  }
  for (const query of queries) {
    try {
      const rows = (await visitorApi.guides(query.slice(0, 80), near)).data as Array<Record<string, any>>
      fetched.push(...rows)
    } catch {
      // Try the broader knowledge-base query before hiding the recommendations.
    }
    const optional = uniqueGuides().filter((row) => !includedNames.has(String(row.title || row.name || '').replace(/[\s·｜|]/g, '').toLowerCase()))
    if (optional.length >= 4) break
  }
  const unique = uniqueGuides()
  const optional = unique.filter((row) => !includedNames.has(String(row.title || row.name || '').replace(/[\s·｜|]/g, '').toLowerCase()))
  // If every returned place is already a formal route stop, still keep useful
  // knowledge cards visible instead of rendering an empty recommendation area.
  guides.value = (optional.length ? optional : unique).slice(0, 4)
}
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

function resourceSummary(item: TravelProduct['resources'][number]) {
  const description = usefulCopy(item.description, '')
  if (description) return description
  const time = item.start_time && item.end_time ? `，${item.start_time.slice(0, 5)}–${item.end_time.slice(0, 5)}` : ''
  if (item.resource_type === 'ROOM') return `${item.resource_name} · ${stay.value?.nights || 1}晚住宿 · ${item.quantity_per_package}间。`
  if (item.resource_type === 'HOTEL_SERVICE') return `${item.resource_name}，酒店内使用${time}。`
  return `${item.resource_name}${item.address ? ` · ${item.address}` : ''}${time}。`
}

function highlightCopy(item: TravelProduct['resources'][number] | IncludedPublicPlace) {
  const description = usefulCopy(item.description, '')
  const sentences = description.match(/[^。！？!?]+[。！？!?]?/g) || []
  const usefulDescription = sentences.slice(0, 2).join('').trim()
  if (item.resource_type === 'ROOM') {
    const feature = usefulDescription || '为当天的游玩留出休息和整理行李的空间。'
    return `${stay.value?.nights || 1} 晚住宿 · ${feature}`
  }
  if (item.resource_type === 'HOTEL_SERVICE') {
    return usefulDescription || `入住期间可使用${item.resource_name}，方便衔接当天的体验安排。`
  }
  if (usefulDescription.length >= 18) return usefulDescription
  const name = String(item.resource_name || '')
  const intro = usefulDescription.replace(/[。；;!?！？]+$/g, '').trim()
  if (/陶艺|陶杯|陶瓷/.test(name)) return [intro, `在工作室参与陶艺手作，适合${crowdLabel.value}把一段共同体验安排进旅程`].filter(Boolean).join('。') + '。'
  if (/甜品|烘焙|蛋糕/.test(name)) return [intro, '一起参与甜品手作，让亲子或朋友同行有一项可以共同完成的体验'].filter(Boolean).join('。') + '。'
  if (/运动馆|攀岩|卡丁车|运动/.test(name)) return [intro, '把一段有明确场地和时段的运动体验加入行程，适合想增加活动量的同行者'].filter(Boolean).join('。') + '。'
  if (/乐园|游乐|儿童剧/.test(name)) return [intro, '为亲子同行保留一段集中游玩的时间，具体项目以套餐列明权益为准'].filter(Boolean).join('。') + '。'
  if (item.resource_type === 'PUBLIC_REFERENCE') return usefulDescription || `将${name}作为这次行程中的正式公共游览安排。`
  return usefulDescription || `前往${name}参与套餐列明的体验。`
}

function resourceMeta(item: TravelProduct['resources'][number]) {
  const place = item.address || (item.resource_type === 'ROOM' || item.resource_type === 'HOTEL_SERVICE' ? '酒店内' : '杭州')
  const time = item.start_time && item.end_time ? item.start_time.slice(0, 5) + ' – ' + item.end_time.slice(0, 5) : ''
  return [place, time].filter(Boolean).join(' · ')
}

function itineraryTime(item: TravelProduct['resources'][number]) {
  if (item.start_time && item.end_time) return `${item.start_time.slice(0, 5)} – ${item.end_time.slice(0, 5)}`
  if (item.resource_type === 'ROOM') return '入住与退房时间以订单确认为准'
  if (item.resource_type === 'HOTEL_SERVICE') return '酒店内使用'
  return '时间以订单确认为准'
}

function itineraryAction(item: TravelProduct['resources'][number]) {
  if (item.resource_type === 'ROOM') return `办理入住 · ${item.resource_name}含一晚住宿`
  if (item.resource_type === 'HOTEL_SERVICE') return `酒店内使用 · ${item.resource_name}`
  return item.address ? `体验地点：${item.address}` : '体验地点以订单确认为准'
}

async function load() {
  loading.value = true
  try {
    if (hotelContext.value) {
      // 内部预览必须能看到草稿与已售罄商品，公开接口会把这些过滤掉。
      product.value = (await hotelApi.product(Number(route.params.id))).data
      await loadNearbyGuides()
      alternatives.value = { room_types: [], same_room_packages: [] }
      related.value = []
      roomOptions.value = []
      dateOptions.value = []
      return
    }
    product.value = (await visitorApi.product(Number(route.params.id), nights.value, selectedRoomId.value)).data
    await loadNearbyGuides()
    if (previewMode.value) {
      alternatives.value = { room_types: [], same_room_packages: [] }
      related.value = []
      roomOptions.value = []
      dateOptions.value = []
    } else {
      alternatives.value = (await visitorApi.productAlternatives(Number(route.params.id))).data
      const sameDay = await visitorApi.products({ target_date: product.value?.target_date, compact: true })
      related.value = sameDay.data.filter((item) => item.id !== product.value?.id).slice(0, 4)
      roomOptions.value = (await visitorApi.productRooms(Number(route.params.id))).data.rooms
      try { dateOptions.value = (await visitorApi.productDates(Number(route.params.id))).data.dates } catch { dateOptions.value = [] }
    }
  }
  catch (e) { showToast(errorMessage(e)) }
  finally { loading.value = false }
}

async function chooseRoom(option: Record<string, any>) {
  if (!option.available) { showToast('该房型当天已售罄，请选择其他房型'); return }
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
  if (Number(option.sale_quantity || 0) <= 0) return
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
watch(roomOptions, async () => {
  await nextTick()
  updateRoomScrollButtons()
}, { deep: true, flush: 'post' })
watch(product, async (value, previous) => {
  if (value && (value.id !== previous?.id || value.room_inventory_id !== previous?.room_inventory_id)) {
    await nextTick()
    setupAnchorSpy()
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
onBeforeUnmount(() => {
  window.removeEventListener('scroll', updateAnchorFromScroll)
  window.removeEventListener('scroll', updatePurchaseBarVisibility)
})
</script>

<template>
  <div v-if="loading" class="detail-loading"><span /> 正在打开这段杭州体验…</div>
  <div v-else-if="product" class="visitor-product-detail" :class="{ 'is-embedded-preview': embeddedMode }">
    <div v-if="hotelContext && !embeddedMode" class="internal-preview-banner">酒店内部预览 · 展示候选商品内容与当前库存状态</div>
    <div v-else-if="previewMode && !embeddedMode" class="preview-mode-banner"><b>游客端效果预览</b><router-link to="/hotel/products/generate">返回产品方案</router-link></div>
    <div class="detail-purchase-layout">
    <div class="product-detail-card">
    <section ref="heroRef" class="product-detail-hero" @touchstart.passive="onSwipeStart" @touchend.passive="onSwipeEnd">
      <MediaImage :media="hero" aspect="hero" eager />
      <div class="product-detail-hero__veil" />
      <router-link v-if="!embeddedMode" :to="previewMode ? '/hotel/products/generate' : '/visitor/products'" class="back-to-list">{{ hotelContext ? '← 返回候选工作台' : previewMode ? '← 返回方案' : '← 返回体验列表' }}</router-link>
      <div v-if="!previewMode" class="hero-actions" aria-label="商品操作">
        <button type="button" :aria-label="favorite ? '取消收藏' : '收藏商品'" @click.stop="favorite = !favorite">{{ favorite ? '♥' : '♡' }}</button>
      </div>
      <span class="hero-counter">{{ heroIndex + 1 }} / {{ heroTotal }}</span>
      <button v-if="heroTotal > 1" type="button" class="hero-nav hero-nav--prev" aria-label="上一张图片" @click.stop="moveHero(-1)">‹</button>
      <button v-if="heroTotal > 1" type="button" class="hero-nav hero-nav--next" aria-label="下一张图片" @click.stop="moveHero(1)">›</button>
      <div v-if="heroTotal > 1" class="hero-dots" aria-label="选择图片"><button v-for="(_, index) in heroMediaList" :key="index" type="button" :class="{ active: heroIndex === index }" :aria-label="`第 ${index + 1} 张图片`" @click.stop="heroIndex = index"></button></div>
    </section>

    <section class="commerce-summary">
      <div class="commerce-head">
        <div class="commerce-title">
          <h1>{{ product.product_name }}</h1>
          <div class="commerce-price"><strong>¥{{ stayPrice }}</strong><span>/ 套</span></div>
          <p>{{ publicTitle }}</p>
          <div class="commerce-tags"><span>{{ crowdLabel }}</span><span>{{ stayLabel }}</span></div>
        </div>
      </div>
      <div class="commerce-inclusion"><span>套餐包含</span><strong>{{ purchaseIncludes }}</strong></div>
      <div id="purchase-options" class="date-picker-row">
        <b>入住日期</b>
        <button v-for="d in dateOptions" :key="d.id" type="button" :disabled="d.sale_quantity <= 0" :aria-label="`${Number(d.target_date.slice(5, 7))}月${Number(d.target_date.slice(8, 10))}日${d.sale_quantity > 0 ? `剩${d.sale_quantity}套` : '已售罄'}`" :class="['date-chip', { active: d.id === product.id, 'is-sold-out': d.sale_quantity <= 0 }]" @click="chooseDate(d)">
          <strong>{{ Number(d.target_date.slice(5, 7)) }}月{{ Number(d.target_date.slice(8, 10)) }}日</strong><small>{{ d.sale_quantity > 0 ? `剩 ${d.sale_quantity} 套` : '已售罄' }}</small>
        </button>
        <span v-if="!dateOptions.length" class="date-chip active"><strong>{{ targetDateLabel }}</strong><small>{{ previewMode ? '预览中' : product.sale_quantity > 0 ? `剩 ${product.sale_quantity} 套` : soldOutDateLabel }}</small></span>
      </div>
      <div v-if="roomOptions.length" class="room-choice-inline">
        <div class="room-choice-inline__head">
          <span class="section-kicker">选择房型 <small>同一套餐可换房型</small></span>
          <div v-if="roomOptions.length > 1" class="room-choice-inline__arrows" aria-label="房型选择导航">
            <button type="button" aria-label="向左选择房型" :disabled="!roomCanScrollLeft" @click="scrollRoomOptions(-1)">‹</button>
            <button type="button" aria-label="向右选择房型" :disabled="!roomCanScrollRight" @click="scrollRoomOptions(1)">›</button>
          </div>
        </div>
        <div ref="roomOptionTrack" class="room-choice-inline__track room-choice__options" @scroll.passive="updateRoomScrollButtons">
          <button v-for="item in roomOptions" :key="item.room_inventory_id" type="button" :disabled="!item.available" :class="{ disabled: !item.available, active: item.room_inventory_id === product.room_inventory_id }" @click="chooseRoom(item)">
            <b>{{ item.room_type }}</b>
            <span class="room-choice-inline__summary"><strong>¥{{ item.price }}</strong><small>{{ item.available ? `剩 ${item.sale_quantity} 套` : '已售罄' }}</small></span>
          </button>
        </div>
      </div>
      <p v-if="soldOut" class="soldout-inline"><strong>{{ soldOutDateLabel }}</strong><button v-if="hasAvailableAlternatives" type="button" @click="scrollToAlternatives">查看可售方案</button></p>
      <p class="commerce-stay-note">{{ stayLabel }} · {{ stayRange }} · {{ crowdLabel }}</p>
      <div v-if="!previewMode" class="commerce-purchase-actions">
        <button type="button" class="commerce-assistant-link" @click="router.push({ path: '/visitor/assistant', query: { product: String(product.id) } })">问问这趟行程</button>
        <el-button v-if="product.sale_quantity > 0" type="primary" @click="openIntent">立即购买</el-button>
        <el-button v-else type="primary" @click="scrollToAlternatives">查看可售方案</el-button>
      </div>
    </section>
    </div>
    </div>

    <nav class="detail-anchor-nav" aria-label="商品章节导航"><button v-for="item in anchorSections" :key="item.id" type="button" :class="{ active: activeSection === item.id }" @click="scrollToSection(item.id)">{{ item.label }}</button></nav>

    <main class="detail-content" :key="`detail-${product.id}-${product.room_inventory_id}`">
      <section id="highlights" class="commerce-highlight"><div class="section-heading"><div><span class="section-kicker">产品内容</span><h2>套餐包含</h2></div></div><div class="highlight-grid"><article v-for="(item,index) in highlightResources" :key="item.id" tabindex="0" :data-inclusion-kind="item.resource_type === 'PUBLIC_REFERENCE' ? 'included_in_itinerary' : 'included_in_package'"><MediaImage v-if="highlightMedia(item,index)" :media="highlightMedia(item,index)!" aspect="card"/><div v-else class="highlight-image-empty" aria-label="该体验暂无匹配图片">体验图片待补充</div><span class="highlight-type-tag">{{ item.resource_type === 'ROOM' ? '住宿' : item.resource_type === 'PUBLIC_REFERENCE' ? '正式行程' : '包含体验' }}</span><h3>{{ item.resource_name }}</h3><p>{{ highlightCopy(item) }}</p></article></div></section>

      <section id="itinerary" class="itinerary-section">
        <div class="section-heading">
          <div><span class="section-kicker">行程</span><h2>{{ stayLabel }}行程安排</h2></div>
          <span class="section-count">{{ dayPlan.length < 10 ? '0' + dayPlan.length : dayPlan.length }}</span>
        </div>
        <div v-if="dayPlan.length" class="day-plan-list">
          <article v-for="day in dayPlan" :key="day.day_index" class="day-plan">
            <header class="day-plan__head">
              <div><span class="day-plan__label">{{ day.label }}</span><strong>{{ day.title || (Number(day.day_index) === 1 ? '入住与体验安排' : '继续体验 · 退房返程') }}</strong></div>
              <small>{{ day.date || product.target_date }}</small>
            </header>
            <ol class="day-plan__items">
              <li v-for="(entry, index) in day.items" :key="index" :class="{ 'day-plan__item--free': entry.kind === 'FREE_TIME', 'day-plan__item--formal': ['PARTNER_RESOURCE', 'PUBLIC_REFERENCE'].includes(entry.kind), 'day-plan__item--operation': ['ROOM', 'HOTEL_SERVICE', 'TRANSFER', 'BAGGAGE'].includes(entry.kind) }">
                <span class="day-plan__time"><b>{{ entry.slot_label }}</b><span v-if="entry.time">{{ entry.time }}</span></span>
                <div class="day-plan__entry">
                  <MediaImage
                    v-if="['PARTNER_RESOURCE', 'PUBLIC_REFERENCE'].includes(entry.kind) && plannedItineraryMedia(Number(day.day_index), index)"
                    class="day-plan__entry-image"
                    :media="plannedItineraryMedia(Number(day.day_index), index)!"
                    aspect="card"
                  />
                  <div class="day-plan__entry-copy">
                    <b class="day-plan__title"><span v-if="['ROOM', 'HOTEL_SERVICE'].includes(entry.kind)" class="timeline-operation-icon" aria-hidden="true">⌂</span><span>{{ entry.title }}</span><small v-if="entry.address" class="day-plan__address-inline">{{ entry.address }}</small></b>
                    <p>{{ entry.description }}</p>
                    <div v-if="entry.suggestions?.length" class="day-plan__suggestions">
                      <b>空闲时间可选</b>
                      <p v-for="suggestion in entry.suggestions" :key="suggestion.title"><strong>{{ suggestion.title }}</strong><span>{{ suggestion.detail }}</span></p>
                    </div>
                    <div class="day-plan__meta">
                      <span v-if="entry.duration_text">{{ entry.duration_text }}</span>
                      <span v-if="entry.notes" class="day-plan__note" :class="{ 'day-plan__note--warning': entry.schedule_conflict }">{{ entry.notes }}</span>
                    </div>
                  </div>
                </div>
              </li>
            </ol>
          </article>
        </div>
        <div v-else class="itinerary-list">
          <article v-for="(item, index) in product.resources" :key="item.id" class="itinerary-card">
            <div v-if="plannedFallbackMedia(index)" class="itinerary-card__image"><MediaImage :media="plannedFallbackMedia(index)!" aspect="card" /></div>
            <div class="itinerary-card__body">
              <div class="itinerary-card__top"><span>{{ experienceLabelZh(item.resource_type) }}</span><b>第 {{ index + 1 }} 段</b></div>
              <h3>{{ item.resource_name }}</h3>
              <p>{{ resourceSummary(item) }}</p>
              <strong class="itinerary-card__time">{{ itineraryTime(item) }}</strong>
              <small>{{ itineraryAction(item) }} · {{ resourceMeta(item) }}</small>
            </div>
            <strong class="itinerary-card__quantity">×{{ item.quantity_per_package }}</strong>
          </article>
        </div>
      </section>

        <section id="fees" class="fee-section"><div class="section-heading"><div><span class="section-kicker">价格明细</span><h2>费用说明</h2></div></div><div class="fee-columns"><div><h3>套餐已含</h3><div class="fee-group"><strong>住宿及体验 · 已计入套餐价格</strong><p>✓ {{ stay?.room_name || '酒店住宿' }} × {{ stay?.nights || 1 }} 晚<small>{{ stayRange }}</small></p><p v-for="item in feeResources" :key="'paid'+item.id">✓ {{ item.resource_name }} ×{{ item.quantity_per_package }}<small>{{ resourceMeta(item) }}</small></p><p v-for="item in feeHotelServices" :key="'service'+item.id">✓ {{ item.resource_name }}<small>{{ resourceMeta(item) }}</small></p></div><div v-if="feePublicStops.length" class="fee-group fee-group--public"><strong>正式公共行程 · 已纳入套餐安排</strong><p v-for="stop in feePublicStops" :key="'public'+stop.resource_name">✓ {{ stop.resource_name }}<small>公共开放地点，无需额外门票</small></p></div></div><div><h3>需自理</h3><p>往返交通与停车费用</p><p>套餐外的餐饮和个人消费</p><p>超出套餐数量的加购项目</p></div></div></section><section id="notice" class="notice-section"><div class="section-heading"><div><span class="section-kicker">出行前确认</span><h2>入住与集合</h2></div></div><div class="notice-list"><p><b>入住</b><span>{{ stay?.check_in_time || '13:00' }} 后办理</span></p><p><b>退房</b><span>{{ stay?.check_out_time || '13:00' }} 前</span></p><p><b>首项体验集合</b><span>{{ earliestExperience ? `${earliestExperience} 前抵达集合地点` : '按行程确认集合时间' }}</span></p></div></section>
      <section class="hotel-detail-section">
        <div class="section-heading"><div><span class="section-kicker">住宿</span><h2>酒店与房型</h2></div></div>
        <div class="hotel-detail-grid">
          <div><span>房型</span><strong>{{ roomResource?.resource_name || '酒店客房' }}</strong></div>
          <div><span>可住人数</span><strong>最多 {{ roomMaxGuests }} 人</strong></div>
          <div><span>入住 / 退房</span><strong>{{ stay?.check_in_time || '13:00' }} 后 / {{ stay?.check_out_time || '13:00' }} 前</strong></div>
          <div v-if="hotelAddressLabel" class="full"><span>酒店地址</span><strong>{{ hotelAddressLabel }}</strong></div>
          <div class="full"><span>房型说明</span><strong>{{ roomFeatureNames || roomFeatures || '具体房内设施以酒店实际房型为准。' }}</strong></div>
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

      <section id="guides" class="guide-source-section">
        <div class="section-heading"><div><span class="section-kicker">周边推荐</span><h2>附近可选</h2></div></div>
        <div v-if="guides.length" class="guide-list">
          <article v-for="guide in guides" :key="guide.source + guide.title" data-inclusion-kind="optional_nearby">
            <header>
              <strong>{{ guide.title }}<span v-if="guide.category_label"> | {{ guide.category_label }}</span></strong>
              <span class="guide-exclusion">{{ guide.is_remote ? '远程备选' : '不含套餐' }}</span>
            </header>
            <p v-if="guide.distance_note || guide.verification_note" class="guide-distance-note">{{ guide.distance_note }}<template v-if="guide.verification_note">{{ guide.distance_note ? ' ' : '' }}{{ guide.verification_note }}</template></p>
            <p class="guide-content">{{ guide.content || guide.summary || '可按开放时段安排短途游览。' }}</p>
            <ul class="guide-facts">
              <li v-if="guide.crowds_label"><b>适合人群</b>{{ guide.crowds_label }}</li>
              <li><b>推荐时段</b>{{ guideRecommendedTime(guide) }}</li>
              <li v-if="guideDurationLabel(guide)"><b>建议停留</b>约 {{ guideDurationLabel(guide) }}</li>
              <li v-if="guide.address" class="guide-address"><b>地址</b><span>{{ guide.address }}</span><a :href="guideMapUrl(guide)" target="_blank" rel="noopener noreferrer">地图路线 ↗</a></li>
              <li v-if="guide.opening_hours"><b>开放时间</b>{{ guide.opening_hours }}</li>
              <li v-if="guide.reservation_notice"><b>预约提示</b>{{ guide.reservation_notice }}</li>
              <li class="guide-how-to"><b>怎么去</b><span>{{ guideHowToGo(guide) }}</span></li>
            </ul>
          </article>
        </div>
        <p v-else class="guide-empty">附近暂无可展示的推荐地点。</p>
      </section>

      <section v-if="previewMode && gallery.length" class="moments-section">
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

    <section v-if="!previewMode && !heroVisible" class="booking-bar">
      <div class="booking-bar__left"><div class="booking-bar__price"><strong>¥{{ stayPrice }}</strong><span>/ 套</span></div><span class="booking-bar__stock">{{ product.sale_quantity > 0 ? `余 ${product.sale_quantity} 套` : soldOutDateLabel }}</span></div>
      <div class="booking-bar__right"><button class="assistant-action" @click="router.push({ path: '/visitor/assistant', query: { product: String(product.id) } })">问问这趟行程</button><el-button type="primary" @click="product.sale_quantity > 0 ? openIntent() : scrollToAlternatives()">{{ product.sale_quantity > 0 ? '立即购买' : '查看可售方案' }}</el-button></div>
    </section>

    <el-dialog v-model="intentDialog" title="购买信息" width="min(94vw, 520px)"><el-form label-position="top"><el-form-item label="联系人" required><el-input v-model="form.contact_name" placeholder="怎么称呼" /></el-form-item><el-form-item label="联系电话" required><el-input v-model="form.contact_phone" placeholder="便于酒店联系确认" /></el-form-item><el-form-item label="备注"><el-input v-model="form.natural_language" type="textarea" :rows="3" maxlength="300" show-word-limit placeholder="到店时间、同行人或其他需要说明的情况，可以不填" /></el-form-item></el-form><div class="intent-summary"><span>{{ product.product_name }}</span><span>{{ stayLabel }}</span><span>¥{{ stayPrice }}</span></div><template #footer><el-button @click="intentDialog = false">取消</el-button><el-button type="primary" :loading="intentLoading" @click="submitIntent">提交购买</el-button></template></el-dialog>

  </div>
  <div v-else class="home-empty">
    <div class="empty-mark" aria-hidden="true"><svg viewBox="0 0 48 48"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></div>
    <h3>{{ hotelContext ? '商品详情暂时无法打开' : soldOutDateLabel }}</h3>
    <p>{{ hotelContext ? '请返回候选列表重试预览，商品草稿和资源信息仍保留。' : '同一天的其他房型或体验搭配还有余量，回到列表可以按主题筛选。' }}</p>
    <el-button type="primary" @click="$router.push(hotelContext ? '/hotel/products/generate' : '/visitor/products')">{{ hotelContext ? '返回候选工作台' : '查看同一天的其他方案' }}</el-button>
  </div>
</template>

<style scoped>
.visitor-product-detail{padding-bottom:86px}.detail-loading{min-height:300px;display:grid;place-items:center;color:var(--muted);font-size:14px}.detail-loading span{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--teal);box-shadow:14px 0 var(--gold),28px 0 var(--teal);margin-right:38px;animation:stay-breathe 1.2s infinite alternate}.product-detail-hero{position:relative;min-height:318px;border-radius:16px;overflow:hidden;background:#173b35;color:#fff}.product-detail-hero>.media-image{position:absolute;inset:0;min-height:100%;border-radius:inherit}.product-detail-hero__veil{position:absolute;inset:0;background:linear-gradient(90deg,rgba(12,39,34,.82),rgba(12,39,34,.2) 75%),linear-gradient(0deg,rgba(12,39,34,.65),transparent 52%)}.back-to-list{position:absolute;z-index:2;top:14px;left:14px;padding:6px 9px;border:1px solid rgba(255,255,255,.42);border-radius:999px;background:rgba(0,0,0,.16);color:#fff;font-size:11px}.product-detail-hero__content{position:absolute;z-index:2;left:5%;right:18%;bottom:30px;max-width:700px}.hero-kicker,.section-kicker{display:inline-flex;align-items:center;gap:8px;color:#23796c;font-size:11px;font-weight:700;letter-spacing:.08em}.hero-kicker{color:rgba(255,255,255,.9)}.hero-kicker i{width:3px;height:3px;border-radius:50%;background:currentColor}.product-detail-hero h1{margin:9px 0 7px;font-size:clamp(27px,3.3vw,40px);line-height:1.13;letter-spacing:-.8px}.product-detail-hero p{max-width:600px;margin:0;color:rgba(255,255,255,.88);font-size:13px;line-height:1.62}.hero-price{position:absolute;z-index:2;right:5%;bottom:29px;text-align:right}.hero-price strong{display:block;font-size:27px;line-height:1;color:#fff}.hero-price span{display:block;margin-top:5px;color:rgba(255,255,255,.78);font-size: 11.5px}.trip-strip{display:grid;grid-template-columns:repeat(3,1fr);margin:10px 0 0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}.trip-strip>div{min-width:0;padding:11px 14px;border-right:1px solid var(--line)}.trip-strip>div:last-child{border-right:0}.trip-strip span{display:block;margin-bottom:4px;color:var(--muted);font-size: 11.5px}.trip-strip strong{display:block;overflow:hidden;color:var(--ink);font-size:13px;text-overflow:ellipsis;white-space:nowrap}.detail-content{max-width:960px;margin:0 auto;padding:26px 3% 14px}.compact-story,.itinerary-section,.moments-section{margin-bottom:26px}.section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:12px}.section-heading h2,.travel-note-heading h2,.share-copy h2,.concierge-header h2{margin:5px 0 0;color:var(--ink);font-family:var(--font-sans);font-size:21px;font-weight:680;line-height:1.22}.section-count{color:#aac8be;font-family:var(--font-mono);font-size:18px;line-height:1}.story-lead{max-width:760px;margin:0;color:var(--ink);font-size:14px;line-height:1.72}.story-note{max-width:720px;margin:8px 0 0;color:var(--muted);font-size:12px;line-height:1.62}.story-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.story-tags span{padding:5px 8px;border-radius:999px;background:#eff7f3;color:#2b7569;font-size: 11.5px}.itinerary-list{display:grid;gap:7px}.itinerary-card{position:relative;display:grid;grid-template-columns:118px minmax(0,1fr) auto;gap:11px;align-items:stretch;min-height:112px;padding:7px;border:1px solid var(--line);border-radius:12px;background:#fff;box-shadow:0 4px 13px rgba(35,64,55,.03)}.itinerary-card__image,.itinerary-card__image .media-image{height:96px;border-radius:8px;overflow:hidden}.itinerary-card__body{min-width:0;padding:1px 0}.itinerary-card__top{display:flex;align-items:center;justify-content:space-between;gap:8px}.itinerary-card__top span{padding:3px 6px;border-radius:999px;background:#edf7f2;color:#287567;font-size: 11px;font-weight:700}.itinerary-card__top b{color:#9aafa7;font-size: 11px;font-weight:500}.itinerary-card h3{overflow:hidden;margin:5px 0 3px;color:var(--ink);font-size:14px;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}.itinerary-card p{display:-webkit-box;overflow:hidden;margin:0;color:#576963;font-size:11px;line-height:1.48;-webkit-box-orient:vertical;-webkit-line-clamp:2}.itinerary-card small{display:block;overflow:hidden;margin-top:5px;color:#93a19b;font-size: 11px;text-overflow:ellipsis;white-space:nowrap}.itinerary-card__quantity{align-self:start;padding:4px 3px 0 0;color:#597a70;font-size:11px}.moments-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.moments-grid figure{margin:0;overflow:hidden;border:1px solid var(--line);border-radius:11px;background:#fff}.moments-grid .media-image{height:148px}.moments-grid figcaption{padding:8px}.moments-grid figcaption span{display:block;overflow:hidden;color:#7e9690;font-size: 11px;text-overflow:ellipsis;white-space:nowrap}.moments-grid figcaption strong{display:block;overflow:hidden;margin-top:3px;color:var(--ink);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.travel-note-section{display:grid;grid-template-columns:170px minmax(0,1fr);gap:22px;margin:0 0 24px;padding:17px 18px;border-radius:13px;background:#f0f7f3}.travel-note-heading h2{font-size:19px}.travel-note-heading button{margin-top:9px;padding:0 0 3px;border:0;border-bottom:1px solid #438b7c;background:transparent;color:#317a6d;font-size:11px;cursor:pointer}.travel-note-copy{padding-top:1px}.travel-note-copy p{margin:0;color:#40544d;font-size:12px;line-height:1.6}.travel-note-copy p.first{margin-bottom:5px;color:var(--ink);font-size:14px;font-weight:650}.travel-note-copy p.hashtag{color:#338070;font-size: 11.5px}.share-section{display:grid;grid-template-columns:108px minmax(0,1fr);gap:16px;align-items:center;margin:0 0 24px;padding:12px 14px;border:1px solid var(--line);border-radius:13px;background:#fff}.poster-preview{padding:5px;border:0;border-radius:8px;background:#163d36;box-shadow:0 6px 14px rgba(24,61,54,.16);cursor:pointer}.poster-preview img{display:block;width:100%;height:auto;border-radius:4px}.share-copy h2{font-size:20px}.share-copy p{max-width:560px;margin:7px 0 0;color:var(--muted);font-size:11px;line-height:1.55}.share-actions{display:flex;gap:7px;margin-top:9px}.concierge-section{padding:17px 18px;border:1px solid #d9ebe3;border-radius:13px;background:linear-gradient(135deg,#f5faf7,#eef7f2)}.concierge-header h2{font-size:20px}.concierge-header p{margin:6px 0 0;color:var(--muted);font-size:11px;line-height:1.55}.concierge-quick{display:flex;gap:6px;flex-wrap:wrap;margin:11px 0}.concierge-quick button,.chat-followups button{padding:6px 8px;border:1px solid #cfe4db;border-radius:999px;background:#fff;color:#3a7166;font-size: 11.5px;cursor:pointer}.concierge-chat{display:grid;gap:7px;max-height:230px;overflow:auto;margin:10px 0}.concierge-bubble{max-width:83%;padding:9px 10px;border-radius:5px 11px 11px;background:#fff;color:#3e534c;font-size:11px;line-height:1.55;box-shadow:0 3px 9px rgba(27,77,63,.05)}.concierge-bubble.is-user{justify-self:end;border-radius:11px 5px 11px 11px;background:#dceee7;color:#1f4e43}.chat-suggestions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));margin-top:8px}.chat-suggestions .product-card{background:#fff}.chat-followups{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}.concierge-input{display:flex;gap:7px}.booking-bar{position:sticky;bottom:10px;z-index:11;display:flex;align-items:center;justify-content:space-between;gap:12px;max-width:960px;margin:0 auto;padding:11px 14px;border:1px solid #dce8e2;border-radius:12px;background:rgba(255,255,255,.96);box-shadow:0 8px 24px rgba(33,67,57,.13);backdrop-filter:blur(10px)}.booking-bar p{margin:3px 0 0;color:var(--muted);font-size:11px}.booking-bar__right{display:flex;align-items:center;gap:6px;white-space:nowrap}.booking-bar__right strong{color:#1c685a;font-family:var(--font-mono);font-size:20px}.booking-bar__right span{margin-right:3px;color:var(--muted);font-size: 11.5px}.poster-dialog__image{display:block;width:100%;max-height:72vh;object-fit:contain;margin:0 auto;border-radius:6px;background:#edf4f0}.form-tip{margin-top:7px;color:var(--muted);font-size:12px;line-height:1.6}.intent-summary{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}.intent-summary span{padding:7px 10px;border-radius:999px;background:#edf7f2;color:var(--teal-dark);font-size:12px}.age-row{display:flex;gap:8px;flex-wrap:wrap}.age-row :deep(.el-input-number){width:92px}.safety-callout{margin-top:12px;padding:11px 13px;border-radius:10px;background:#fff8eb;color:#8b6a36;font-size:12px;line-height:1.6}.home-empty{text-align:center;padding:75px 24px;border:1px solid var(--line);background:#fff}.empty-mark{display:grid;place-items:center;width:42px;height:42px;margin:0 auto 14px;border-radius:14px;background:var(--teal);color:#fff;font-family:Georgia,serif;font-size:25px}.home-empty h3{margin:10px 0;color:var(--ink);font-family:Georgia,serif;font-size:24px;font-weight:500}.home-empty p{color:var(--muted);font-size:13px;line-height:1.8}.home-empty .el-button{margin-top:12px}@keyframes stay-breathe{to{transform:translateX(7px);opacity:.5}}@media(max-width:800px){.visitor-product-detail{padding-bottom:76px}.product-detail-hero{min-height:260px;border-radius:12px}.back-to-list{top:10px;left:10px;font-size: 11.5px}.product-detail-hero__content{right:14px;bottom:15px;left:14px}.product-detail-hero h1{margin:7px 0 5px;font-size:25px;letter-spacing:-.5px}.product-detail-hero p{font-size:11px;line-height:1.45}.hero-price{right:13px;bottom:15px}.hero-price strong{font-size:20px}.trip-strip{margin-top:8px;border-radius:10px}.trip-strip>div{padding:8px 7px}.trip-strip span{font-size: 11px}.trip-strip strong{font-size: 11.5px}.detail-content{padding:20px 0 10px}.compact-story,.itinerary-section,.moments-section{margin-bottom:22px}.section-heading{margin-bottom:10px}.section-heading h2,.travel-note-heading h2,.share-copy h2,.concierge-header h2{font-size:19px}.section-count{font-size:16px}.story-lead{font-size:13px;line-height:1.62}.story-note{font-size:11px;line-height:1.52}.story-tags{margin-top:8px}.itinerary-list{gap:6px}.itinerary-card{grid-template-columns:86px minmax(0,1fr) 18px;gap:7px;min-height:92px;padding:5px;border-radius:10px}.itinerary-card__image,.itinerary-card__image .media-image{height:80px;border-radius:7px}.itinerary-card__body{padding:1px 0}.itinerary-card__top span{padding:2px 5px;font-size: 11.5px}.itinerary-card h3{margin:4px 0 2px;font-size:13px}.itinerary-card p{font-size: 11.5px;line-height:1.38}.itinerary-card small{margin-top:4px;font-size: 11.5px}.itinerary-card__quantity{padding-top:4px;font-size: 11.5px}.moments-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.moments-grid .media-image{height:110px}.moments-grid figure{border-radius:8px}.moments-grid figcaption{padding:6px}.moments-grid figcaption span{font-size: 11.5px}.moments-grid figcaption strong{margin-top:2px;font-size: 11px}.travel-note-section{grid-template-columns:1fr;gap:9px;margin-bottom:20px;padding:13px;border-radius:11px}.travel-note-heading h2{font-size:18px}.travel-note-heading button{margin-top:6px}.travel-note-copy p{font-size:11px;line-height:1.5}.travel-note-copy p.first{font-size:13px}.share-section{grid-template-columns:76px minmax(0,1fr);gap:10px;margin-bottom:20px;padding:10px;border-radius:11px}.share-copy h2{font-size:18px}.share-copy p{font-size: 11.5px;line-height:1.45}.share-actions{gap:5px;margin-top:7px}.share-actions :deep(.el-button){padding:6px 7px;font-size: 11.5px}.concierge-section{padding:13px;border-radius:11px}.concierge-header h2{font-size:18px}.concierge-quick{margin:9px 0}.concierge-quick button{padding:5px 7px;font-size: 11px}.concierge-input :deep(.el-input__wrapper){min-height:30px}.concierge-input :deep(.el-button){padding:7px 9px}.booking-bar{position:fixed;right:9px;bottom:9px;left:9px;width:auto;padding:9px 10px;border-radius:10px}.booking-bar p{display:none}.booking-bar__right{gap:4px}.booking-bar__right strong{font-size:16px}.booking-bar__right span{display:none}.booking-bar__right :deep(.el-button){padding:7px 8px;font-size: 11.5px}.poster-dialog__image{max-height:67vh}}@media(max-width:390px){.product-detail-hero h1{font-size:23px}.moments-grid .media-image{height:96px}.itinerary-card{grid-template-columns:80px minmax(0,1fr) 16px}.itinerary-card__image,.itinerary-card__image .media-image{height:74px}.booking-bar__right strong{font-size:14px}}
.product-detail-hero__ai{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.itinerary-card__time{display:block;margin-top:6px;color:var(--teal-dark);font-size:11px;font-weight:650}.chat-suggestions{grid-template-columns:1fr!important;gap:7px}.chat-suggestions .product-card--compact{width:100%}
</style>








<style scoped>
.detail-facts-section,.guide-source-section{margin:0 0 26px}.detail-facts-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.detail-facts-grid>div{padding:14px 16px;background:#fff;border:1px solid var(--line);border-radius:10px}.detail-facts-grid b{font-size:13px;color:var(--teal-dark)}.detail-facts-grid p{margin:7px 0 0;color:#576963;font-size:12px;line-height:1.65}.guide-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.guide-list a{display:grid;gap:6px;padding:13px 14px;background:#f6faf7;border:1px solid #dcebe4;border-radius:10px;color:var(--ink);text-decoration:none}.guide-list a strong{font-size:12px}.guide-list a span{color:var(--muted);font-size: 11.5px;line-height:1.5}
</style>
<style scoped>
.product-detail-hero,.trip-strip,.detail-content,.booking-bar{width:min(960px,100%);max-width:960px;margin-left:auto;margin-right:auto}.product-detail-hero{margin-top:0}.detail-content{box-sizing:border-box}.booking-bar{box-sizing:border-box}.guide-list article{display:grid;gap:6px;padding:13px 14px;background:#f6faf7;border:1px solid #dcebe4;border-radius:10px}.guide-list article p{margin:0;color:#4d625b;font-size:11px;line-height:1.6}.assistant-dialog :deep(.el-dialog__body){padding:0 18px 18px}.assistant-dialog .concierge-section{border:0;background:transparent;padding:0}.assistant-minimize{position:absolute;right:48px;top:18px;border:0;background:transparent;color:#26796a;font-size:12px;cursor:pointer}.chat-suggestions{grid-template-columns:1fr!important}.chat-suggestions .product-card--compact{display:grid;grid-template-columns:96px minmax(0,1fr);width:100%}
</style>
<style scoped>
.commerce-summary{max-width:960px;margin:12px auto 0;padding:16px;background:#fff}.commerce-title h2{margin:0;font-size:22px}.commerce-title p{margin:6px 0;color:var(--muted);font-size:12px}.commerce-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.commerce-tags span{padding:4px 8px;background:#fff3e6;color:#9a6427;font-size: 11.5px}.commerce-stats{display:flex;gap:28px;margin-top:16px}.commerce-stats div{display:grid;gap:3px}.commerce-stats strong{font-size:20px;color:#d56835}.commerce-stats small{color:var(--muted);font-size: 11.5px}.date-picker-row{display:flex;align-items:center;gap:8px;overflow:auto;margin-top:16px;padding-top:12px;border-top:1px solid var(--line)}.date-picker-row>b{white-space:nowrap;font-size:12px}.date-chip{display:grid;min-width:64px;padding:7px 9px;border:1px solid var(--line);text-align:center;cursor:pointer}.date-chip.active{border-color:#1e806d;background:#eaf7f1}.date-chip strong{font-size:12px}.date-chip small{margin-top:3px;color:var(--muted);font-size: 11px}.detail-anchor-nav{position:sticky;top:0;z-index:9;display:flex;justify-content:center;gap:34px;max-width:960px;margin:0 auto;padding:12px;background:#fff;border-bottom:1px solid var(--line)}.detail-anchor-nav a{color:var(--muted);font-size:12px;text-decoration:none}.commerce-highlight{margin-bottom:26px}.highlight-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.highlight-grid article{overflow:hidden;background:#fff;border:1px solid var(--line)}.highlight-grid .media-image{height:150px}.highlight-grid h3{margin:10px 12px 4px;font-size:14px}.highlight-grid p{margin:0 12px 12px;color:var(--muted);font-size:11px;line-height:1.55}.fee-section,.notice-section,.review-section{margin-bottom:26px}.fee-columns{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fee-columns>div{padding:14px 16px;background:#fff;border:1px solid var(--line)}.fee-columns h3{margin:0 0 8px;font-size:13px}.fee-columns p,.notice-list p{margin:6px 0;color:#586a63;font-size:12px;line-height:1.6}.notice-list{padding:12px 16px;background:#fff;border:1px solid var(--line)}.review-card{margin-bottom:8px;padding:14px 16px;background:#fff;border:1px solid var(--line)}.review-card div{display:flex;justify-content:space-between;gap:8px}.review-card span{color:#dc8a38;font-size:11px}.review-card p{margin:8px 0 0;color:#586a63;font-size:12px;line-height:1.6}@media(max-width:700px){.commerce-summary,.detail-anchor-nav{width:100%;box-sizing:border-box}.detail-anchor-nav{justify-content:space-around;gap:0}.highlight-grid{grid-template-columns:1fr 1fr}.highlight-grid article:last-child{grid-column:1/-1}.fee-columns{grid-template-columns:1fr}.commerce-stats{gap:18px}}
</style>

<style scoped>
.visitor-product-detail{max-width:960px;margin:0 auto;background:#f6f7f5}.product-detail-hero{border-radius:0 0 14px 14px}.commerce-summary{border-radius:14px;margin-top:8px;box-shadow:0 4px 16px rgba(40,60,50,.06)}.detail-anchor-nav{border-radius:0;box-shadow:0 2px 8px rgba(30,50,40,.04)}.booking-bar{position:fixed;left:50%;bottom:12px;transform:translateX(-50%);width:min(960px,calc(100% - 24px));z-index:30;background:rgba(255,255,255,.97);border-radius:14px;box-shadow:0 8px 28px rgba(25,55,43,.2)}.assistant-action{border:1px solid #1e806d;background:#eaf7f1;color:#1e6b5d;border-radius:8px;padding:8px 11px;font-size:12px;cursor:pointer;white-space:nowrap}.assistant-dialog :deep(.el-dialog){max-width:760px;margin-top:8vh!important}.assistant-dialog :deep(.el-dialog__body){max-height:68vh;overflow:auto}.assistant-dialog .concierge-section{min-height:320px}.chat-suggestions,.chat-suggestions .product-card--compact{display:grid!important;grid-template-columns:116px minmax(0,1fr)!important;width:100%!important;min-width:0}.chat-suggestions .product-card--compact>.media-image{width:116px;min-width:116px;height:100%;min-height:120px}.chat-suggestions .product-card--compact .product-card__body{min-width:0;overflow:hidden}.chat-suggestions .product-card--compact h3,.chat-suggestions .product-card--compact .product-card__hook{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:700px){.visitor-product-detail{width:100%}.commerce-summary{margin-top:6px;padding:13px}.commerce-title h2{font-size:19px}.commerce-stats{gap:16px}.date-picker-row{margin-left:-2px;margin-right:-2px}.detail-anchor-nav{position:sticky;top:0}.detail-content{padding:20px 12px 110px!important}.booking-bar{left:8px;right:8px;bottom:8px;transform:none;width:auto}.assistant-action{padding:7px 8px;font-size:11px}.booking-bar__right strong{font-size:17px}.assistant-dialog :deep(.el-dialog){width:calc(100% - 20px)!important;margin:10vh auto 0!important}.assistant-dialog :deep(.el-dialog__body){max-height:65vh;padding:12px}.assistant-dialog .concierge-section{min-height:0}.chat-suggestions,.chat-suggestions .product-card--compact{grid-template-columns:104px minmax(0,1fr)!important}.chat-suggestions .product-card--compact>.media-image{width:104px;min-width:104px;min-height:104px}}
</style>


<style scoped>
/* Visitor storefront layer: visual hierarchy follows a conventional travel-commerce product page. */
.visitor-product-detail {
  --shop-orange: var(--visitor-action, #e96b24);
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
.date-chip small { margin-top: 2px; color: #999; font-size: 11.5px; }
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
.chat-suggestions :deep(.product-card--compact) .product-card__bottom .muted { color: #aaa; font-size: 11.5px; }
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
  .trip-strip span { font-size: 11.5px; }
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
.date-note { flex: 0 0 auto; color: #999; font-size: 11.5px; }
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
.day-plan__meta span { padding: 3px 7px; border-radius: 999px; background: #f6f1ec; color: #8a7c72; font-size: 11.5px; }
.day-plan__meta .day-plan__note { background: #fff5e6; color: #a4703a; }
.day-plan__meta .day-plan__note--warning{background:#fff0eb;color:#9a4f36;border:1px solid #efd2c5;border-radius:7px;padding:6px 8px}
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
.soldout-banner__actions span { display: block; margin-top: 3px; color: #a5876f; font-size: 11.5px; }
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
.chat-suggestions .product-card--compact .product-card__facts { display: flex; flex-wrap: wrap; gap: 4px 8px; font-size: 11.5px; }
.chat-suggestions .product-card--compact .product-card__bottom { padding-top: 8px; }
.chat-suggestions .product-card--compact .product-card__bottom strong { font-size: 16px; }
.review-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.review-card { padding: 14px 16px; border: 1px solid #eee9e4; border-radius: 10px; background: #fff; }
.review-card__head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
.review-card__head b { color: #33302e; font-size: 13px; }
.review-card__head span { color: #ff6a00; font-size: 12px; }
.review-card__head small { margin-left: auto; color: #a9a09a; font-size: 11.5px; }
.review-highlights { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.review-highlights span { padding: 3px 7px; border-radius: 999px; background: #f5f1ec; color: #8b8078; font-size: 11.5px; }
.review-source { display: block; margin-top: 8px; color: #b6ada7; font-size: 11.5px; }
.review-empty { margin: 0; padding: 18px; border: 1px dashed #eee9e4; border-radius: 10px; color: #a9a09a; font-size: 12px; }
@media (max-width: 820px) { .review-list { grid-template-columns: 1fr; } }
</style>


<style scoped>
.hotel-detail-section, .photo-detail-section { margin-bottom: 24px; }
.hotel-detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.hotel-detail-grid > div { padding: 12px 14px; border: 1px solid #eee9e4; border-radius: 10px; background: #fff; }
.hotel-detail-grid > div.full { grid-column: 1 / -1; }
.hotel-detail-grid span { display: block; color: #a9a09a; font-size: 11.5px; }
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
.guide-source-line { display: block; margin-top: 5px; color: #a9a09a; font-size: 11.5px; }
.guide-content { width: 100%; margin: 9px 0 0; color: #4f5b57; font-size: 13px; line-height: 1.8; }
.guide-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px 18px; width: 100%; margin: 10px 0 0; padding: 10px 0 0; border-top: 1px dashed #f0e8e0; list-style: none; }
.guide-facts li { color: #6f6660; font-size: 11px; line-height: 1.65; }
.guide-facts b { display: inline-block; min-width: 62px; margin-right: 6px; color: #9a9089; font-weight: 500; }
.guide-verified { display: block; margin-top: 8px; color: #b3aaa3; font-size: 11.5px; }
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
.route-leg span { color: #a89c93; font-size: 11.5px; }
.route-leg p { margin: 4px 0 0; color: #6f6660; font-size: 11px; }
.route-leg small { display: block; margin-top: 3px; color: #9a8f87; font-size: 11.5px; line-height: 1.55; }
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
.detail-extra { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; align-content: start; gap: 18px; }
.detail-extra > div { min-width:0; align-self:start; padding: 4px 0 4px 12px; border:0; border-left:2px solid #e6ece8; border-radius:0; background:transparent; }
.detail-extra p { margin: 7px 0 0; color: #6f6660; font-size: 11px; line-height: 1.7; }.detail-advice-list{display:grid;gap:7px;margin:7px 0 0;padding:0;list-style:none}.detail-advice-list li{position:relative;padding-left:12px;color:#59665f;font-size:12px;line-height:1.65}.detail-advice-list li::before{content:"";position:absolute;left:0;top:.68em;width:4px;height:4px;border-radius:50%;background:#91ad9c}
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
.internal-preview-banner { position: sticky; top: 0; z-index: 20; padding: 8px 14px; background: #eef5ff; color: #405e8a; text-align: center; font-size: 12px; font-weight: 650; }
.preview-mode-banner { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 0 10px; padding:10px 14px; border:1px solid #d8e9e0; border-radius:10px; background:#f0f8f4; color:#315f52; font-size:12px; }
.preview-mode-banner a { color:#236e5e; font-weight:650; text-decoration:none; }
.review-section { margin:0 0 24px; }
.review-rating { color:#88703a; font-size:12px; }
.review-list { display:grid; gap:8px; }
.review-card { padding:12px 14px; border:1px solid var(--line); border-radius:10px; background:#fff; }
.review-card header { display:flex; justify-content:space-between; gap:12px; color:var(--ink); font-size:12px; }
.review-card header span { color:var(--muted); font-size: 11.5px; }
.review-card p,.review-empty { margin:7px 0 0; color:#53645d; font-size:12px; line-height:1.7; }
.review-highlights { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; }
.review-highlights span { padding:3px 7px; border-radius:999px; background:#edf7f2; color:#36796b; font-size: 11.5px; }
@media (max-width: 700px) {
  .preview-mode-banner { margin:0 0 8px; padding:9px 11px; }
  .review-card header { align-items:flex-start; flex-direction:column; gap:3px; }
  .guide-source-section .guide-facts { grid-template-columns: 1fr; }
}
</style>

<style scoped>
/* Purchase decision comes first; supporting details follow in calm, readable sections. */
.visitor-product-detail {
  width: min(1180px, calc(100% - 40px));
  max-width: 1180px;
  margin: 0 auto;
  padding-bottom: 108px;
  background: #fff;
}
.detail-purchase-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(380px, .88fr);
  align-items: stretch;
  gap: 30px;
  margin-top: 16px;
}
.detail-purchase-layout .product-detail-hero {
  width: 100%;
  height: auto;
  min-height: 480px;
  border-radius: 12px;
  background: #eef1ed;
}
.detail-purchase-layout .product-detail-hero > .media-image { position: absolute; inset: 0; width: 100%; height: 100%; }
.detail-purchase-layout .product-detail-hero__veil { background: linear-gradient(180deg, rgba(0,0,0,.10), transparent 38%, rgba(0,0,0,.26)); }
.detail-purchase-layout .product-detail-hero__content,
.detail-purchase-layout .hero-price { display: none; }
.detail-purchase-layout .back-to-list { top: 16px; left: 16px; padding: 8px 12px; font-size: 13px; }
.detail-purchase-layout .hero-actions { top: 16px; right: 16px; }
.commerce-summary {
  display: flex;
  max-width: none;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  gap: 18px;
  margin: 0;
  padding: 16px 8px;
  border: 0;
  border-radius: 0;
  background: #fff;
  box-shadow: none;
}
.commerce-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.commerce-title { min-width: 0; }
.commerce-title h1 { margin: 0; color: #26352e; font-size: clamp(25px, 2.3vw, 32px); font-weight: 680; line-height: 1.35; letter-spacing: -.4px; }
.commerce-title p { max-width: 560px; margin: 9px 0 0; color: #58665e; font-size: 15px; line-height: 1.7; }
.commerce-tags { gap: 14px; margin-top: 13px; }
.commerce-tags span { padding: 0; background: transparent; color: #587365; font-size: 13px; }
.commerce-price { display: flex; flex: 0 0 auto; flex-wrap: nowrap; align-items: baseline; gap: 6px; margin: 2px 0 0; white-space: nowrap; }
.commerce-price strong { color: #e66b26; font-size: 30px; }
.commerce-price span { color: #747e77; font-size: 13px; }
.commerce-inclusion { display: grid; gap: 5px; padding: 14px 0; border-top: 1px solid #edf0ec; border-bottom: 1px solid #edf0ec; }
.commerce-inclusion span { color: #7b867f; font-size: 12px; }
.commerce-inclusion strong { color: #34483d; font-size: 15px; font-weight: 600; line-height: 1.65; }
.commerce-summary .date-picker-row { flex-wrap: wrap; overflow: visible; gap: 8px; margin: 0; padding: 0; }
.commerce-summary .date-picker-row > b { width: 100%; color: #4d5c53; font-size: 13px; }
.commerce-summary .date-chip { min-width: 82px; padding: 8px 10px; border: 1px solid #e5e9e4; border-radius: 8px; background: #fff; color: #4f5a54; }
.commerce-summary .date-chip.active { border-color: #79a08d; background: #f1f7f2; color: #345d49; box-shadow: none; }
.commerce-summary .date-chip strong { font-size: 13px; }
.commerce-summary .date-chip small { color: #738177; font-size: 12px; }
.commerce-stay-note { margin: -9px 0 0; color: #6d7971; font-size: 13px; line-height: 1.6; }
.commerce-purchase-actions { display: flex; align-items: center; gap: 12px; margin-top: 2px; }
.commerce-purchase-actions :deep(.el-button--primary) { min-width: 160px; height: 46px; border: 0; border-radius: 7px; background: var(--visitor-action, #e96b24); font-size: 15px; font-weight: 650; }
.commerce-assistant-link { min-height: 42px; padding: 0 8px; border: 0; background: transparent; color: #3c6b58; font-size: 14px; cursor: pointer; }
.commerce-confirmation { margin: -10px 0 0; color: #88928b; font-size: 12px; line-height: 1.5; }
.detail-anchor-nav { top: 62px; max-width: 1180px; margin: 22px auto 0; justify-content: flex-start; gap: 30px; border-top: 1px solid #ecefea; }
.detail-anchor-nav button { padding: 14px 2px 12px; font-size: 14px; }
.detail-content { max-width: 1120px; padding: 8px 12px 24px; }
.detail-content > .commerce-highlight,
.detail-content > .itinerary-section,
.detail-content > .fee-section,
.detail-content > .notice-section,
.detail-content > .hotel-detail-section,
.detail-content > .photo-detail-section,
.detail-content > .guide-source-section,
.detail-content > .moments-section,
.detail-content > .related-section {
  margin: 0;
  padding: 28px 0;
  border: 0;
  border-bottom: 1px solid #eef0ec;
  border-radius: 0;
  background: #fff;
  box-shadow: none;
}
.section-heading { margin-bottom: 18px; }
.section-heading h2 { padding-left: 0; color: #293a31; font-size: 22px; }
.section-heading h2::before { display: none; }
.section-heading .section-kicker { color: #849188; font-size: 12px; letter-spacing: 0; }
.detail-story { max-width: 860px; margin: 0 0 18px; color: #56645c; font-size: 15px; line-height: 1.8; }
.highlight-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 22px; }
.highlight-grid article { padding: 0; border: 0; border-radius: 0; background: transparent; }
.highlight-grid .media-image { height: 190px; border-radius: 8px; }
.highlight-grid h3 { margin: 11px 0 5px; color: #33443a; font-size: 16px; line-height: 1.5; }
.highlight-grid p { margin: 0; color: #68746d; font-size: 14px; line-height: 1.7; }
.day-plan { padding: 20px 0; border: 0; border-bottom: 1px solid #eef0ec; border-radius: 0; background: transparent; box-shadow: none; }
.day-plan__items li { padding: 14px 0; border-bottom: 1px solid #f0f2ef; }
.day-plan__time { color: #4d6b59; font-size: 13px; }
.day-plan__items li > div > b { color: #2f4037; font-size: 15px; }
.day-plan__items li p { color: #606e65; font-size: 14px; line-height: 1.7; }
.day-plan__optional { display: inline-block; margin-top: 6px; color: #927342; font-size: 12px; }
.day-plan__meta { color: #728077; font-size: 12px; }
.fee-columns { gap: 36px; }
.fee-columns > div { padding: 0; border: 0; border-radius: 0; background: transparent; }
.fee-columns h3 { padding: 0 0 10px; border-bottom: 1px solid #e9eee9; color: #3b624f; font-size: 15px; }
.fee-columns p { padding: 9px 0; color: #55645b; font-size: 14px; line-height: 1.65; }
.fee-columns p small { display: block; margin: 3px 0 0 20px; color: #8a958d; font-size: 12px; }
.notice-list { padding: 0; border: 0; background: transparent; }
.notice-list p { margin: 0; padding: 10px 0; border-bottom: 1px solid #f0f2ef; color: #56645c; font-size: 14px; line-height: 1.7; }
.hotel-detail-grid { gap: 0 30px; }
.hotel-detail-grid > div { padding: 13px 0; border: 0; border-bottom: 1px solid #f0f2ef; border-radius: 0; background: transparent; }
.hotel-detail-grid span { color: #7d8981; font-size: 12px; }
.hotel-detail-grid strong { color: #3a4a40; font-size: 14px; }
.photo-detail-lead { color: #627168; font-size: 14px; }
.photo-detail-list li { border-left: 0; border-bottom: 1px solid #f0f2ef; background: transparent; color: #56645c; font-size: 14px; }
.guide-intro { margin: -6px 0 12px; color: #7b867e; font-size: 13px; }
.guide-source-section .guide-list { gap: 0; }
.guide-source-section .guide-list > article { padding: 16px 0; border: 0; border-bottom: 1px solid #eef0ec; border-radius: 0; background: transparent; }
.guide-source-section .guide-list > article > header strong { color: #35483c; font-size: 16px; }
.guide-source-section .guide-content { color: #5b6960; font-size: 14px; }
.guide-source-section .guide-facts { padding: 8px 0 0; border: 0; }
.guide-source-section .guide-facts li { color: #65736a; font-size: 13px; }
.guide-source-section .guide-verified { color: #929b94; font-size: 12px; }
.booking-bar { width: min(1180px, calc(100% - 32px)); max-width: 1180px; border: 1px solid #e7ebe6; border-radius: 10px; box-shadow: 0 8px 24px rgba(29, 47, 37, .12); }
.booking-bar__right { gap: 14px; }
.assistant-action { border: 0; background: transparent; color: #3c6b58; font-size: 13px; }
.assistant-dialog :deep(.el-dialog) { border-radius: 12px; }
.share-preview { display: grid; grid-template-columns: 44% minmax(0, 1fr); gap: 16px; align-items: center; padding: 8px; }
.share-preview > .media-image { height: 190px; border-radius: 8px; }
.share-preview strong { color: #2e4036; font-size: 18px; line-height: 1.4; }
.share-preview p { margin: 10px 0; color: #627067; font-size: 14px; line-height: 1.6; }
.share-preview span { color: #df6a28; font-size: 14px; font-weight: 650; }
@media (max-width: 860px) {
  .visitor-product-detail { width: min(100%, 740px); }
  .detail-purchase-layout { grid-template-columns: 1fr; gap: 0; margin-top: 8px; }
  .detail-purchase-layout .product-detail-hero { min-height: 0; aspect-ratio: 1.55; }
  .commerce-summary { gap: 14px; padding: 20px 4px 18px; }
  .commerce-head { gap: 12px; }
  .commerce-title h1 { font-size: 25px; }
  .commerce-price strong { font-size: 26px; }
  .detail-anchor-nav { gap: 20px; overflow-x: auto; }
  .detail-content { padding-inline: 4px; }
}
@media (max-width: 600px) {
  .visitor-product-detail { width: 100%; padding: 0 14px 108px; box-sizing: border-box; }
  .detail-purchase-layout .product-detail-hero { aspect-ratio: 1.35; border-radius: 9px; }
  .detail-purchase-layout .back-to-list { top: 10px; left: 10px; }
  .commerce-summary { gap: 12px; padding: 17px 0; }
  .commerce-title h1 { font-size: 22px; }
  .commerce-title p { margin-top: 6px; font-size: 14px; }
  .commerce-price strong { font-size: 22px; }
  .commerce-inclusion strong { font-size: 14px; }
  .commerce-purchase-actions { gap: 10px; }
  .commerce-purchase-actions :deep(.el-button--primary) { min-width: 132px; height: 42px; }
  .commerce-assistant-link { font-size: 13px; }
  .detail-anchor-nav { position: sticky; top: 56px; z-index: 10; gap: 18px; justify-content: flex-start; margin: 0 -14px; padding: 0 14px; background: #fff; }
  .detail-anchor-nav button { flex: 0 0 auto; padding: 13px 1px 11px; font-size: 13px; }
  .detail-content { padding: 0 0 12px; }
  .detail-content > .commerce-highlight,
  .detail-content > .itinerary-section,
  .detail-content > .fee-section,
  .detail-content > .notice-section,
  .detail-content > .hotel-detail-section,
  .detail-content > .photo-detail-section,
  .detail-content > .guide-source-section,
  .detail-content > .moments-section,
  .detail-content > .related-section { padding: 22px 0; }
  .section-heading h2 { font-size: 19px; }
  .detail-story { font-size: 14px; }
  .highlight-grid { grid-template-columns: 1fr; gap: 18px; }
  .highlight-grid .media-image { height: auto; aspect-ratio: 1.7; }
  .highlight-grid p,.fee-columns p,.notice-list p,.hotel-detail-grid strong { font-size: 13px; }
  .fee-columns { grid-template-columns: 1fr; gap: 18px; }
  .hotel-detail-grid { grid-template-columns: 1fr; }
  .share-preview { grid-template-columns: 1fr; }
  .share-preview > .media-image { height: 180px; }
  .booking-bar { right: 10px; bottom: 10px; left: 10px; width: auto; padding: 8px 10px; }
  .booking-bar__right { gap: 7px; }
  .booking-bar__right strong { font-size: 17px; }
  .booking-bar__right span { display: none; }
}

/* Keep the established left-image/right-summary hero, with room for the full
   storefront width; the itinerary returns to a quiet schedule timeline. */
.visitor-product-detail { width: min(1280px, 100%); max-width: 1280px; margin-inline: auto; }
.detail-purchase-layout { grid-template-columns: minmax(0, 1.08fr) minmax(390px, .92fr); gap: 30px; align-items: stretch; }
.detail-purchase-layout .product-detail-hero { min-height: 490px; border-radius: 14px; }
.commerce-summary { align-content: center; min-width: 0; padding-inline: 8px; }
.detail-content { width: 100%; max-width: 1180px; margin-inline: auto; }
.highlight-grid { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 22px; }
.highlight-grid > article { min-width: 0; padding: 0 0 14px; border: 0; border-bottom: 1px solid #ecefeb; border-radius: 0; background: transparent; }
.highlight-grid > article .media-image { width: 100%; aspect-ratio: 1.65; overflow: hidden; border-radius: 9px; }
.highlight-grid > article h3 { margin: 12px 0 5px; color: #293d33; font-size: 16px; }
.highlight-grid > article p { margin: 0; color: #68766e; font-size: 13px; line-height: 1.65; }
.day-plan-list { display: grid; gap: 28px; }
.day-plan { padding: 0; border: 0; border-radius: 0; background: transparent; }
.day-plan__head { align-items: center; padding: 0 0 11px; border-bottom: 1px solid #e9eeea; }
.day-plan__head > div { display: flex; align-items: center; gap: 12px; }
.day-plan__head strong { margin: 0; color: #53645a; font-size: 13px; font-weight: 600; }
.day-plan__head small { color: #89938d; font-size: 12px; }
.day-plan__label { padding: 4px 9px; border-radius: 999px; background: #eef5ef; color: #3f6f58; font-size: 12px; }
.day-plan__items { position: relative; gap: 0; padding-top: 6px; }
.day-plan__items::before { position: absolute; top: 14px; bottom: 14px; left: 109px; width: 1px; background: #dfe8e1; content: ''; }
.day-plan__items li { position: relative; grid-template-columns: 92px minmax(0, 1fr); gap: 36px; padding: 14px 0; }
.day-plan__items li::before { position: absolute; top: 20px; left: 104px; width: 9px; height: 9px; border: 2px solid #fff; border-radius: 50%; background: #4d9770; box-shadow: 0 0 0 1px #b9d4c2; content: ''; }
.day-plan__time { display: grid; justify-items: end; gap: 4px; padding-top: 0; color: #3e6a52; font-family: var(--font-sans); font-size: 12px; line-height: 1.5; text-align: right; }
.day-plan__time b { margin: 0; color: #819088; font-size: 11px; font-weight: 500; }
.day-plan__items li > div > b { color: #293d33; font-size: 15px; }
.day-plan__items p { margin: 5px 0 0; color: #69776e; font-size: 13px; line-height: 1.65; }
.day-plan__meta { display: grid; gap: 4px; margin-top: 7px; }
.day-plan__meta span { width: fit-content; padding: 0; border: 0; border-radius: 0; background: transparent; color: #87928b; font-size: 12px; line-height: 1.55; }
.day-plan__meta .day-plan__note { color: #7a6b50; }
.guide-list { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.guide-source-section .guide-list > article { display: flex; min-width: 0; flex-direction: column; gap: 8px; padding: 16px; border: 1px solid #e8ede8; border-radius: 11px; background: #fff; }
.guide-source-section .guide-list > article > header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.guide-source-section .guide-list > article > header strong { color: #30483a; font-size: 15px; }
.guide-source-section .guide-list > article > header em { flex: 0 0 auto; color: #7a897f; font-size: 11px; font-style: normal; }
.guide-source-section .guide-content { margin: 0; color: #65736b; font-size: 13px; line-height: 1.65; }
.guide-source-section .guide-facts { display: grid; gap: 5px; margin: 0; padding: 8px 0 0; border-top: 1px solid #eff2ef; }
.guide-source-section .guide-facts li { color: #68766d; font-size: 12px; line-height: 1.6; }
.guide-source-section .guide-facts b { min-width: 0; color: #87938b; font-weight: 500; }
.guide-source-section .guide-list > article > footer { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: auto; padding-top: 5px; }
.guide-source-section .guide-list > article > footer span { color: #a26437; font-size: 11px; }
.guide-source-section .guide-list > article > footer a { color: #718177; font-size: 11px; text-decoration: none; }
.guide-empty { margin: 0; padding: 18px 0; color: #7d8981; font-size: 13px; }
.booking-bar { width: min(1280px, calc(100% - 40px)); max-width: 1280px; }
@media (max-width: 980px) {
  .detail-purchase-layout { grid-template-columns: minmax(0, 1fr) minmax(330px, .95fr); gap: 20px; }
  .detail-purchase-layout .product-detail-hero { min-height: 420px; }
  .guide-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 860px) {
  .visitor-product-detail { width: 100%; }
  .detail-purchase-layout { grid-template-columns: 1fr; gap: 0; }
  .detail-purchase-layout .product-detail-hero { min-height: 0; }
}
@media (max-width: 700px) {
  .day-plan__items::before { left: 83px; }
  .day-plan__items li { grid-template-columns: 68px minmax(0, 1fr); gap: 28px; }
  .day-plan__items li::before { left: 78px; }
  .guide-list { grid-template-columns: 1fr; gap: 10px; }
  .guide-source-section .guide-list > article { padding: 13px 0; border: 0; border-bottom: 1px solid #e9eeea; border-radius: 0; background: transparent; }
}
</style>

<style scoped>
.day-plan-list{gap:12px}.day-plan{padding:17px 18px;border:1px solid #f0e1d6;border-radius:12px;background:#fffdfb;box-shadow:none}.day-plan__head{align-items:flex-start;padding-bottom:10px;border-bottom:1px dashed #f0e2d6}.day-plan__head>div{display:grid;justify-items:start;gap:7px}.day-plan__head strong{display:block;margin:0;color:#292724;font-size:17px;line-height:1.35}.day-plan__head small{padding-top:4px;color:#a4968b;font-size:11.5px;white-space:nowrap}.day-plan__summary{margin:10px 0 13px;color:#7d6f66;font-size:12px;line-height:1.65}.day-plan__items{gap:12px;margin-top:12px}.day-plan__items li{grid-template-columns:96px minmax(0,1fr);gap:12px}.day-plan__time{padding-top:1px;color:#d56835;font-size:11.5px;line-height:1.5}.day-plan__time b{font-size:12px}.day-plan__items>li>div{min-width:0}.day-plan__items>li>div>b{color:#292724;font-size:13.5px;line-height:1.45}.day-plan__items p{margin-top:3px;color:#766a62;font-size:12px;line-height:1.6}.day-plan__meta{gap:5px;margin-top:6px}.day-plan__meta span{background:#f7f1eb;font-size:11.5px}@media(max-width:700px){.day-plan{padding:14px}.day-plan__items li{grid-template-columns:76px minmax(0,1fr);gap:8px}.day-plan__head strong{font-size:15px}}

/* Itinerary follows the compact day card and two-column activity rows in the reference. */
.day-plan-list { display: grid; gap: 14px; }
.day-plan { padding: 16px 18px; border: 1px solid #f0e1d6; border-radius: 12px; background: #fffdfb; box-shadow: none; }
.day-plan__head { align-items: flex-start; padding: 0 0 11px; border-bottom: 1px dashed #f0e2d6; }
.day-plan__head > div { display: grid; justify-items: start; gap: 7px; }
.day-plan__head strong { display: block; margin: 0; color: #292724; font-size: 16px; line-height: 1.4; }
.day-plan__head small { padding-top: 4px; color: #a4968b; font-size: 12px; white-space: nowrap; }
.day-plan__label { width: fit-content; padding: 4px 9px; border-radius: 999px; background: #fff0e6; color: #d56835; font-size: 12px; }
.day-plan__items { position: relative; gap: 0; margin-top: 7px; padding-top: 0; }
.day-plan__items::before, .day-plan__items li::before { display: none !important; content: none !important; }
.day-plan__items li { position: static; grid-template-columns: 96px minmax(0, 1fr); gap: 13px; padding: 10px 0; border: 0; }
.day-plan__time { display: grid; justify-items: start; align-content: start; gap: 2px; padding-top: 0; color: #df5f2c; font-size: 12px; line-height: 1.45; text-align: left; }
.day-plan__time b { margin: 0; color: #262522; font-size: 13px; font-weight: 650; }
.day-plan__items li > div > b { color: #292724; font-size: 14px; line-height: 1.45; }
.day-plan__items p { margin: 4px 0 0; color: #766a62; font-size: 12.5px; line-height: 1.65; }
.day-plan__meta { display: flex; flex-wrap: wrap; gap: 5px 6px; margin-top: 7px; }
.day-plan__meta span { width: fit-content; padding: 3px 8px; border: 0; border-radius: 999px; background: #f7f1eb; color: #8d7a6d; font-size: 11.5px; line-height: 1.5; }
.day-plan__meta .day-plan__note { background: #fff4e5; color: #94613b; }
.day-plan__meta .day-plan__note--warning { background: #fff0eb; color: #9a4f36; }

/* Nearby recommendations use one readable card per place. */
.guide-source-section .section-heading h2::before { display: inline-block; width: 3px; height: 18px; margin-right: 9px; border-radius: 2px; background: #ef6b28; vertical-align: -3px; content: ''; }
.guide-source-section .guide-list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
.guide-source-section .guide-list > article { display: grid; gap: 8px; padding: 16px 18px; border: 1px solid #eee9e2; border-radius: 10px; background: #f8fbf9; }
.guide-source-section .guide-list > article > header { display: grid; justify-content: start; gap: 3px; }
.guide-source-section .guide-list > article > header strong { color: #24463d; font-size: 16px; line-height: 1.45; }
.guide-source-section .guide-list > article > header strong span { color: #718078; font-size: 13px; font-weight: 500; }
.guide-source-section .guide-list > article > header em { color: #c57735; font-size: 12px; font-style: normal; }
.guide-source-section .guide-source-line { display: block; width: fit-content; margin: 1px 0 0; color: #87958e; font-size: 12px; text-decoration: none; }
.guide-source-section a.guide-source-line:hover { color: #326d5d; text-decoration: underline; }
.guide-source-section .guide-content { margin: 0; color: #43574f; font-size: 13px; line-height: 1.75; }
.guide-source-section .guide-facts { display: grid; grid-template-columns: minmax(0, 1fr); gap: 5px; margin: 3px 0 0; padding: 8px 0 0; border-top: 1px dashed #eee7df; }
.guide-source-section .guide-facts li { display: grid; grid-template-columns: 60px minmax(0, 1fr); gap: 8px; color: #58675f; font-size: 12px; line-height: 1.65; overflow-wrap: anywhere; }
.guide-source-section .guide-facts b { min-width: 0; margin: 0; color: #287363; font-weight: 600; }
.guide-source-section .guide-list > article > footer { display: flex; justify-content: flex-start; margin-top: 0; padding: 0; }
.guide-source-section .guide-list > article > footer span { color: #b66b34; font-size: 11.5px; }

/* Group facts without drawing a rule after every line. */
.fee-columns { gap: 44px; }
.fee-columns h3 { padding: 0 0 7px; border: 0; color: #3b624f; font-size: 15px; }
.fee-columns p { margin: 0; padding: 4px 0; border: 0; color: #55645b; font-size: 14px; line-height: 1.65; }
.notice-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 34px; }
.notice-list p { margin: 0; padding: 0; border: 0; color: #56645c; font-size: 13.5px; line-height: 1.7; }
.hotel-detail-grid { gap: 15px 38px; }
.hotel-detail-grid > div { padding: 0; border: 0; border-radius: 0; background: transparent; }
.hotel-detail-grid span { color: #9a8f86; font-size: 12px; }
.hotel-detail-grid strong { margin-top: 4px; color: #3a4a40; font-size: 14px; }

@media (max-width: 700px) {
  .day-plan { padding: 14px; }
  .day-plan__items li { grid-template-columns: 76px minmax(0, 1fr); gap: 8px; }
  .day-plan__head strong { font-size: 15px; }
  .guide-source-section .guide-list > article { padding: 14px; }
  .notice-list { grid-template-columns: 1fr; gap: 10px; }
}



.highlight-public-tag {
  display: inline-block;
  margin-top: 10px;
  color: #bd6938;
  font-size: 11px;
  line-height: 1.4;
}
.day-plan__entry {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 13px;
}
.day-plan__entry-image {
  width: 116px;
  height: 78px;
  flex: 0 0 116px;
  overflow: hidden;
  border-radius: 8px;
}
.day-plan__entry-image :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.day-plan__entry-copy {
  min-width: 0;
}
@media (max-width: 700px) {
  .day-plan__entry { gap: 9px; }
  .day-plan__entry-image { width: 88px; height: 66px; flex-basis: 88px; }
}
</style>

<style scoped>
/* Use the desktop canvas for product decisions and keep the amount with its unit. */
.visitor-product-detail { width: min(1520px, calc(100% - 40px)); max-width: 1520px; }
.detail-content { max-width: 1480px; }
.detail-anchor-nav { max-width: 1520px; }
.booking-bar { width: min(1520px, calc(100% - 40px)); max-width: 1520px; }
.visitor-product-detail .commerce-head .commerce-price { display: inline-flex !important; flex: 0 0 auto; flex-direction: row; flex-wrap: nowrap !important; align-items: baseline; justify-content: flex-end; gap: 5px; width: max-content; max-width: 100%; white-space: nowrap; }
.visitor-product-detail .commerce-head .commerce-price strong,
.visitor-product-detail .commerce-head .commerce-price span { flex: 0 0 auto; white-space: nowrap; }
.visitor-product-detail .commerce-head .commerce-price strong { font-size: clamp(23px, 2vw, 30px); }
.visitor-product-detail .commerce-head .commerce-price span { font-size: 12px; }
.booking-bar__price { display: flex; flex: 0 0 auto; align-items: baseline; gap: 5px; white-space: nowrap; }
.booking-bar__price strong, .booking-bar__price span { white-space: nowrap; }
.commerce-highlight > .section-heading,
.commerce-highlight > .highlight-grid { padding-inline: 14px; }
.highlight-grid > article { padding-inline: 0; }
.highlight-grid > article h3 { margin-top: 14px; }
.highlight-grid > article p { line-height: 1.75; }
.day-plan { padding: 20px 24px; }
.day-plan__items li { gap: 20px; }
.day-plan__entry { gap: 16px; }
.day-plan__suggestions { display: grid; gap: 3px; margin-top: 10px; }
.day-plan__suggestions > b { color: #567461; font-size: 12px; font-weight: 600; }
.day-plan__suggestions > p { display: grid; gap: 2px; margin: 3px 0 0; }
.day-plan__suggestions > p > strong { color: #394d40; font-size: 12px; font-weight: 600; line-height: 1.5; }
.day-plan__suggestions > p > span { color: #77837b; font-size: 11.5px; line-height: 1.55; }
@media (max-width: 860px) { .visitor-product-detail { width: 100%; } .detail-content { max-width: none; } .booking-bar { width: auto; } }
@media (max-width: 700px) {
  .day-plan { padding: 18px 18px; }
  .day-plan__items li { grid-template-columns: 76px minmax(0, 1fr); gap: 14px; }
  .day-plan__entry { gap: 11px; }
  .day-plan__suggestions > p > span { font-size: 11px; }
}
</style>

<style scoped>
/* Visitor product detail typography scale and shared alignment. */
.visitor-product-detail .commerce-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) max-content;
  align-items: start;
  gap: 16px;
}
.visitor-product-detail .commerce-title { min-width: 0; }
.visitor-product-detail .commerce-title h1 {
  display: -webkit-box;
  max-width: 100%;
  margin: 0 0 8px;
  overflow: hidden;
  color: #263832;
  font-size: clamp(26px, 1.45vw, 28px);
  font-weight: 680;
  line-height: 1.28;
  text-wrap: balance;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.visitor-product-detail .commerce-title > p { margin: 0 0 8px; color: #64736a; font-size: 14px; line-height: 1.6; }
.visitor-product-detail .commerce-tags { gap: 7px; }
.visitor-product-detail .commerce-tags > span { font-size: 12px; line-height: 1.45; }
.visitor-product-detail .commerce-head .commerce-price {
  align-self: start;
  justify-self: end;
  gap: 5px;
  margin-top: 2px;
}
.visitor-product-detail .commerce-head .commerce-price strong { color: #dc6c31; font-size: 27px; font-weight: 700; line-height: 1.2; }
.visitor-product-detail .commerce-head .commerce-price span { color: #778179; font-size: 13px; }
.visitor-product-detail .commerce-inclusion { gap: 6px; padding: 12px 0; }
.visitor-product-detail .commerce-inclusion > span { color: #758178; font-size: 13px; }
.visitor-product-detail .commerce-inclusion > strong { color: #34483d; font-size: 14px; line-height: 1.6; }
.visitor-product-detail .date-picker-row {
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  overflow: visible;
  margin: 0;
  padding: 0;
}
.visitor-product-detail .date-picker-row > b { width: auto; margin-right: 3px; font-size: 13px; }
.visitor-product-detail .date-chip {
  display: inline-flex;
  flex: 0 1 auto;
  min-width: 0;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  text-align: left;
  white-space: nowrap;
}
.visitor-product-detail .date-chip strong { font-size: 13px; }
.visitor-product-detail .date-chip small { margin: 0; color: #718078; font-size: 12px; }
.visitor-product-detail .commerce-stay-note { margin: -5px 0 0; color: #768179; font-size: 13px; line-height: 1.5; }
.visitor-product-detail .commerce-purchase-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.visitor-product-detail .commerce-purchase-actions :deep(.el-button) { height: 44px; margin: 0; padding-inline: 22px; font-size: 14px; }
.visitor-product-detail .commerce-assistant-link { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; padding: 0 16px; font-size: 14px; line-height: 1; }
.visitor-product-detail .back-to-list { font-size: 12px; }

.visitor-product-detail .detail-anchor-nav {
  top: 56px !important;
  display: flex;
  width: 100%;
  max-width: 1280px;
  height: 50px;
  align-items: stretch;
  justify-content: space-around;
  gap: 0;
  margin: 12px auto 0 !important;
  padding: 0;
}
.visitor-product-detail .detail-anchor-nav button {
  display: inline-flex;
  min-width: 0;
  height: 50px;
  flex: 1 1 0;
  align-items: center;
  justify-content: center;
  padding: 0 10px;
  font-size: 14px;
  line-height: 1;
}
.visitor-product-detail .detail-anchor-nav button.active::after { right: 20%; left: 20%; height: 2px; }
.visitor-product-detail .detail-content {
  width: 100%;
  max-width: 1280px;
  margin-inline: auto;
  padding: 20px 0 44px;
}
.visitor-product-detail .detail-content > section {
  margin: 0;
  padding: 24px 0;
}
.visitor-product-detail .detail-content .section-heading {
  align-items: center;
  margin: 0 0 16px;
  padding: 0;
}
.visitor-product-detail .detail-content .section-heading h2 {
  position: static;
  margin: 0;
  padding: 0;
  color: #273b32;
  font-size: 22px;
  font-weight: 680;
  line-height: 1.35;
}
.visitor-product-detail .detail-content .section-heading h2::before {
  position: static;
  display: inline-block;
  width: 3px;
  height: 18px;
  margin: 0 12px 0 0;
  border-radius: 2px;
  background: #ef6b28;
  vertical-align: -2px;
  content: '';
}
.visitor-product-detail .detail-content .section-kicker { font-size: 12px; }
.visitor-product-detail .detail-content .section-count { font-size: 12px; }
.visitor-product-detail .commerce-highlight > .section-heading,
.visitor-product-detail .commerce-highlight > .highlight-grid { padding-inline: 0; }
.visitor-product-detail .highlight-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  align-items: stretch;
  gap: 16px;
}
.visitor-product-detail .highlight-grid > article {
  display: grid;
  height: 100%;
  grid-template-rows: 176px 18px minmax(44px, auto) 1fr;
  gap: 8px;
  padding: 0 0 14px;
  border: 1px solid #e9ece8;
  border-radius: 11px;
  background: #fff;
}
.visitor-product-detail .highlight-grid > article .media-image {
  width: 100%;
  height: 176px;
  overflow: hidden;
  border-radius: 10px 10px 0 0;
}
.visitor-product-detail .highlight-grid > article .media-image :deep(img) { width: 100%; height: 100%; object-fit: cover; }
.visitor-product-detail .highlight-type-tag {
  justify-self: start;
  align-self: center;
  margin: 0 14px;
  color: #b76532;
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
}
.visitor-product-detail .highlight-grid > article h3 {
  min-height: 44px;
  margin: 0 14px;
  color: #2d4036;
  font-size: 16.5px;
  font-weight: 650;
  line-height: 1.38;
}
.visitor-product-detail .highlight-grid > article p {
  margin: 0 14px;
  color: #65746b;
  font-size: 14px;
  line-height: 1.6;
}

.visitor-product-detail .itinerary-section .section-heading { margin-bottom: 14px; }
.visitor-product-detail .day-plan { padding: 18px 22px; }
.visitor-product-detail .day-plan__head {
  align-items: center;
  gap: 16px;
  padding-bottom: 10px;
}
.visitor-product-detail .day-plan__head > div { display: flex; min-width: 0; align-items: center; gap: 12px; }
.visitor-product-detail .day-plan__head strong { margin: 0; color: #2e4036; font-size: 16px; font-weight: 650; line-height: 1.35; }
.visitor-product-detail .day-plan__head small { margin-left: auto; padding: 0; color: #78847d; font-size: 13px; }
.visitor-product-detail .day-plan__label { flex: 0 0 auto; font-size: 12px; }
.visitor-product-detail .day-plan__items li {
  grid-template-columns: 86px minmax(0, 1fr);
  align-items: start;
  gap: 20px;
  padding: 13px 0;
}
.visitor-product-detail .day-plan__time { gap: 3px; padding: 0; font-family: var(--font-sans); font-size: 13px; line-height: 1.45; }
.visitor-product-detail .day-plan__time b { margin: 0; font-size: 13px; font-weight: 650; }
.visitor-product-detail .day-plan__entry { min-width: 0; align-items: flex-start; gap: 14px; }
.visitor-product-detail .day-plan__entry-image { width: 116px; height: 82px; flex: 0 0 116px; }
.visitor-product-detail .day-plan__entry-copy { min-width: 0; flex: 1 1 auto; }
.visitor-product-detail .day-plan__entry-copy > b { color: #293d33; font-size: 16px; font-weight: 650; line-height: 1.4; }
.visitor-product-detail .day-plan__entry-copy > p { margin: 5px 0 0; color: #5f6e64; font-size: 14px; line-height: 1.65; }
.visitor-product-detail .day-plan__meta,
.visitor-product-detail .day-plan__entry-copy small { color: #78847d; font-size: 13px; line-height: 1.55; }
.visitor-product-detail .day-plan__suggestions { gap: 5px; margin-top: 8px; }
.visitor-product-detail .day-plan__suggestions > b,
.visitor-product-detail .day-plan__suggestions > p > strong,
.visitor-product-detail .day-plan__suggestions > p > span { font-size: 13px; line-height: 1.55; }

.visitor-product-detail .fee-columns {
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}
.visitor-product-detail .fee-columns > div { min-width: 0; }
.visitor-product-detail .fee-columns h3 { margin: 0 0 8px; padding: 0; border: 0; font-size: 16px; line-height: 1.4; }
.visitor-product-detail .fee-columns p { margin: 0; padding: 5px 0; border: 0; font-size: 14px; line-height: 1.6; }
.visitor-product-detail .fee-columns p small { margin-top: 2px; font-size: 13px; }
.visitor-product-detail .notice-list {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px 22px;
  padding: 0;
  border: 0;
  background: transparent;
}
.visitor-product-detail .notice-list p { display: grid; gap: 5px; margin: 0; padding: 0; border: 0; font-size: 14px; line-height: 1.55; }
.visitor-product-detail .notice-list p b { color: #7b877f; font-size: 13px; font-weight: 500; }
.visitor-product-detail .notice-list p span { color: #35473c; font-size: 14px; font-weight: 550; }
.visitor-product-detail .hotel-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 30px; }
.visitor-product-detail .hotel-detail-grid > div { min-width: 0; padding: 0; border: 0; background: transparent; }
.visitor-product-detail .hotel-detail-grid span { color: #849088; font-size: 13px; }
.visitor-product-detail .hotel-detail-grid strong { margin-top: 4px; color: #35463d; font-size: 14px; font-weight: 450; line-height: 1.6; }
.visitor-product-detail .hotel-detail-grid > div:nth-child(-n+2) strong { font-size: 15px; font-weight: 600; }
.visitor-product-detail .hotel-detail-grid > div.full strong { font-size: 14px; font-weight: 400; }

.visitor-product-detail .guide-source-section .guide-list > article > header { display: flex; align-items: baseline; justify-content: space-between; gap: 14px; }
.visitor-product-detail .guide-source-section .guide-list > article > header { align-items: center; }
.visitor-product-detail .guide-source-section .guide-list > article > header strong { min-width: 0; font-size: 16px; font-weight: 650; line-height: 1.4; }
.visitor-product-detail .guide-source-section .guide-list > article > header strong span { font-size: 13px; }
.visitor-product-detail .guide-exclusion { flex: 0 0 auto; color: #a26437; font-size: 12px; line-height: 1.4; }
.visitor-product-detail .guide-distance-note { margin: 0; padding: 7px 9px; border-radius: 7px; background: #fff7eb; color: #94612d; font-size: 12px; line-height: 1.55; }
.visitor-product-detail .guide-advice { display: grid; grid-template-columns: 96px minmax(0, 1fr); align-items: start; gap: 10px; }
.visitor-product-detail .guide-advice > b { color: #2f6f60; font-size: 13px; font-weight: 600; line-height: 1.68; }
.visitor-product-detail .guide-source-section .guide-source-line { font-size: 13px; }
.visitor-product-detail .guide-source-section .guide-content { font-size: 14px; line-height: 1.68; }
.visitor-product-detail .guide-source-section .guide-facts li { grid-template-columns: 76px minmax(0, 1fr); font-size: 13px; line-height: 1.55; }
.visitor-product-detail .guide-source-section .guide-facts .guide-how-to { grid-template-columns: 76px minmax(0, 1fr) auto; align-items: start; }
.visitor-product-detail .guide-how-to a { color: #bb6534; font-size: 13px; line-height: 1.55; text-decoration: none; white-space: nowrap; }
.visitor-product-detail .guide-how-to a:hover { color: #e86c26; text-decoration: underline; }
.visitor-product-detail .guide-source-section .guide-facts b { font-size: 13px; }
.visitor-product-detail .guide-source-section .guide-list > article > footer span { font-size: 12px; }
.visitor-product-detail .photo-detail-lead,
.visitor-product-detail .photo-detail-list,
.visitor-product-detail .review-section,
.visitor-product-detail .related-section { font-size: 14px; line-height: 1.65; }
.visitor-product-detail small { font-size: max(12px, 1em); }
.visitor-product-detail .booking-bar { min-height: 62px; }
.visitor-product-detail .booking-bar__price { align-items: baseline; gap: 6px; }
.visitor-product-detail .booking-bar__price strong { font-size: 27px; line-height: 1.2; }
.visitor-product-detail .booking-bar__price span { font-size: 13px; }
.visitor-product-detail .booking-bar :deep(.el-button),
.visitor-product-detail .booking-bar .commerce-assistant-link { min-height: 42px; height: 42px; font-size: 14px; }

@media (max-width: 1100px) {
  .visitor-product-detail .highlight-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .visitor-product-detail .detail-purchase-layout { grid-template-columns: minmax(0, 1fr); gap: 10px; }
  .visitor-product-detail .product-detail-hero { min-height: 0; aspect-ratio: 1.55; }
  .visitor-product-detail .commerce-summary { padding: 16px 4px; }
  .visitor-product-detail .commerce-head { grid-template-columns: minmax(0, 1fr); gap: 9px; }
  .visitor-product-detail .commerce-head .commerce-price { justify-self: start; }
  .visitor-product-detail .detail-anchor-nav { margin-inline: -14px !important; padding-inline: 14px; overflow-x: auto; }
  .visitor-product-detail .detail-anchor-nav button { flex: 0 0 auto; min-width: 92px; padding-inline: 8px; }
  .visitor-product-detail .detail-content { padding: 12px 0 34px; }
  .visitor-product-detail .detail-content > section { padding: 20px 0; }
  .visitor-product-detail .highlight-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .visitor-product-detail .highlight-grid > article { grid-template-rows: 132px 18px minmax(44px, auto) 1fr; }
  .visitor-product-detail .highlight-grid > article .media-image { height: 132px; }
  .visitor-product-detail .highlight-grid > article h3 { margin-inline: 10px; font-size: 15px; }
  .visitor-product-detail .highlight-grid > article p { margin-inline: 10px; font-size: 13px; }
  .visitor-product-detail .highlight-type-tag { margin-inline: 10px; }
  .visitor-product-detail .day-plan { padding: 15px 12px; }
  .visitor-product-detail .day-plan__items li { grid-template-columns: 78px minmax(0, 1fr); gap: 10px; }
  .visitor-product-detail .day-plan__entry { gap: 10px; }
  .visitor-product-detail .day-plan__entry-image { width: 84px; height: 64px; flex-basis: 84px; }
  .visitor-product-detail .fee-columns { grid-template-columns: minmax(0, 1fr); gap: 18px; }
  .visitor-product-detail .notice-list { grid-template-columns: minmax(0, 1fr); gap: 12px; }
  .visitor-product-detail .hotel-detail-grid { grid-template-columns: minmax(0, 1fr); gap: 13px; }
  .visitor-product-detail .guide-advice { grid-template-columns: minmax(0, 1fr); gap: 3px; }
  .visitor-product-detail .guide-source-section .guide-facts .guide-how-to { grid-template-columns: 76px minmax(0, 1fr); }
  .visitor-product-detail .guide-how-to a { grid-column: 2; }
}
</style>

<style scoped>
.visitor-product-detail .detail-content {
  display: flex;
  flex-direction: column;
  gap: 44px;
  width: min(100%, 1280px);
  max-width: 1280px;
  box-sizing: border-box;
  padding: 20px 0 44px;
}
.visitor-product-detail .detail-content > section { margin: 0; padding: 0 48px; }
.visitor-product-detail .detail-content .section-heading { margin: 0 0 22px; }
.visitor-product-detail .detail-content .section-heading h2::before { width: 3px; height: 18px; margin-right: 9px; }
.visitor-product-detail .highlight-grid { gap: 16px; }
.visitor-product-detail .highlight-grid > article { padding-bottom: 18px; }
.visitor-product-detail .highlight-grid > article h3,
.visitor-product-detail .highlight-grid > article p,
.visitor-product-detail .highlight-type-tag { margin-inline: 20px; }
.visitor-product-detail .day-plan { padding: 20px 24px; }
.visitor-product-detail .day-plan__items li { grid-template-columns: 88px minmax(0, 1fr); gap: 16px; }
.visitor-product-detail .day-plan__entry { gap: 16px; }
.visitor-product-detail .day-plan__entry-copy > b { display: flex; align-items: center; gap: 8px; }
.visitor-product-detail .timeline-operation-icon { display: inline-grid; width: 20px; height: 20px; flex: 0 0 auto; place-items: center; border-radius: 50%; background: #f2f3f1; color: #6d7b72; font-size: 13px; font-weight: 500; }
.visitor-product-detail .fee-columns { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 44px; max-width: 1100px; }
.visitor-product-detail .fee-group { margin-top: 14px; }
.visitor-product-detail .fee-group > strong { display: block; margin: 0 0 7px; color: #6b766e; font-size: 13px; font-weight: 600; line-height: 1.5; }
.visitor-product-detail .fee-group > p { padding: 4px 0; }
.visitor-product-detail .fee-group--public > strong { color: #45735b; }
.visitor-product-detail .notice-list,
.visitor-product-detail .hotel-detail-grid { max-width: 1100px; }
.visitor-product-detail .guide-source-section .guide-list { max-width: 1100px; }
.visitor-product-detail .guide-source-section .guide-list > article { padding: 20px 24px; }
@media (max-width: 860px) {
  .visitor-product-detail .detail-content { gap: 34px; padding-top: 16px; }
  .visitor-product-detail .detail-content > section { padding-inline: 28px; }
}
@media (max-width: 700px) {
  .visitor-product-detail .detail-content { gap: 30px; padding: 12px 0 34px; }
  .visitor-product-detail .detail-content > section { padding-inline: 16px; }
  .visitor-product-detail .detail-content .section-heading { margin-bottom: 18px; }
  .visitor-product-detail .highlight-grid { gap: 12px; }
  .visitor-product-detail .highlight-grid > article h3,
  .visitor-product-detail .highlight-grid > article p,
  .visitor-product-detail .highlight-type-tag { margin-inline: 12px; }
  .visitor-product-detail .day-plan { padding: 16px; }
  .visitor-product-detail .day-plan__items li { grid-template-columns: 76px minmax(0, 1fr); gap: 12px; }
  .visitor-product-detail .day-plan__entry { gap: 10px; }
  .visitor-product-detail .fee-columns { grid-template-columns: minmax(0, 1fr); gap: 20px; }
  .visitor-product-detail .guide-source-section .guide-list > article { padding: 16px; }
}
</style>

<style scoped>
/* Unified visitor storefront details. */
.visitor-product-detail { width: min(100%, 1200px); max-width: 1200px; margin: 0 auto; padding: 0 0 116px; background: transparent; box-sizing: border-box; }
.visitor-product-detail .detail-purchase-layout { display: grid; grid-template-columns: minmax(0, 1.22fr) minmax(0, 1fr); gap: 30px; align-items: stretch; width: 100%; margin: 0 auto 0; }
.visitor-product-detail .product-detail-hero { width: 100%; max-width: none; min-height: 490px; margin: 0; border-radius: 14px; }
.visitor-product-detail .commerce-summary { display: flex; flex-direction: column; justify-content: center; gap: 20px; width: 100%; max-width: none; min-width: 0; margin: 0; padding: 34px; border: 0; border-radius: 14px; background: #fff; box-shadow: 0 6px 24px rgba(30, 54, 43, .06); box-sizing: border-box; }
.visitor-product-detail .commerce-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 14px; }
.visitor-product-detail .commerce-title { min-width: 0; }
.visitor-product-detail .commerce-title h1 { display: -webkit-box; overflow: hidden; margin: 0; color: #26362e; font-size: clamp(26px, 2.2vw, 28px); font-weight: 680; line-height: 1.28; letter-spacing: -.35px; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.visitor-product-detail .commerce-title > p { margin: 8px 0 0; color: #65736b; font-size: 14px; line-height: 1.6; }
.visitor-product-detail .commerce-tags { gap: 7px; margin-top: 12px; }
.visitor-product-detail .commerce-tags span { padding: 5px 9px; border-radius: 999px; font-size: 12px; }
.visitor-product-detail .commerce-price { align-self: start; min-width: max-content; padding-top: 1px; text-align: right; }
.visitor-product-detail .commerce-price strong { color: #dd6524; font-size: 27px; font-weight: 700; line-height: 1.1; white-space: nowrap; }
.visitor-product-detail .commerce-price span { margin-left: 4px; color: #7e8981; font-size: 13px; white-space: nowrap; }
.visitor-product-detail .commerce-inclusion { display: grid; gap: 6px; margin: 0; padding: 0; border: 0; }
.visitor-product-detail .commerce-inclusion > span { color: #89938c; font-size: 12px; }
.visitor-product-detail .commerce-inclusion > strong { color: #354940; font-size: 14px; font-weight: 600; line-height: 1.65; }
.visitor-product-detail .date-picker-row { flex-wrap: nowrap; gap: 8px; margin: 0; padding: 0; border: 0; }
.visitor-product-detail .date-picker-row > b { margin-right: 2px; color: #738078; font-size: 13px; }
.visitor-product-detail .date-chip { min-width: 82px; padding: 8px 9px; border: 1px solid #e0e5e0; border-radius: 9px; background: #fff; }
.visitor-product-detail .date-chip strong { font-size: 13px; }
.visitor-product-detail .date-chip small { font-size: 12px; }
.visitor-product-detail .date-chip.active { border-color: #237966; background: #eef7f2; }
.visitor-product-detail .date-chip.is-sold-out { border-color: #ead1cd; background: #fbf2f0; color: #9e5d55; cursor: not-allowed; opacity: .88; }
.visitor-product-detail .date-chip:disabled { cursor: not-allowed; }
.visitor-product-detail .date-chip:disabled:hover { transform: none; }
.visitor-product-detail .soldout-inline { display: flex; align-items: center; gap: 12px; margin: -12px 0 0; color: #9e5d55; font-size: 13px; }
.visitor-product-detail .soldout-inline button { padding: 0; border: 0; background: none; color: #a65c31; font: inherit; text-decoration: underline; cursor: pointer; }
.visitor-product-detail .commerce-stay-note { margin: -10px 0 0; color: #77827b; font-size: 13px; line-height: 1.5; }
.visitor-product-detail .commerce-purchase-actions { display: flex; align-items: center; gap: 10px; margin: 0; }
.visitor-product-detail .commerce-purchase-actions :deep(.el-button),
.visitor-product-detail .commerce-purchase-actions .commerce-assistant-link { height: 46px; min-height: 46px; padding: 0 21px; border-radius: 9px; font-size: 14px; font-weight: 600; }
.visitor-product-detail .commerce-purchase-actions .commerce-assistant-link { border: 1px solid #d8e2db; background: #fff; color: #345b49; cursor: pointer; }
.visitor-product-detail .commerce-purchase-actions .commerce-assistant-link:hover { border-color: #9fbdab; background: #f8fbf8; }
.visitor-product-detail .detail-anchor-nav { width: 100%; max-width: 1200px; margin: 24px auto 0; border: 0; border-bottom: 1px solid #e6e9e5; box-shadow: none; }
.visitor-product-detail .detail-content { width: 100%; max-width: 1200px; gap: 44px; padding: 28px 0 44px; }
.visitor-product-detail .detail-content > section { padding-inline: 48px; border: 0; }
.visitor-product-detail .detail-content .section-heading { margin: 0 0 22px; }
.visitor-product-detail .highlight-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.visitor-product-detail .highlight-grid > article { border: 1px solid #e7e9e5; border-radius: 12px; box-shadow: none; }
.visitor-product-detail .highlight-type-tag { margin: 14px 18px 0; font-size: 12px; }
.visitor-product-detail .highlight-grid > article h3 { margin: 7px 18px 0; font-size: 16px; }
.visitor-product-detail .highlight-grid > article p { margin: 6px 18px 18px; font-size: 14px; line-height: 1.6; }
.visitor-product-detail .day-plan { border-color: #e8e3dc; box-shadow: none; }
.visitor-product-detail .day-plan__item--formal .day-plan__time b { color: #9b642e; }
.visitor-product-detail .day-plan__item--operation .day-plan__time b { color: #68756d; }
.visitor-product-detail .day-plan__item--free { border-radius: 9px; background: #f5f7f4; }
.visitor-product-detail .day-plan__item--free .day-plan__time b { color: #78857c; }
.visitor-product-detail .day-plan__suggestions > b { color: #78857c; }
.visitor-product-detail .fee-columns { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 40px; max-width: 960px; }
.visitor-product-detail .fee-columns > div { padding: 0; border: 0; background: transparent; }
.visitor-product-detail .fee-columns h3 { margin-bottom: 12px; font-size: 16px; }
.visitor-product-detail .fee-columns p { color: #59665e; font-size: 14px; }
.visitor-product-detail .fee-group > strong { color: #56685d; }
.visitor-product-detail .fee-group--public > strong { color: #38725c; }
.visitor-product-detail .notice-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; max-width: 960px; padding: 0; border: 0; background: transparent; }
.visitor-product-detail .notice-list p { gap: 6px; }
.visitor-product-detail .hotel-detail-grid { max-width: 960px; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px 32px; }
.visitor-product-detail .hotel-detail-grid > .full { grid-column: 1 / -1; }
.visitor-product-detail .guide-source-section .guide-list { grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: 1080px; gap: 16px; }
.visitor-product-detail .guide-source-section .guide-list > article { padding: 20px; border-color: #e6e9e4; background: #f7f9f6; box-shadow: none; }
.visitor-product-detail .guide-source-section .guide-advice { display: block; margin: 10px 0 12px; }
.visitor-product-detail .guide-source-section .guide-advice > b { display: none; }
.visitor-product-detail .guide-content { margin: 0; color: #56655d; font-size: 14px; line-height: 1.65; }
.visitor-product-detail .guide-source-section .guide-facts { gap: 8px; }
.visitor-product-detail .guide-source-section .guide-facts li { grid-template-columns: 78px minmax(0, 1fr); font-size: 13px; }
.visitor-product-detail .guide-source-section .guide-facts .guide-address { grid-template-columns: 56px minmax(0, 1fr) auto; align-items: start; }
.visitor-product-detail .guide-address a { color: #a95f31; font-size: 12px; line-height: 1.6; text-decoration: none; white-space: nowrap; }
.visitor-product-detail .guide-how-to { grid-template-columns: 56px minmax(0, 1fr) !important; }
.visitor-product-detail .booking-bar { position: fixed; left: 50%; bottom: 12px; transform: translateX(-50%); display: flex; align-items: center; justify-content: space-between; gap: 24px; width: min(1200px, calc(100% - 36px)); max-width: 1200px; min-height: 68px; padding: 10px 22px; border: 1px solid #e4e7e2; border-radius: 12px; box-sizing: border-box; }
.visitor-product-detail .booking-bar > div:first-child { display: flex !important; }
.visitor-product-detail .booking-bar__left { display: flex; align-items: baseline; gap: 12px; min-width: 0; }
.visitor-product-detail .booking-bar__price { display: flex; align-items: baseline; gap: 5px; }
.visitor-product-detail .booking-bar__price strong { color: #dc6523; font-size: 26px; }
.visitor-product-detail .booking-bar__price span { display: inline; color: #768078; font-size: 13px; }
.visitor-product-detail .booking-bar__stock { color: #6c786f; font-size: 13px; white-space: nowrap; }
.visitor-product-detail .booking-bar__right { gap: 10px; }
.visitor-product-detail .booking-bar .assistant-action { min-width: 150px; height: 44px; border: 1px solid #d4dfd7; border-radius: 9px; background: #fff; color: #345b49; font-size: 14px; }
.visitor-product-detail .booking-bar :deep(.el-button) { min-width: 132px; height: 44px; border-radius: 9px; font-size: 14px; }
@media (max-width: 900px) {
  .visitor-product-detail .detail-purchase-layout { grid-template-columns: minmax(0, 1.05fr) minmax(0, .95fr); gap: 18px; }
  .visitor-product-detail .commerce-summary { padding: 24px; }
  .visitor-product-detail .highlight-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .visitor-product-detail .detail-content > section { padding-inline: 30px; }
}
@media (max-width: 700px) {
  .visitor-product-detail { padding-bottom: 104px; }
  .visitor-product-detail .detail-purchase-layout { grid-template-columns: 1fr; gap: 10px; }
  .visitor-product-detail .product-detail-hero { min-height: 0; aspect-ratio: 1.55; }
  .visitor-product-detail .commerce-summary { padding: 20px; gap: 16px; }
  .visitor-product-detail .commerce-head { grid-template-columns: minmax(0, 1fr) auto; }
  .visitor-product-detail .commerce-title h1 { font-size: 24px; }
  .visitor-product-detail .commerce-price strong { font-size: 23px; }
  .visitor-product-detail .detail-content { gap: 36px; padding: 22px 0 32px; }
  .visitor-product-detail .detail-content > section { padding-inline: 18px; }
  .visitor-product-detail .highlight-grid { gap: 12px; }
  .visitor-product-detail .highlight-type-tag { margin-inline: 12px; }
  .visitor-product-detail .highlight-grid > article h3 { margin-inline: 12px; font-size: 15px; }
  .visitor-product-detail .highlight-grid > article p { margin-inline: 12px; font-size: 13px; }
  .visitor-product-detail .notice-list { grid-template-columns: 1fr; gap: 14px; }
  .visitor-product-detail .hotel-detail-grid { grid-template-columns: 1fr 1fr; gap: 14px; }
  .visitor-product-detail .guide-source-section .guide-list { grid-template-columns: 1fr; }
  .visitor-product-detail .guide-source-section .guide-list > article { padding: 16px; }
  .visitor-product-detail .guide-source-section .guide-facts .guide-address { grid-template-columns: 50px minmax(0, 1fr); }
  .visitor-product-detail .guide-address a { grid-column: 2; }
  .visitor-product-detail .booking-bar { bottom: 8px; width: calc(100% - 16px); min-height: 62px; padding: 8px 10px; gap: 8px; }
  .visitor-product-detail .booking-bar__left { display: grid; gap: 0; }
  .visitor-product-detail .booking-bar__price strong { font-size: 20px; }
  .visitor-product-detail .booking-bar__stock { font-size: 11px; }
  .visitor-product-detail .booking-bar__right { gap: 6px; }
  .visitor-product-detail .booking-bar .assistant-action { min-width: 0; padding-inline: 9px; font-size: 12px; }
  .visitor-product-detail .booking-bar :deep(.el-button) { min-width: 0; padding-inline: 11px; font-size: 12px; }
}

/* Final storefront refinements: give the hero an inset frame and keep the
   summary title, price and date choices in a clear vertical order. */
.visitor-product-detail .detail-purchase-layout { align-items: start; }
.visitor-product-detail .product-detail-hero {
  align-self: start;
  height: 438px;
  min-height: 0;
  box-sizing: border-box;
  padding: 12px;
  border-radius: 16px;
  background: #eef1ed;
}
.visitor-product-detail .product-detail-hero > .media-image,
.visitor-product-detail .product-detail-hero__veil { inset: 12px; width: auto; height: auto; min-height: 0; border-radius: 10px; }
.visitor-product-detail .product-detail-hero__veil { background: linear-gradient(0deg, rgba(12,39,34,.34), transparent 50%); }
.visitor-product-detail .commerce-head { display: block; }
.visitor-product-detail .commerce-title { display: grid; align-content: start; }
.visitor-product-detail .commerce-title h1 { margin: 0; }
.visitor-product-detail .commerce-title > .commerce-price {
  display: inline-flex !important;
  align-self: start;
  justify-self: start;
  align-items: baseline;
  gap: 5px;
  width: fit-content;
  min-width: 0;
  margin: 9px 0 0;
  padding: 0;
  text-align: left;
}
.visitor-product-detail .commerce-title > .commerce-price strong { font-size: 27px; }
.visitor-product-detail .commerce-title > .commerce-price span { margin: 0; }
.visitor-product-detail .highlight-grid { grid-auto-rows: auto; align-items: stretch; }
.visitor-product-detail .highlight-grid > article {
  height: auto;
  grid-template-rows: 152px auto auto auto;
  align-content: start;
  gap: 6px;
  padding-bottom: 14px;
}
.visitor-product-detail .highlight-grid > article .media-image { height: 152px; }
.visitor-product-detail .highlight-image-empty { display: grid; min-height: 152px; place-items: center; background: linear-gradient(135deg, #f1f5f1, #e8eee9); color: #829087; font-size: 12px; }
.visitor-product-detail .highlight-grid > article h3 { min-height: 0; margin-top: 2px; }
.visitor-product-detail .highlight-grid > article p { margin-top: 0; margin-bottom: 2px; }
.visitor-product-detail .date-picker-row { align-items: center; justify-content: flex-start !important; align-self: flex-start; gap: 8px; flex-wrap: nowrap; width: 100%; min-width: 0; overflow-x: auto; overflow-y: hidden; }
.visitor-product-detail .date-picker-row > b { display: inline-flex; flex: 0 0 auto; width: max-content !important; margin: 0 3px 0 0; white-space: nowrap; }
.visitor-product-detail .date-picker-row > .date-chip { flex: 0 0 auto; margin: 0; }
.visitor-product-detail .date-chip {
  display: grid;
  width: 84px;
  height: 84px;
  min-width: 84px;
  flex: 0 0 84px;
  align-content: center;
  justify-items: center;
  gap: 8px;
  box-sizing: border-box;
  padding: 6px 4px;
  text-align: center;
  white-space: normal;
}
.visitor-product-detail .date-chip strong { color: #34463c; font-size: 13px; line-height: 1.25; }
.visitor-product-detail .date-chip small { color: #738078; font-size: 11.5px; line-height: 1.25; }
.visitor-product-detail .day-plan__item--free { background: transparent !important; }
.visitor-product-detail .day-plan__title { display: flex; flex-wrap: nowrap; align-items: baseline; gap: 4px 8px; min-width: 0; }
.visitor-product-detail .day-plan__title > span:not(.timeline-operation-icon) { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.visitor-product-detail .day-plan__address-inline { min-width: 0; overflow: hidden; color: #7b877f; font-size: 12px; font-weight: 400; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.visitor-product-detail .guide-source-section .guide-facts .guide-address { align-items: center; }
.visitor-product-detail .guide-address a {
  display: inline-flex;
  grid-column: auto;
  align-items: center;
  justify-self: start;
  min-height: 0;
  padding: 2px 6px;
  border: 1px solid #e7e8e3;
  border-radius: 999px;
  background: #fff;
  color: #9b6038;
  font-size: 11px;
  line-height: 1.3;
}
.visitor-product-detail .guide-facts li { font-size: 13px; line-height: 1.6; }
.visitor-product-detail .guide-facts b { font-size: 13px; }
.visitor-product-detail .room-choice-inline { display: grid; gap: 8px; min-width: 0; margin: -2px 0 0; }
.visitor-product-detail .room-choice-inline__head { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 12px; }
.visitor-product-detail .room-choice-inline__head .section-kicker { color: #738078; font-size: 13px; font-weight: 600; }
.visitor-product-detail .room-choice-inline__head .section-kicker small { margin-left: 5px; color: #89938c; font-size: 11px; font-weight: 400; }
.visitor-product-detail .room-choice-inline__arrows { display: flex; flex: 0 0 auto; gap: 6px; }
.visitor-product-detail .room-choice-inline__arrows button { display: grid; width: 30px; height: 30px; place-items: center; border: 1px solid #dce4dd; border-radius: 8px; background: #fff; color: #476451; font-size: 20px; line-height: 1; cursor: pointer; }
.visitor-product-detail .room-choice-inline__arrows button:hover:not(:disabled) { border-color: #9eb7a6; background: #f4f8f4; }
.visitor-product-detail .room-choice-inline__arrows button:disabled { background: #f6f7f5; color: #b7beb8; cursor: not-allowed; opacity: .8; }
.visitor-product-detail .room-choice-inline__track { display: grid; grid-auto-columns: calc((100% - 10px) / 2); grid-auto-flow: column; grid-template-columns: none; gap: 10px; min-width: 0; margin: 0; padding: 1px 1px 5px; overflow-x: auto; overflow-y: hidden; overscroll-behavior-inline: contain; scroll-behavior: smooth; scroll-snap-type: x mandatory; scrollbar-width: thin; }
.visitor-product-detail .room-choice-inline__track > button { min-width: 0; min-height: 74px; scroll-snap-align: start; }
.visitor-product-detail .room-choice-inline__track > button:disabled { cursor: not-allowed; }
.visitor-product-detail .room-choice-inline__track > button.disabled { opacity: .58; }
@media (max-width: 900px) {
  .visitor-product-detail .product-detail-hero { height: auto; min-height: 0; aspect-ratio: 1.55; }
}
@media (max-width: 700px) {
  .visitor-product-detail .product-detail-hero { padding: 9px; border-radius: 13px; }
  .visitor-product-detail .product-detail-hero > .media-image,
  .visitor-product-detail .product-detail-hero__veil { inset: 9px; border-radius: 8px; }
  .visitor-product-detail .commerce-title > .commerce-price { margin-top: 7px; }
  .visitor-product-detail .date-picker-row { flex-wrap: wrap; }
  .visitor-product-detail .room-choice-inline__track { grid-auto-columns: calc((100% - 8px) / 2); gap: 8px; }
  .visitor-product-detail .room-choice-inline__track > button { min-height: 70px; padding: 9px; }
  .visitor-product-detail .date-chip { width: 78px; height: 78px; min-width: 78px; flex-basis: 78px; }
  .visitor-product-detail .day-plan__title { flex-wrap: wrap; }
  .visitor-product-detail .day-plan__address-inline { flex-basis: 100%; margin-left: 0; white-space: normal; }
  .visitor-product-detail .highlight-grid > article { grid-template-rows: 126px auto auto auto; }
  .visitor-product-detail .highlight-grid > article .media-image { height: 126px; }
  .visitor-product-detail .guide-source-section .guide-facts .guide-address { grid-template-columns: 50px minmax(0, 1fr) auto; }
  .visitor-product-detail .guide-address a { grid-column: auto; }
}
</style>

<style scoped>
/* Keep the gallery and purchase details together as one aligned product card. */
.visitor-product-detail .detail-purchase-layout { display:block; width:100%; margin:0 auto; }
.visitor-product-detail .product-detail-card {
  display:grid;
  grid-template-columns:minmax(0, 1.18fr) minmax(0, 1fr);
  align-items:stretch;
  gap:20px;
  width:100%;
  padding:12px;
  border:1px solid #e7eae6;
  border-radius:16px;
  background:#fff;
  box-shadow:0 7px 24px rgba(30,54,43,.055);
  box-sizing:border-box;
}
.visitor-product-detail .product-detail-hero {
  justify-self:start;
  align-self:center;
  width:100%;
  height:438px;
  min-height:0;
  margin:0;
  padding:0;
  border-radius:12px;
  background:transparent;
  overflow:hidden;
}
.visitor-product-detail .product-detail-hero > .media-image,
.visitor-product-detail .product-detail-hero__veil { inset:0; width:100%; height:100%; border-radius:12px; }
.visitor-product-detail .commerce-summary {
  justify-content:center;
  min-width:0;
  padding:22px 24px 22px 4px;
  border:0;
  border-radius:0;
  background:transparent;
  box-shadow:none;
}
.visitor-product-detail .room-choice-inline__head .section-kicker small { display:none; }
.visitor-product-detail .room-choice-inline__track { grid-auto-columns:calc((100% - 20px) / 3); gap:10px; }
.visitor-product-detail .room-choice-inline__track > button {
  display:grid;
  align-content:center;
  gap:5px;
  height:62px;
  min-height:62px;
  padding:8px 10px;
  border:1px solid #e0e6e1;
  border-radius:9px;
  background:#fff;
  text-align:left;
  transition:border-color .18s ease,background .18s ease,box-shadow .18s ease;
}
.visitor-product-detail .room-choice-inline__track > button.active { border-color:#43836c; background:#f0f7f2; box-shadow:0 0 0 1px rgba(67,131,108,.08); }
.visitor-product-detail .room-choice-inline__track > button:hover:not(:disabled) { border-color:#85ad97; background:#f7faf7; }
.visitor-product-detail .room-choice-inline__track > button > b { overflow:hidden; color:#34483d; font-size:12px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
.visitor-product-detail .room-choice-inline__summary { display:flex; min-width:0; align-items:baseline; justify-content:space-between; gap:7px; }
.visitor-product-detail .room-choice-inline__summary strong { color:#d95f24; font-size:12px; font-weight:650; white-space:nowrap; }
.visitor-product-detail .room-choice-inline__summary small { overflow:hidden; color:#748078; font-size:10.5px; text-overflow:ellipsis; white-space:nowrap; }
.visitor-product-detail .room-choice-inline__track > button.disabled { background:#f8f6f5; }
.visitor-product-detail .highlight-grid { grid-auto-rows:auto; align-items:start; }
.visitor-product-detail .highlight-grid > article {
  position:relative;
  z-index:0;
  height:326px;
  max-height:326px;
  overflow:hidden;
  transition:max-height .24s ease,height .24s ease,box-shadow .2s ease,border-color .2s ease;
}
.visitor-product-detail .highlight-grid > article p {
  display:-webkit-box;
  overflow:hidden;
  -webkit-box-orient:vertical;
  -webkit-line-clamp:3;
}
.visitor-product-detail .highlight-grid > article:hover,
.visitor-product-detail .highlight-grid > article:focus-visible {
  z-index:3;
  height:auto;
  max-height:620px;
  overflow:visible;
  border-color:#cbd9cf;
  background:#fff;
  box-shadow:0 12px 28px rgba(30,54,43,.12);
}
.visitor-product-detail .highlight-grid > article:hover p,
.visitor-product-detail .highlight-grid > article:focus-visible p { display:block; overflow:visible; }
.visitor-product-detail .highlight-grid > article:focus-visible { outline:2px solid #739582; outline-offset:2px; }
@media (max-width:900px) {
  .visitor-product-detail .product-detail-card { grid-template-columns:minmax(0, 1.05fr) minmax(0, .95fr); gap:14px; }
  .visitor-product-detail .product-detail-hero { height:390px; }
  .visitor-product-detail .commerce-summary { padding:20px 18px 20px 2px; }
}
@media (max-width:700px) {
  .visitor-product-detail .product-detail-card { grid-template-columns:minmax(0, 1fr); gap:10px; padding:9px; }
  .visitor-product-detail .product-detail-hero { height:auto; aspect-ratio:1.55; }
  .visitor-product-detail .commerce-summary { padding:14px 8px 10px; gap:14px; }
  .visitor-product-detail .room-choice-inline__track > button { height:58px; min-height:58px; padding:7px 8px; }
  .visitor-product-detail .room-choice-inline__track { grid-auto-columns:calc((100% - 8px) / 2); gap:8px; }
  .visitor-product-detail .highlight-grid > article { height:300px; max-height:300px; }
}
</style>
