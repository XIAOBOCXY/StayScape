<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { showToast } from 'vant'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import { primaryFromRefinedProduct, validationChangeNote } from './productGenerationState.mjs'

type AnyRecord = Record<string, any>

// 与后端 product_advisor_service.ADVISOR_CONTRACT_VERSION 保持一致；
// 版本不一致时不复用历史快照，改为重新生成当前经营判断。
const ADVISOR_CONTRACT_VERSION = 11

const overview = ref<AnyRecord>({})
const conversations = ref<AnyRecord[]>([])
const proposals = ref<AnyRecord[]>([])
const orders = ref<AnyRecord>({ total: 0, confirmed: 0, held: 0, cancelled: 0, confirmed_revenue: '0', categories: [], orders: [] })
const advisor = ref<AnyRecord | null>(null)
const activeConversationId = ref<number | null>(null)
const brief = ref('')
const loading = ref(false)
const loadError = ref('')
const dataReady = ref(false)
// 经营分析是否已跑完一轮（成功或失败都算完成），步骤条只表示业务进度，不锁死后续工作。
const analysisDone = ref(false)
const submitting = ref(false)
const processingMessage = ref('正在读取未来房态、近期成交、合作资源、天气与地点信息…')
const advisorAnalysisSignature = ref('')
const advisorLoadedThisVisit = ref(false)
const loadedAt = ref('')
const selectedStage = ref<number | null>(1)
// 经营分析默认展示房态，其他数据通过分类按钮切换。
const panel = ref<'inventory' | 'resources' | 'orders' | 'weather' | 'knowledge'>('inventory')
const evidenceLoaded = ref<string[]>([])
const evidenceLoading = ref('')
const evidenceLoadingSections = ref<string[]>([])
const evidenceErrors = ref<Record<string, string>>({})
const evidenceError = ref('')
const weatherFetchState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const weatherUpdatedAt = ref('')
const evidenceDateFilters = ref<Record<string, string>>({ inventory: '', resources: '', orders: '', weather: '', knowledge: '' })
const evidencePages = ref<Record<string, number>>({ inventory: 1, resources: 1, services: 1, orders: 1, weather: 1, knowledge: 1 })
const evidencePageSize = 12
const adviceVariant = ref(0)
const expandedDiagnosisKey = ref('')
const diagnosisGridRef = ref<HTMLElement | null>(null)
const evidenceRequests = new Map<string, Promise<void>>()
// 本次会话真正生成出来的候选：生成后直接进入「预览与发布」，不再单独占用一个确认步骤。
const sessionProposalIds = ref<number[]>([])
const resolvedCandidateCount = ref(0)
// 主方案下方「调整这个方案」的展开状态：替代资源默认不展示。
const activeAdjust = ref<'' | 'resources' | 'price' | 'crowd' | 'route' | 'service'>('')
const resourceTab = ref<'experience' | 'hotel'>('experience')
// 价格调整的目标值，以及重算完成后的卡片高亮，避免「点了没反应」的错觉。
const priceTarget = ref('')
const cardFlash = ref(false)
const detailTab = ref<'basis' | 'value' | 'risk' | 'compare'>('basis')
const editingProduct = ref<AnyRecord | null>(null)
const refinements = ref<AnyRecord[]>([])
const previousPrimary = ref<AnyRecord | null>(null)
const changeNote = ref('')
const changeDetails = ref<AnyRecord[]>([])
const historyOpen = ref(false)
const inventoryRooms = ref<AnyRecord[]>([])
const targetInventoryKey = ref('')
const batchRoomIds = ref<number[]>([])
const batchApplying = ref(false)
const batchResult = ref<AnyRecord | null>(null)
const copyDraft = ref<AnyRecord | null>(null)
const copySaving = ref(false)
const copyRewriting = ref(false)
// 每次指令带来的变化，比聊天记录更接近运营真正关心的信息。
const operationLog = ref<AnyRecord[]>([])
const operationGroups = computed<AnyRecord[]>(() => {
  const groups: AnyRecord[] = []
  for (const item of operationLog.value) {
    const stamp = Number(item.stamp || 0)
    const previous = groups[groups.length - 1]
    if (previous && stamp && previous.lastStamp && previous.lastStamp - stamp <= 3 * 60 * 1000) {
      previous.items.push(item)
      previous.lastStamp = stamp
      continue
    }
    groups.push({ title: '本轮方案调整', items: [item], lastStamp: stamp })
  }
  return groups
})

const activeConversation = computed(() => conversations.value.find((item) => Number(item.id) === activeConversationId.value) || null)
const pressure = computed<AnyRecord>(() => (overview.value.inventory_pressure as AnyRecord) || {})
const focusRoom = computed<AnyRecord | null>(() => (pressure.value.focus_room as AnyRecord) || null)
const insights = computed<AnyRecord>(() => (overview.value.operations_insights as AnyRecord) || {})
const availableServices = computed<AnyRecord[]>(() => {
  const currentServices = (primarySpec.value?.service_options || []) as AnyRecord[]
  const overviewServices = (insights.value.available_services || []) as AnyRecord[]
  const servicesByKey = new Map<string, AnyRecord>()
  for (const item of [...overviewServices, ...currentServices]) {
    const key = String(item.id || item.name || item.service_name || '')
    if (key) servicesByKey.set(key, { ...(servicesByKey.get(key) || {}), ...item, name: item.name || item.service_name })
  }
  const selectedIds = new Set(((primarySpec.value?.services || []) as AnyRecord[]).map((item) => String(item.id || item.name || '')))
  return [...servicesByKey.values()].filter((item) => Number(item.available_quantity ?? item.availableQuantity ?? 0) > 0 || item.is_selected || selectedIds.has(String(item.id || item.name || item.service_name || '')))
})
const availableAddResources = computed<AnyRecord[]>(() => {
  const options = (primarySpec.value?.add_resource_options || []) as AnyRecord[]
  return options.map((item) => ({ ...item, kind: '体验', is_selected: false }))
})
const availableHotelPerks = computed<AnyRecord[]>(() => {
  const selectedKeys = new Set(((primarySpec.value?.services || []) as AnyRecord[]).flatMap((item) => [String(item.id || ''), String(item.name || item.service_name || '')]).filter(Boolean))
  const options: AnyRecord[] = availableServices.value.map((item) => ({
    ...item,
    kind: '酒店权益',
    name: item.name || item.service_name,
    is_selected: Boolean(item.is_selected) || selectedKeys.has(String(item.id || '')) || selectedKeys.has(String(item.name || item.service_name || '')),
    recommendation_score: Number(item.recommendation_score ?? 55),
    recommendation_level: item.recommendation_level || 'caution',
    recommendation_label: item.recommendation_label || '可选权益',
  }))
  const byName = new Map(options.map((item) => [String(item.name || ''), item]))
  for (const service of ((primarySpec.value?.services || []) as AnyRecord[])) {
    const name = String(service.name || '')
    if (!name || byName.has(name)) continue
    byName.set(name, { ...service, kind: '酒店权益', is_selected: true, addable: false, recommendation_label: '已加入方案', fit_label: '已加入方案' })
  }
  return [...byName.values()].sort((a: AnyRecord, b: AnyRecord) => Number(b.recommendation_score || 0) - Number(a.recommendation_score || 0)
  || Number(b.sets ?? b.available_quantity ?? 0) - Number(a.sets ?? a.available_quantity ?? 0))
})
const selectedExperienceCards = computed<AnyRecord[]>(() => ((primarySpec.value?.experiences || []) as AnyRecord[]).map((item) => ({
  ...item,
  kind: '体验',
  is_selected: true,
  addable: false,
  recommendation_label: '已加入方案',
  fit_label: '已加入方案',
  sets: item.sets ?? item.remaining_capacity,
  remaining_capacity: item.remaining_capacity ?? item.capacity,
})))
const allExperienceCards = computed<AnyRecord[]>(() => {
  const selectedNames = new Set(selectedExperienceCards.value.map((item) => String(item.name || '')))
  return [...selectedExperienceCards.value, ...availableAddResources.value.filter((item) => !selectedNames.has(String(item.name || '')))]
  .sort((a, b) => Number(Boolean(b.is_selected)) - Number(Boolean(a.is_selected))
    || Number(b.recommendation_score || 0) - Number(a.recommendation_score || 0)
    || String(a.name || '').localeCompare(String(b.name || ''), 'zh-CN'))
})
const weatherLabel = computed(() => {
  if (weatherFetchState.value === 'loading' || weatherFetchState.value === 'idle') return '天气获取中'
  if (weatherFetchState.value === 'error') return '天气获取失败'
  if (overview.value.weather?.usable === false) return '天气待核验'
  if (!overview.value.weather) return '暂无逐日预报'
  const scenario = String(overview.value.weather?.scenario || '')
  const base = { RAIN: '有降雨', SUNNY: '晴天', CLOUDY: '多云' }[scenario] || '天气读取中'
  const low = overview.value.weather?.temperature_min
  const high = overview.value.weather?.temperature_max
  return low !== null && low !== undefined && high !== null && high !== undefined
    ? `${base} ${Math.round(low)}–${Math.round(high)}℃`
    : base
})
const knowledgeTotal = computed(() => Number(overview.value.knowledge_total ?? (overview.value.knowledge || []).length ?? 0))
const roomEvidenceRows = computed<AnyRecord[]>(() => {
  const today = new Date()
  const end = new Date(today)
  end.setDate(end.getDate() + Number(pressure.value.window_days ?? 17))
  const startKey = localDateKey(today)
  const endKey = localDateKey(end)
  return inventoryRooms.value
    .filter((room) => room.status !== 'DISABLED' && String(room.available_date || '') >= startKey && String(room.available_date || '') < endKey)
    .sort((a, b) => String(a.available_date).localeCompare(String(b.available_date)) || String(a.room_type).localeCompare(String(b.room_type)))
})
const roomEvidenceTotal = computed(() => roomEvidenceRows.value.reduce((sum, room) => sum + Number(room.available_count || 0), 0))
const roomEvidenceDateCount = computed(() => new Set(roomEvidenceRows.value.map((room) => room.available_date)).size)
const roomEvidenceTypeCount = computed(() => new Set(roomEvidenceRows.value.map((room) => displayValue(room.room_type, '未命名房型'))).size)
const inventoryCountQuartiles = computed(() => {
  const counts = roomEvidenceRows.value.map((room) => Number(room.available_count || 0)).sort((a, b) => a - b)
  if (!counts.length) return { low: 0, high: 0 }
  return { low: counts[Math.floor((counts.length - 1) * 0.25)], high: counts[Math.floor((counts.length - 1) * 0.75)] }
})
function inventoryAvailabilityState(row: AnyRecord) {
  const count = Number(row.available_count || 0)
  if (count <= 0 || ['SOLD_OUT', 'DISABLED'].includes(String(row.status || '').toUpperCase())) return { label: '暂无余量', tone: 'muted' }
  const { low, high } = inventoryCountQuartiles.value
  if (high > low && count >= high) return { label: '余量较多', tone: 'high' }
  if (high > low && count <= low) return { label: '余量偏少', tone: 'warning' }
  return { label: '可售', tone: 'good' }
}
const resourceEvidenceRows = computed<AnyRecord[]>(() => (insights.value.resource_evidence || []) as AnyRecord[])
const serviceEvidenceRows = computed<AnyRecord[]>(() => (insights.value.service_evidence || []) as AnyRecord[])
const sellableResourceEvidenceRows = computed<AnyRecord[]>(() => resourceEvidenceRows.value.filter((row) => String(row.status || '').toUpperCase() === 'AVAILABLE' && row.package_enabled && Number(row.remaining_capacity || 0) > 0))
const sellableServiceEvidenceRows = computed<AnyRecord[]>(() => serviceEvidenceRows.value.filter((row) => String(row.status || '').toUpperCase() === 'AVAILABLE' && Number(row.available_quantity || 0) > 0))
const weatherEvidenceRows = computed<AnyRecord[]>(() => (overview.value.weather_forecasts || []) as AnyRecord[])
const weatherUsableRows = computed<AnyRecord[]>(() => weatherEvidenceRows.value.filter((row) => row.usable))
const weatherRainDays = computed(() => weatherUsableRows.value.filter((row) => row.scenario === 'RAIN').length)
const evidenceSections = ['inventory', 'orders', 'resources', 'weather', 'knowledge'] as const
function evidenceState(section: string) {
  if (evidenceLoadingSections.value.includes(section)) return 'loading'
  if (evidenceErrors.value[section]) return 'error'
  if (evidenceLoaded.value.includes(section)) return 'ready'
  return 'pending'
}
function evidenceStateLabel(section: string) {
  return ({ loading: '正在采集', ready: '已分析', error: '暂不可用', pending: '等待采集' } as Record<string, string>)[evidenceState(section)]
}
function diagnosisStateLabel(item: AnyRecord) {
  if (item.key !== 'summary') return evidenceStateLabel(String(item.key || ''))
  if (evidenceSettledCount.value === evidenceSections.length) return evidenceReadyCount.value === evidenceSections.length ? '已形成判断' : '部分数据可用'
  return evidenceReadyCount.value ? '分析中' : '等待采集'
}
const evidenceSettledCount = computed(() => evidenceSections.filter((section) => evidenceState(section) === 'ready' || evidenceState(section) === 'error').length)
const evidenceReadyCount = computed(() => evidenceSections.filter((section) => evidenceState(section) === 'ready').length)
const weatherStatusText = computed(() => {
  if (weatherFetchState.value === 'loading' || weatherFetchState.value === 'idle') return '天气数据获取中，请稍候'
  if (weatherFetchState.value === 'error') return '天气数据获取失败；本轮不把未知天气当作确定事实，生成时保留室内替代安排。'
  if (!weatherEvidenceRows.value.length || !weatherUsableRows.value.length) return '暂时没有可用于分析的逐日预报；本轮不把未知天气当作确定事实，生成时保留室内替代安排。'
  return `杭州未来${weatherEvidenceRows.value.length}天结果已读取，其中${weatherUsableRows.value.length}天可用于分析${weatherUpdatedAt.value ? `，读取时间 ${weatherUpdatedAt.value}` : ''}`
})
const recentOrderSummary = computed<AnyRecord>(() => (orders.value.recent || {}) as AnyRecord)
const primarySpec = computed<AnyRecord | null>(() => (advisor.value?.primary as AnyRecord) || null)
const judgement = computed<AnyRecord>(() => (advisor.value?.judgement as AnyRecord) || {})
const primaryExperience = computed<AnyRecord | null>(() => ((primarySpec.value?.experiences as AnyRecord[]) || [])[0] || null)
// 顶部只显示主推与备选；完整的当前选择只在下方展开，避免同一结论重复出现。
const rawPlans = computed<AnyRecord[]>(() => ((judgement.value.plans as AnyRecord[]) || []).slice(0, 4))
function planKey(item: AnyRecord) {
  return [item.target_date, item.room_type, item.resource_name].map((value) => String(value || '')).join('|')
}
function planExperienceNames(item: AnyRecord) {
  const explicit = (item.experience_names || item.experiences || []) as AnyRecord[]
  if (explicit.length) return explicit.map((value) => typeof value === 'string' ? value : String(value.name || '')).filter(Boolean)
  const name = String(item.name || '')
  const joined = name.includes('×') ? name.slice(name.indexOf('×') + 1) : ''
  const names = joined.split(/[、,+]/).map((value) => value.trim()).filter(Boolean)
  if (names.length) return [...new Set(names)]
  return item.resource_name ? [String(item.resource_name)] : []
}
function planTitle(item: AnyRecord) {
  const room = String(item.room_type || String(item.name || '').split('×')[0] || '').trim()
  const experiences = planExperienceNames(item)
  return [room, ...experiences].filter(Boolean).join(' × ') || String(item.name || item.product_name || '经营建议方案')
}
const selectedPlanKey = computed(() => {
  const primary = primarySpec.value
  return primary ? planKey({ target_date: primary.target_date, room_type: primary.room_type, resource_name: primary.experiences?.[0]?.name }) : ''
})
const currentPrimaryPlan = computed<AnyRecord | null>(() => {
  const primary = primarySpec.value
  if (!primary) return null
  return {
    ...primary,
    name: planTitle({ room_type: primary.room_type, experience_names: primary.experiences || [] }),
    experience_names: ((primary.experiences || []) as AnyRecord[]).map((item) => String(item.name || '')).filter(Boolean),
    resource_name: String(primary.experiences?.[0]?.name || ''),
    estimated_price: primary.price || primary.suggested_price,
    remaining: primary.room_quantity ?? focusRoom.value?.remaining ?? 0,
    is_current: true,
    is_ai_primary: true,
  }
})
const adviceAlternatives = computed(() => rawPlans.value.filter((item) => !selectedPlanKey.value || planKey(item) !== selectedPlanKey.value))
const advicePlan = computed<AnyRecord | null>(() => {
  if (adviceVariant.value > 0 && adviceAlternatives.value.length) return adviceAlternatives.value[(adviceVariant.value - 1) % adviceAlternatives.value.length]
  return currentPrimaryPlan.value || rawPlans.value.find((item) => item.is_ai_primary || item.label === 'AI主推') || rawPlans.value[0] || null
})
function concisePlanReason(item: AnyRecord) {
  const targetDate = String(item.target_date || primarySpec.value?.target_date || '')
  const roomName = displayValue(item.room_type || primarySpec.value?.room_type, '可售房型')
  const experienceNames = planExperienceNames(item)
  const room = roomEvidenceRows.value.find((row) => String(row.available_date || '') === targetDate && displayValue(row.room_type) === roomName)
  const resources = resourceEvidenceRows.value.filter((row) => String(row.available_date || '') === targetDate && experienceNames.includes(String(row.name || '')))
  const weather = weatherEvidenceRows.value.find((row) => String(row.target_date || '') === targetDate && row.usable)
  const crowd = recentCrowdRanks.value[0]
  const parts: string[] = []
  if (room) parts.push(displayDate(targetDate) + '的' + roomName + '还可售' + Number(room.available_count || 0) + '间')
  if (crowd) parts.push('近15天' + crowdLabel(crowd.target_crowd) + '有' + Number(crowd.confirmed_orders || 0) + '笔确认订单，这个方向有近期客群作参考')
  const experienceDescriptions = experienceNames.map((name) => {
    const resource = resources.find((row) => String(row.name || '') === name)
    if (!resource) return name
    const detail = resource.indoor ? '室内体验，天气变化时更稳妥' : '户外体验，适合结合当天预报安排'
    const capacity = Number(resource.remaining_capacity || 0)
    const time = resource.start_time && resource.end_time ? '，场次为' + String(resource.start_time).slice(0, 5) + '–' + String(resource.end_time).slice(0, 5) : ''
    return name + time + (capacity ? '，当日余' + capacity + '份名额' : '') + '，' + detail
  })
  if (experienceDescriptions.length) parts.push('住宿之外安排' + experienceDescriptions.join('；'))
  if (weather?.scenario === 'RAIN') parts.push('当日有雨，户外项目建议缩短停留，室内体验可稳定保留')
  else if (weather?.scenario === 'SUNNY' && resources.some((row) => !row.indoor)) parts.push('当日预报晴好，户外体验可以放在主要游览时段')
  const knowledgeDetails = experienceNames.map((name) => {
    const row = knowledgeRows.value.find((item) => {
      const placeName = String(item.name || '')
      return placeName && (placeName.includes(name) || name.includes(placeName))
    })
    return String(row?.description || row?.summary || row?.introduction || '').trim()
  }).filter(Boolean)
  if (knowledgeDetails.length) parts.push('地点知识补充了体验背景：' + knowledgeDetails[0].slice(0, 70) + (knowledgeDetails[0].length > 70 ? '…' : ''))
  const planPrice = Number(item.estimated_price || 0)
  const currentPrice = Number(primarySpec.value?.price || primarySpec.value?.suggested_price || 0)
  if (planPrice && currentPrice && planPrice !== currentPrice) {
    parts.push(planPrice < currentPrice ? '相比当前选择，预计价格低约¥' + Math.round(currentPrice - planPrice) : '相比当前选择，预计价格高约¥' + Math.round(planPrice - currentPrice))
  }
  if (parts.length) return parts.join('。') + '。'
  const fallback = String(item.fit_reason || '').replace(/^(?:推荐理由|适配点|主推理由|备选特点)\s*(?:[：:]\s*|\s+)/, '').trim()
  return fallback || planReason(item)
}
const plans = computed<AnyRecord[]>(() => {
  const priorityKey = advicePlan.value ? planKey(advicePlan.value) : selectedPlanKey.value
  const hasPriorityInRawPlans = rawPlans.value.some((item) => planKey(item) === priorityKey)
  const list = rawPlans.value.map((item) => ({
    ...item,
    is_current: selectedPlanKey.value ? planKey(item) === selectedPlanKey.value : Boolean(item.is_current),
    is_ai_primary: Boolean(priorityKey) && hasPriorityInRawPlans
      ? planKey(item) === priorityKey
      : Boolean(priorityKey) && advicePlan.value ? false : Boolean(item.is_ai_primary) || item.label === 'AI主推',
  }))
  if (currentPrimaryPlan.value && !list.some((item) => planKey(item) === selectedPlanKey.value)) {
    list.push({ ...currentPrimaryPlan.value, is_current: true, is_ai_primary: planKey(currentPrimaryPlan.value) === priorityKey })
  }
  if (advicePlan.value && !list.some((item) => planKey(item) === priorityKey)) {
    list.push({ ...advicePlan.value, is_current: planKey(advicePlan.value) === selectedPlanKey.value, is_ai_primary: true })
  }
  return list.sort((a, b) => Number(Boolean(b.is_ai_primary)) - Number(Boolean(a.is_ai_primary)))
})
const inventoryRoomOptions = computed<AnyRecord[]>(() => inventoryRooms.value
  .filter((room) => room.status === 'AVAILABLE' && Number(room.available_count || 0) > 0 && Number(room.max_guests || 0) > 0)
  .sort((a, b) => String(a.available_date).localeCompare(String(b.available_date)) || String(a.room_type).localeCompare(String(b.room_type))))
const generationRoomOptions = computed(() => {
  const grouped = new Map<string, AnyRecord>()
  for (const room of inventoryRoomOptions.value.filter((item) => Number(item.max_guests || 0) >= Number(primarySpec.value?.party_size || 1))) {
    const key = `${room.available_date}|${room.room_type}`
    const previous = grouped.get(key)
    if (!previous || Number(room.available_count || 0) > Number(previous.available_count || 0)) grouped.set(key, room)
  }
  return [...grouped.values()]
})
const generationDates = computed(() => [...new Set(generationRoomOptions.value.map((room) => String(room.available_date)))])
const selectedGenerationRoom = computed(() => generationRoomOptions.value.find((room) => `${room.available_date}|${room.room_type}` === targetInventoryKey.value) || generationRoomOptions.value[0] || null)
const generationRoomsForDate = computed(() => {
  const selectedDate = String(selectedGenerationRoom.value?.available_date || '')
  return generationRoomOptions.value.filter((room) => String(room.available_date) === selectedDate)
})
const generationDate = computed({
  get: () => String(selectedGenerationRoom.value?.available_date || ''),
  set: (value: string) => {
    const currentType = String(selectedGenerationRoom.value?.room_type || '')
    const target = generationRoomOptions.value.find((room) => String(room.available_date) === value && String(room.room_type) === currentType)
      || generationRoomOptions.value.find((room) => String(room.available_date) === value)
    if (target) targetInventoryKey.value = `${target.available_date}|${target.room_type}`
  },
})
const generationRoomType = computed({
  get: () => String(selectedGenerationRoom.value?.room_type || ''),
  set: (value: string) => {
    const selectedDate = String(selectedGenerationRoom.value?.available_date || '')
    const target = generationRoomOptions.value.find((room) => String(room.available_date) === selectedDate && String(room.room_type) === value)
    if (target) targetInventoryKey.value = `${target.available_date}|${target.room_type}`
  },
})
const batchRoomOptions = computed(() => inventoryRoomOptions.value.filter((room) => Number(room.max_guests || 0) >= Number(primarySpec.value?.party_size || 1)))
function routeForDay(dayIndex: number) {
  return ((primarySpec.value?.route_plan || []) as AnyRecord[]).find((item) => Number(item.day_index) === Number(dayIndex)) || null
}
function routeLegForStop(dayIndex: number, stopName: unknown) {
  const name = String(stopName || '').trim()
  if (!name) return null
  const legs = (routeForDay(dayIndex)?.legs || []) as AnyRecord[]
  return legs.find((leg) => String(leg.to_stop || '').trim() === name)
    || legs.find((leg) => name.length > 3 && String(leg.to_stop || '').includes(name))
    || null
}
function routeReturnLeg(dayIndex: number, itemIndex: number, total: number) {
  if (itemIndex !== total - 1) return null
  const legs = (routeForDay(dayIndex)?.legs || []) as AnyRecord[]
  return legs.find((leg) => /酒店|返程/.test(String(leg.to_stop || ''))) || null
}
function resourceDurationText(item: AnyRecord) {
  const minutes = Number(item.duration_minutes || item.duration || 0)
  if (minutes > 0) return minutes >= 60 ? '约' + Math.floor(minutes / 60) + '小时' + (minutes % 60 ? minutes % 60 + '分钟' : '') : '约' + minutes + '分钟'
  const range = String(item.window || '').match(/(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})/)
  if (!range) return ''
  const diff = (Number(range[3]) * 60 + Number(range[4])) - (Number(range[1]) * 60 + Number(range[2]))
  return diff > 0 ? '约' + Math.floor(diff / 60) + '小时' + (diff % 60 ? diff % 60 + '分钟' : '') : ''
}
function parseScheduleRange(value: unknown) {
  const match = String(value || '').match(/(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})/)
  if (!match) return null
  return { start: Number(match[1]) * 60 + Number(match[2]), end: Number(match[3]) * 60 + Number(match[4]) }
}
function resourceScheduleAdvice(item: AnyRecord) {
  const duration = resourceDurationText(item)
  const targetDate = String(item.available_date || item.target_date || primarySpec.value?.target_date || '')
  const days = ((primarySpec.value?.itinerary_days || []) as AnyRecord[]).filter((day) => !targetDate || !day.date || String(day.date).slice(0, 10) === targetDate)
  const freeSlot = days.flatMap((day) =>
    ((day.items || []) as AnyRecord[])
      .filter((row) => /自由|空闲|午餐与自由/.test(String(row.title || '')))
      .map((row) => String(day.label || ('第' + day.day_index + '天')) + ' ' + String(row.time || '') + ' ' + String(row.title || '')),
  )[0]
  const optionRange = parseScheduleRange(item.window || `${item.start_time || ''}–${item.end_time || ''}`)
  const conflicts = optionRange ? days.flatMap((day) => ((day.items || []) as AnyRecord[])
    .filter((row) => !/自由|空闲|午餐/.test(String(row.title || '')))
    .filter((row) => {
      const range = parseScheduleRange(row.time)
      return Boolean(range && optionRange.start < range.end && range.start < optionRange.end)
    })
    .map((row) => String(row.title || '已安排事项'))) : []
  const conflict = conflicts.length > 0 || /冲突|不建议/.test(String(item.fit_label || ''))
  if (conflict) {
    const conflictText = [...new Set(conflicts)].join('、') || '现有行程'
    return `候选场次${item.window || '与当前时段'}和${conflictText}存在时间冲突${duration ? `；体验约${duration}` : ''}。优先调整到${freeSlot || '当天未安排体验的自由活动时段'}，并预留交通时间；最终以生成后的行程校验为准。`
  }
  if (item.window) return `候选场次为${item.window}${duration ? `，体验${duration}` : ''}；当前行程没有登记重叠节点${freeSlot ? `，可优先参考${freeSlot}` : '，可按自由活动时段规划'}，建议另留出往返交通时间。`
  if (freeSlot) return `当前没有固定场次，体验${duration || '时长待确认'}；建议优先放入${freeSlot}，并避开已确定的体验与转场。`
  return `当前没有登记固定场次${duration ? `，体验${duration}` : '，时长待确认'}；行程暂无明确空档时先按自由活动处理，再依据资源方场次和交通时间复核安排。`
}
const itineraryOptionalPlaces = computed<AnyRecord[]>(() => ((primarySpec.value?.itinerary_days || []) as AnyRecord[])
  .flatMap((day) => ((day.items || []) as AnyRecord[])
    .filter((item) => item.route_only)
    .map((item) => ({ ...item, day_label: day.label || ('第' + day.day_index + '天') })))
  .slice(0, 4))

const stages = [
  { id: 1, label: '经营分析' },
  { id: 2, label: '产品方案' },
  { id: 3, label: '预览与发布' },
]
const availableStage = computed(() => {
  // 生成候选后直接进入「预览与发布」：不再单独占用一个确认步骤。
  if (sessionProposalIds.value.length > 0 || resolvedCandidateCount.value > 0) return 3
  // 经营分析只要读取结束就算完成；即使没有推荐方案，用户也能进入产品方案继续调整条件。
  return analysisDone.value ? 2 : 1
})
const stageIndex = computed(() => Math.min(selectedStage.value || 1, availableStage.value))
async function selectStage(id: number) {
  if (id > availableStage.value) return
  selectedStage.value = id
  if (id === 2) {
    // 进入产品方案前补齐经营证据，使候选方案使用当前房态、订单和资源数据。
    await Promise.allSettled([
      ensureEvidence('inventory'),
      ensureEvidence('orders'),
      ensureEvidence('resources'),
      ensureEvidence('weather'),
      ensureEvidence('knowledge'),
    ])
    if (!submitting.value && (!advisorLoadedThisVisit.value || advisorAnalysisSignature.value !== analysisSignature())) await autoStart()
  } else if (id === 3) {
    void loadRefinementHistory(primarySpec.value?.product_id as number | undefined)
  }
}

async function loadConversationHistory() {
  try {
    const tasks = await hotelApi.aiConversations(1)
    conversations.value = Array.isArray(tasks.data) ? tasks.data : []
    const latest = conversations.value[0] as AnyRecord | undefined
    if (!latest) return
    if (!activeConversationId.value) {
      activeConversationId.value = Number(latest.id)
      const key = operationStorageKey(activeConversationId.value)
      if (key) { try { operationLog.value = JSON.parse(localStorage.getItem(key) || '[]') } catch { operationLog.value = [] } }
      const stored = (latest.last_execution as AnyRecord | undefined)?.answer
      const storedPrimary = (stored as AnyRecord | undefined)?.primary as AnyRecord | undefined
      const storedJudgement = (stored as AnyRecord | undefined)?.judgement as AnyRecord | undefined
      const contractOk = storedJudgement?.contract_version === ADVISOR_CONTRACT_VERSION
        && Boolean(storedPrimary?.resource_options)
        && Boolean((storedJudgement?.plans as unknown[] | undefined)?.length)
      if (stored && typeof stored === 'object' && contractOk) advisor.value = stored as AnyRecord
      const restoredPrimary = (advisor.value?.primary as AnyRecord) || null
      if (restoredPrimary) {
        const normalized = normalizePrimaryParty(restoredPrimary)
        advisor.value = { ...(advisor.value || {}), primary: normalized }
        previousPrimary.value = normalized
        targetInventoryKey.value = String(normalized.target_date) + '|' + String(normalized.room_type)
      }
      // 只要本轮会话还有待确认候选，就恢复到「预览与发布」阶段：
      // 刷新页面不会让已经生成并校验过的候选消失。
      const response = await hotelApi.aiProposals('PENDING_CONFIRMATION', Number(latest.id))
      proposals.value = Array.isArray(response.data) ? response.data : []
      sessionProposalIds.value = proposals.value
        .filter((item) => Number(item.conversation_id) === Number(latest.id))
        .map((item) => Number(item.id))
      // 候选只在后台恢复，页面仍从「经营分析」开始：用户一步步走，不直接跳到预览发布。
    }
  } catch (error) {
    // Historical context is optional for viewing current operating data.
    console.warn('经营分析历史会话读取失败', error)
  }
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const facts = await hotelApi.aiOverview({ section: 'summary' })
    overview.value = { ...overview.value, ...facts.data }
    dataReady.value = true
    const now = new Date()
    loadedAt.value = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0')
    void loadConversationHistory()
  } catch (error) {
    loadError.value = errorMessage(error)
    showToast(loadError.value)
  } finally {
    loading.value = false
    analysisDone.value = true
  }
}

async function ensureEvidence(section: Exclude<typeof panel.value, ''>, force = false) {
  if (!force && evidenceLoaded.value.includes(section)) return
  const pending = evidenceRequests.get(section)
  if (pending) return pending
  const request = (async () => {
    evidenceLoadingSections.value = [...new Set([...evidenceLoadingSections.value, section])]
    if (panel.value === section) evidenceLoading.value = section
    evidenceErrors.value = { ...evidenceErrors.value, [section]: '' }
    evidenceError.value = ''
    if (section === 'weather') {
      weatherFetchState.value = 'loading'
      weatherUpdatedAt.value = ''
      overview.value = { ...overview.value, weather: undefined, weather_forecasts: [] }
    }
    try {
      if (section === 'inventory') {
        const rooms = await hotelApi.rooms({ from_date: localDateKey(new Date()), days: 17 })
        inventoryRooms.value = (rooms.data as AnyRecord[]).map((room) => ({
          ...room,
          room_type: displayValue(room.room_type, '未命名房型'),
        }))
      } else if (section === 'resources') {
        const response = await hotelApi.aiOverview({ section: 'resources' })
        overview.value = { ...overview.value, ...response.data }
      } else if (section === 'orders') {
        orders.value = (await hotelApi.ordersOverview()).data
      } else if (section === 'weather') {
        const response = await hotelApi.aiOverview({ section: 'weather' })
        overview.value = { ...overview.value, ...response.data }
        weatherFetchState.value = 'ready'
        const fetchedAt = (response.data.weather_forecasts as AnyRecord[] | undefined)?.find((row) => row.fetched_at)?.fetched_at
          || (response.data.weather as AnyRecord | undefined)?.fetched_at
        if (fetchedAt) {
          const stamp = new Date(String(fetchedAt))
          weatherUpdatedAt.value = Number.isNaN(stamp.getTime()) ? '' : `${String(stamp.getHours()).padStart(2, '0')}:${String(stamp.getMinutes()).padStart(2, '0')}`
        } else weatherUpdatedAt.value = nowLabel()
      } else if (section === 'knowledge') {
        const response = await hotelApi.knowledge({ limit: 5000 })
        overview.value = { ...overview.value, knowledge: response.data.items, knowledge_total: response.data.total }
      }
      evidenceLoaded.value = [...new Set([...evidenceLoaded.value, section])]
    } catch (error) {
      const message = errorMessage(error)
      evidenceError.value = message
      evidenceErrors.value = { ...evidenceErrors.value, [section]: message }
      if (section === 'weather') weatherFetchState.value = 'error'
    } finally {
      evidenceLoadingSections.value = evidenceLoadingSections.value.filter((item) => item !== section)
      if (evidenceLoading.value === section) evidenceLoading.value = ''
      evidenceRequests.delete(section)
    }
  })()
  evidenceRequests.set(section, request)
  return request
}

function retryEvidence() {
  if (panel.value) void ensureEvidence(panel.value, true)
}
async function refreshData() {
  processingMessage.value = '正在刷新经营摘要…'
  submitting.value = true
  try {
    await load()
    if (panel.value) await ensureEvidence(panel.value, true)
    if (stageIndex.value >= 2) {
      await ensureEvidence('inventory', true)
      await autoStart()
    }
  } finally { submitting.value = false }
}
async function reanalyzeOperations() {
  submitting.value = true
  processingMessage.value = '正在重新读取房态、订单、合作资源、天气与知识库…'
  try {
    await load()
    await Promise.allSettled(evidenceSections.map((section) => ensureEvidence(section, true)))
    if (adviceAlternatives.value.length) {
      adviceVariant.value = adviceVariant.value % adviceAlternatives.value.length + 1
      showToast(`已切换经营建议：${operatingAdvice.value.title}`)
    } else {
      adviceVariant.value = 0
      showToast('当前只有一个完整可售方向，建议仍与产品方案主推保持一致')
    }
  } finally { submitting.value = false }
}
function localDateKey(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}
function resetEvidencePage(key: string) {
  evidencePages.value = { ...evidencePages.value, [key]: 1 }
  if (key === 'resources') evidencePages.value = { ...evidencePages.value, resources: 1, services: 1 }
}
function filterEvidenceDate(rows: AnyRecord[], filterKey: string, dateOf: (row: AnyRecord) => unknown) {
  const filter = String(evidenceDateFilters.value[filterKey] || '')
  return filter ? rows.filter((row) => String(dateOf(row) || '').slice(0, 10) === filter) : rows
}
function evidencePageRows(rows: AnyRecord[], key: string) {
  const totalPages = Math.max(1, Math.ceil(rows.length / evidencePageSize))
  const page = Math.min(Math.max(1, Number(evidencePages.value[key] || 1)), totalPages)
  const start = (page - 1) * evidencePageSize
  return rows.slice(start, start + evidencePageSize)
}
function evidencePageCount(rows: AnyRecord[]) {
  return Math.max(1, Math.ceil(rows.length / evidencePageSize))
}
function changeEvidencePage(rows: AnyRecord[], key: string, step: number) {
  const lastPage = evidencePageCount(rows)
  const current = Number(evidencePages.value[key] || 1)
  evidencePages.value = { ...evidencePages.value, [key]: Math.min(lastPage, Math.max(1, current + step)) }
}
function clearEvidenceDate(key: string) {
  evidenceDateFilters.value = { ...evidenceDateFilters.value, [key]: '' }
  resetEvidencePage(key)
}
function displayValue(value: unknown, fallback = '') {
  if (value === null || value === undefined || value === '') return fallback
  if (typeof value === 'object') {
    const item = value as AnyRecord
    const candidate = item.name ?? item.label ?? item.value ?? item.display_name ?? item.room_type
    return ['string', 'number', 'boolean'].includes(typeof candidate) ? String(candidate) : fallback
  }
  return String(value)
}
function displayDate(value: unknown) {
  const key = displayValue(value && typeof value === 'object' ? ((value as AnyRecord).date ?? (value as AnyRecord).available_date ?? (value as AnyRecord).target_date) : value).slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(key)) return key || '日期未登记'
  const day = new Date(`${key}T00:00:00`)
  return `${key}（周${'日一二三四五六'[day.getDay()]}）`
}
const filteredRoomRows = computed(() => filterEvidenceDate(roomEvidenceRows.value, 'inventory', (row) => row.available_date))
const filteredResourceRows = computed(() => filterEvidenceDate(resourceEvidenceRows.value, 'resources', (row) => row.available_date))
const filteredServiceRows = computed(() => filterEvidenceDate(serviceEvidenceRows.value, 'resources', (row) => row.available_date))
const allOrderRows = computed<AnyRecord[]>(() => (Array.isArray(orders.value.orders) ? orders.value.orders as AnyRecord[] : []))
const filteredOrderRows = computed(() => filterEvidenceDate(allOrderRows.value, 'orders', (row) => row.confirmed_at || row.created_at))
const filteredWeatherRows = computed(() => filterEvidenceDate(weatherEvidenceRows.value, 'weather', (row) => row.target_date))
const filteredKnowledgeRows = computed(() => filterEvidenceDate((overview.value.knowledge || []) as AnyRecord[], 'knowledge', (row) => row.verified_at || row.source_updated_at))
const recentOrderRows = computed<AnyRecord[]>(() => (Array.isArray(recentOrderSummary.value.orders) ? recentOrderSummary.value.orders as AnyRecord[] : []))
const recentConfirmedRows = computed<AnyRecord[]>(() => recentOrderRows.value.filter((row) => row.status === '已成交' || row.status === 'CONFIRMED'))
const recentConfirmedRevenue = computed(() => String(recentOrderSummary.value.confirmed_revenue ?? recentConfirmedRows.value.reduce((total, row) => total + Number(row.amount || 0), 0).toFixed(2)))
function batchCreatedText(result: AnyRecord) {
  return ((result.created || []) as AnyRecord[]).map((item) => `${item.target_date} ${item.room_type}`).join('、')
}
const historyMessages = computed<AnyRecord[]>(() => {
  const messages = activeConversation.value?.messages
  return Array.isArray(messages) ? messages : []
})
const analysisMessages = computed<AnyRecord[]>(() => historyMessages.value.filter((item) => item.kind === 'OPERATIONS_QUERY'))
const operatingQuestions = ['最近什么产品卖得最好？', '未来哪些房型可售余量最多？', '哪些合作体验已有成交关联？']
function analysisSignature() {
  return analysisMessages.value.map((item) => `${item.role}:${item.created_at}:${item.content}`).join('|')
}

async function applySalesCommand(text: string) {
  const response = await hotelApi.salesCommand(text)
  if (evidenceLoaded.value.includes('orders')) await ensureEvidence('orders', true)
  showToast(response.data.message)
}

async function ensureConversation() {
  if (activeConversationId.value) return activeConversationId.value
  const response = await hotelApi.createAiConversation()
  const item = response.data
  conversations.value.unshift(item)
  activeConversationId.value = Number(item.id)
  return activeConversationId.value
}

function mergeConversation(conversation: AnyRecord) {
  const index = conversations.value.findIndex((item) => Number(item.id) === Number(conversation.id))
  if (index >= 0) conversations.value.splice(index, 1, conversation)
  else conversations.value.unshift(conversation)
}

function primaryDiffs(previous: AnyRecord | null, next: AnyRecord | null) {
  if (!next || !previous) return [] as AnyRecord[]
  const diffs: AnyRecord[] = []
  const add = (label: string, before: unknown, after: unknown) => {
    if (String(before ?? '') !== String(after ?? '') && String(after ?? '') !== '') diffs.push({ label, before, after })
  }
  add('体验', previous.experiences?.map((item: AnyRecord) => item.name).join('、'), next.experiences?.map((item: AnyRecord) => item.name).join('、'))
  add('酒店权益', previous.services?.map((item: AnyRecord) => item.name).join('、') || '无', next.services?.map((item: AnyRecord) => item.name).join('、') || '无')
  add('建议售价', previous.price ? `¥${previous.price}` : '', next.price ? `¥${next.price}` : '')
  add('客群', previous.crowd_label, next.crowd_label)
  add('同行人数', previous.party_size ? `${previous.party_size}人` : '', next.party_size ? `${next.party_size}人` : '')
  add('房型', previous.room_type, next.room_type)
  add('可售', previous.max_sellable !== undefined ? `${previous.max_sellable}套` : '', next.max_sellable !== undefined ? `${next.max_sellable}套` : '')
  add('单位成本', previous.cost ? `¥${previous.cost}` : '', next.cost ? `¥${next.cost}` : '')
  add('毛利率', previous.margin !== undefined ? `${previous.margin}%` : '', next.margin !== undefined ? `${next.margin}%` : '')
  add('路线调整', String(previous.route_note || '默认路线'), String(next.route_note || '默认路线'))
  const routeSummary = (value: AnyRecord) => ((value.itinerary_days || []) as AnyRecord[])
    .map((day) => String(day.label || '') + '：' + ((day.items || []) as AnyRecord[]).map((item) => String(item.title || '')).join('、'))
    .join('；')
  add('行程顺序', routeSummary(previous), routeSummary(next))
  return diffs
}

function describeChange(previous: AnyRecord | null, next: AnyRecord | null) {
  const diffs = primaryDiffs(previous, next)
  if (!next) return ''
  const notice = next.selection_notice ? ` ${next.selection_notice}` : ''
  if (!diffs.length) return `当前已保留现有资源下的组合（${next.product_name}，¥${next.price}）。${notice}`
  return `已根据你的要求调整：${diffs.map((item) => `${item.label} ${item.before} → ${item.after}`).join('；')}。${notice}`
}

function flashCard() {
  cardFlash.value = true
  window.setTimeout(() => { cardFlash.value = false }, 2000)
}

function operationStorageKey(id: number | null) { return id ? 'stayscape_operation_log_' + id : '' }

function nowLabel() {
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

function operationTitle(instruction: string) {
  if (/增加|加上|搭配/.test(instruction)) return '增加资源'
  if (/换资源|换成|替换/.test(instruction)) return '更换体验'
  if (/价格|售价|预算|压价/.test(instruction)) return '调整价格'
  if (/客群|情侣|亲子|朋友|独自/.test(instruction)) return '切换客群'
  if (/路线|行程|自由时间/.test(instruction)) return '调整路线'
  return '调整方案'
}

function logOperation(instruction: string, change: string, changes: AnyRecord[] = [], next: AnyRecord | null = null) {
  if (!instruction) return
  operationLog.value = [{ at: nowLabel(), stamp: Date.now(), title: operationTitle(instruction), instruction, change, changes, result: next ? { name: next.product_name, price: next.price, quantity: next.max_sellable } : null }, ...operationLog.value].slice(0, 40)
  const key = operationStorageKey(activeConversationId.value)
  if (key) localStorage.setItem(key, JSON.stringify(operationLog.value))
}

// 每轮回答都会替换当前主方案，这就是「对话直接编辑产品」的核心。
function applyAdvisor(nextAdvisor: AnyRecord, instruction: string) {
  let nextPrimary = (nextAdvisor.primary as AnyRecord) || null
  let effectiveAdvisor = nextAdvisor
  let changes: AnyRecord[] = []
  if (!nextPrimary && previousPrimary.value) {
    const nextJudgement = (nextAdvisor.judgement as AnyRecord) || {}
    const oldJudgement = (advisor.value?.judgement as AnyRecord) || {}
    const hasNewDirections = Array.isArray(nextJudgement.plans) && nextJudgement.plans.length > 0
    nextPrimary = previousPrimary.value
    effectiveAdvisor = {
      ...(advisor.value || {}),
      ...nextAdvisor,
      primary: nextPrimary,
      judgement: hasNewDirections ? nextJudgement : oldJudgement,
    }
    changeNote.value = validationChangeNote(
      nextAdvisor.validation_error,
      `${String(nextJudgement.text || '本轮没有找到满足新条件的组合')}；已保留上一版方案，你可以调整条件或重试。`,
    )
    changeDetails.value = []
  } else {
    changes = primaryDiffs(previousPrimary.value, nextPrimary)
    changeDetails.value = changes
    changeNote.value = describeChange(previousPrimary.value, nextPrimary)
    if (nextPrimary) {
      previousPrimary.value = nextPrimary
      targetInventoryKey.value = `${nextPrimary.target_date}|${nextPrimary.room_type}`
    }
  }
  advisor.value = effectiveAdvisor
  adviceVariant.value = 0
  activeAdjust.value = ''
  flashCard()
  logOperation(instruction, changeNote.value, changes, nextPrimary)
}

function applyRefinedProduct(refinedProduct: AnyRecord | undefined, instruction: string) {
  if (!refinedProduct) return
  const current = primarySpec.value || {}
  const nextPrimary: AnyRecord = {
    ...primaryFromRefinedProduct(refinedProduct, current),
    crowd_label: crowdLabel(refinedProduct.target_crowd || current.crowd),
  }
  const changes = primaryDiffs(previousPrimary.value, nextPrimary)
  changeDetails.value = changes
  changeNote.value = describeChange(previousPrimary.value, nextPrimary)
  previousPrimary.value = nextPrimary
  advisor.value = { ...(advisor.value || {}), primary: nextPrimary }
  proposals.value = proposals.value.map((proposal) => Number(proposal.product_id) === Number(refinedProduct.id)
    ? { ...proposal, product: { ...(proposal.product as AnyRecord), ...refinedProduct } }
    : proposal)
  activeAdjust.value = ''
  flashCard()
  logOperation(instruction, changeNote.value, changes, nextPrimary)
}

async function submit() {
  const text = brief.value.trim()
  if (!text) { showToast(stageIndex.value === 1 ? '请输入想了解的经营问题' : '请用一句话说明想怎么调整方案'); return }
  submitting.value = true
  processingMessage.value = stageIndex.value === 1 ? '正在查询房态、成交、资源、天气或地点数据…' : '正在根据你的要求重新计算产品组成、价格、容量与行程…'
  try {
    if (stageIndex.value === 1) {
      const conversationId = await ensureConversation()
      const response = await hotelApi.analyzeOperationsQuestion(Number(conversationId), text)
      mergeConversation(response.data.conversation as AnyRecord)
      brief.value = ''
      return
    }
    const cardAction = ['resources', 'price', 'crowd', 'route', 'service'].includes(activeAdjust.value)
    const refineId = Number(editingProduct.value?.id || (cardAction ? primarySpec.value?.product_id : 0))
    // 销售状态指令（暂停/下架/开售）必须优先于商品微调，
    // 否则「下架这个产品」会被当成文案微调，把营销文案重写掉。
    if (/(暂停|停售|下架|恢复|上架|开售|开启销售)/.test(text)) {
      await applySalesCommand(text)
      brief.value = ''
      return
    }
    if (refineId) {
      const response = await hotelApi.refineProduct(refineId, text)
      refinements.value.unshift({ instruction: text, ...response.data })
      applyRefinedProduct(response.data.product as AnyRecord | undefined, text)
      void loadRefinementHistory(refineId)
      brief.value = ''
      return
    }
    const conversationId = await ensureConversation()
    const response = await hotelApi.advisor(Number(conversationId), text)
    const data = response.data
    mergeConversation(data.conversation as AnyRecord)
    const created = (data.proposals as AnyRecord[]) || []
    if (created.length) {
      sessionProposalIds.value = [...sessionProposalIds.value, ...created.map((item) => Number(item.id))]
      proposals.value = [...created, ...proposals.value]
    }
    applyAdvisor(data.advisor as AnyRecord, text)
    selectedStage.value = (data.advisor as AnyRecord)?.step === 'GENERATED' ? 3 : 2
    brief.value = ''
  } catch (error) { showToast(errorMessage(error)) }
  finally { submitting.value = false }
}

function askOption(option: AnyRecord) {
  brief.value = String(option.message || option.label || '')
  void submit()
}

// 选中一张卡片 → 之后的对话都在改这一个商品。
function startEditing(card: AnyRecord) {
  if (!card.product_id) return
  editingProduct.value = { id: card.product_id, name: card.name }
  brief.value = ''
  showToast(`已进入微调：${card.name}，直接说要改什么`)
}

function stopEditing() {
  editingProduct.value = null
}

// 预览按需展开（默认不加载 iframe），避免一屏同时加载多个预览。
const previewCardKey = ref('')
function toggleCandidatePreview(card: AnyRecord) {
  previewCardKey.value = previewCardKey.value === String(card.key) ? '' : String(card.key)
}

// 「继续调整此候选」回到产品方案阶段，并把这个候选设为正在微调的对象。
async function continueEditing(card: AnyRecord) {
  if (card?.product_id) editingProduct.value = { id: Number(card.product_id), name: String(card.name || '') }
  const target = card?.raw?.product as AnyRecord | undefined
  if (target) {
    const nextPrimary = primaryFromRefinedProduct(target, primarySpec.value || {})
    advisor.value = { ...(advisor.value || {}), primary: nextPrimary }
    previousPrimary.value = nextPrimary
  }
  selectedStage.value = 2
  await nextTick()
  showToast('已回到产品方案，直接说要改什么即可')
}

// 「生成候选产品」把当前方案变成真正待确认的产品。
async function generateFromPlan(primary: AnyRecord) {
  if (!primary) return
  if (primary.product_id) {
    startEditing({ product_id: primary.product_id, name: primary.product_name })
    return
  }
  const experience = (primary.experiences || [])[0]?.name || ''
  submitting.value = true
  processingMessage.value = '正在核验所选方向的房态、资源名额、成本、价格与游客端行程…'
  try {
    const conversationId = await ensureConversation()
    await hotelApi.advisor(Number(conversationId), `${primary.target_date} ${primary.room_type} + ${experience} 的方案`)
    const response = await hotelApi.advisor(Number(conversationId), '就这个，生成候选')
    const data = response.data
    mergeConversation(data.conversation as AnyRecord)
    const created = ((data.proposals as AnyRecord[]) || [])
    if (created.length) {
      sessionProposalIds.value = [...sessionProposalIds.value, ...created.map((item) => Number(item.id))]
      proposals.value = [...created, ...proposals.value]
    }
    applyAdvisor(data.advisor as AnyRecord, '生成候选产品')
    if (created.length) {
      const product = created[0]?.product as AnyRecord | undefined
      if (product) {
        advisor.value = { ...(advisor.value || {}), primary: primaryFromRefinedProduct(product, primarySpec.value || {}) }
        editingProduct.value = { id: Number(product.id || created[0].product_id), name: String(product.product_name || primary.product_name) }
      }
    }
    selectedStage.value = created.length ? 3 : 2
    const generatedId = Number((created[0]?.product as AnyRecord | undefined)?.id || created[0]?.product_id || 0)
    if (generatedId) void loadRefinementHistory(generatedId)
  } catch (error) { showToast(errorMessage(error)) }
  finally { submitting.value = false }
}

async function changeGenerationInventory() {
  const [targetDate, roomType] = targetInventoryKey.value.split('|')
  if (!targetDate || !roomType) return
  await ask(`改为 ${targetDate} 的 ${roomType}`)
}

async function selectEvidence(section: typeof panel.value) {
  panel.value = section
  await ensureEvidence(section)
}

function askOperatingQuestion(question: string) {
  brief.value = question
  return submit()
}

function openResourceTab(tab: 'experience' | 'hotel') {
  if (activeAdjust.value === 'service' && resourceTab.value === tab) {
    activeAdjust.value = ''
    return
  }
  resourceTab.value = tab
  activeAdjust.value = 'service'
}

async function adoptOperatingAdvice() {
  const advice = operatingAdvice.value
  const directive = String(advice?.prompt || '').trim()
  if (!directive) return
  const targetDate = String(advice.target_date || '')
  const roomType = displayValue(advice.room_type, '')
  const resources = Array.isArray(advice.resource_names) ? advice.resource_names.map((item: unknown) => displayValue(item, '').trim()).filter(Boolean) : []
  if (!targetDate || !roomType) {
    showToast('这条建议缺少明确的入住日期或房型，暂时无法采用。')
    return
  }
  const sameAsCurrent = primarySpec.value
    && String(primarySpec.value.target_date || '') === targetDate
    && displayValue(primarySpec.value.room_type) === roomType
    && resources.every((name: string) => ((primarySpec.value?.experiences || []) as AnyRecord[]).some((item) => String(item.name || '') === name))
  if (sameAsCurrent) {
    targetInventoryKey.value = `${targetDate}|${roomType}`
    selectedStage.value = 2
    showToast('已采用当前主推组合')
    return
  }
  const adoptionBrief = `经营建议：${directive}。请将日期${targetDate}、房型${roomType}${resources.length ? `及体验${resources.join('、')}` : ''}作为产品方案中的主推组合，并补充两个侧重点不同的备选。结合订单客群、当日库存、体验内容、天气和已核验地点知识撰写推荐说明。`
  const adopted = await autoStart(adoptionBrief, { targetDate, roomType, resourceNames: resources })
  if (adopted) targetInventoryKey.value = `${targetDate}|${roomType}`
}

function resizeVisitorPreview(event: Event) {
  const frame = event.target as HTMLIFrameElement | null
  const doc = frame?.contentDocument
  if (!frame || !doc) return
  // 预览框限高：之前会把 iframe 撑到内容真实高度（实测 1.1 万 px），整页被一张预览拖长。
  const resize = () => {
    const contentHeight = Math.max(doc.body?.scrollHeight || 0, doc.documentElement?.scrollHeight || 0, 480)
    const height = Math.min(contentHeight, 720)
    frame.style.height = `${height}px`
  }
  resize()
  window.setTimeout(resize, 250)
  window.setTimeout(resize, 900)
  doc.fonts?.ready.then(resize).catch(() => undefined)
  const observer = new MutationObserver(resize)
  observer.observe(doc.documentElement, { childList: true, subtree: true })
  for (const image of Array.from(doc.images)) {
    if (!image.complete) image.addEventListener('load', resize, { once: true })
  }
}

async function applyBatch(card: AnyRecord) {
  const targets = batchRoomIds.value
    .map((id) => inventoryRoomOptions.value.find((room) => Number(room.id) === Number(id)))
    .filter((room): room is AnyRecord => Boolean(room))
    .map((room) => ({ target_date: room.available_date, room_inventory_id: Number(room.id) }))
  if (!targets.length) { showToast('先选择一个或多个可售日期与房型'); return }
  batchApplying.value = true
  try {
    const response = await hotelApi.batchApplyProduct(card.product_id, targets)
    batchResult.value = response.data
    if (response.data.created_count) showToast(`已生成 ${response.data.created_count} 个草稿产品`)
    else showToast('所选日期暂时无法复制，查看下方原因')
  } catch (error) { showToast(errorMessage(error)) }
  finally { batchApplying.value = false }
}

async function editVisitorCopy(card: AnyRecord) {
  if (Number(copyDraft.value?.id) === Number(card.product_id)) { copyDraft.value = null; return }
  try {
    const response = await hotelApi.product(Number(card.product_id))
    const product = response.data as AnyRecord
    copyDraft.value = {
      id: Number(card.product_id),
      product: { ...product },
      resources: (product.resources || []).map((item: AnyRecord) => ({ ...item })),
      assets: (product.marketing_assets || []).map((item: AnyRecord) => ({ ...item })),
      days: (product.day_plan || []).map((day: AnyRecord) => ({ ...day, items: (day.items || []).map((item: AnyRecord) => ({ ...item })) })),
      details: JSON.parse(JSON.stringify(product.detail_sections || { intro: [], experience_details: [], spend_notes: [], tips: [] })),
    }
  } catch (error) { showToast(errorMessage(error)) }
}

async function rewriteMainCopy(field: string) {
  if (!copyDraft.value) return
  copyRewriting.value = true
  try {
    const current = String(copyDraft.value.product[field] || '')
    const response = await hotelApi.rewriteProductCopy(copyDraft.value.id, { field, current_text: current, context: copyDraft.value.product.product_name })
    copyDraft.value.product[field] = response.data.replacement_text
  } catch (error) { showToast(errorMessage(error)) }
  finally { copyRewriting.value = false }
}

async function rewriteResourceCopy(resource: AnyRecord) {
  if (!copyDraft.value) return
  copyRewriting.value = true
  try {
    const response = await hotelApi.rewriteProductCopy(copyDraft.value.id, { field: 'resource_description', current_text: String(resource.description || resource.resource_name), context: `${copyDraft.value.product.product_name}；体验：${resource.resource_name}；地址：${resource.address || ''}` })
    resource.description = response.data.replacement_text
  } catch (error) { showToast(errorMessage(error)) }
  finally { copyRewriting.value = false }
}

async function rewriteResourceName(resource: AnyRecord) {
  if (!copyDraft.value) return
  copyRewriting.value = true
  try {
    const response = await hotelApi.rewriteProductCopy(copyDraft.value.id, { field: 'resource_title', current_text: String(resource.resource_name || ''), context: `${copyDraft.value.product.product_name}；资源地址：${resource.address || ''}` })
    resource.resource_name = response.data.replacement_text
  } catch (error) { showToast(errorMessage(error)) }
  finally { copyRewriting.value = false }
}

async function rewriteItineraryCopy(item: AnyRecord, field: 'itinerary_title' | 'itinerary_description') {
  if (!copyDraft.value) return
  copyRewriting.value = true
  try {
    const current = String(item[field === 'itinerary_title' ? 'title' : 'description'] || '')
    const response = await hotelApi.rewriteProductCopy(copyDraft.value.id, { field, current_text: current, context: `${copyDraft.value.product.product_name}；${item.time || ''}；${item.address || ''}` })
    item[field === 'itinerary_title' ? 'title' : 'description'] = response.data.replacement_text
  } catch (error) { showToast(errorMessage(error)) }
  finally { copyRewriting.value = false }
}

async function rewriteDayCopy(day: AnyRecord, field: 'itinerary_title' | 'itinerary_summary') {
  if (!copyDraft.value) return
  copyRewriting.value = true
  try {
    const current = String(day[field === 'itinerary_title' ? 'title' : 'summary'] || '')
    const response = await hotelApi.rewriteProductCopy(copyDraft.value.id, { field, current_text: current, context: `${copyDraft.value.product.product_name}；${day.label || ''} ${day.date || ''}` })
    day[field === 'itinerary_title' ? 'title' : 'summary'] = response.data.replacement_text
  } catch (error) { showToast(errorMessage(error)) }
  finally { copyRewriting.value = false }
}

async function rewriteAssetCopy(asset: AnyRecord, field: 'marketing_asset_title' | 'marketing_asset_content') {
  if (!copyDraft.value) return
  copyRewriting.value = true
  try {
    const key = field === 'marketing_asset_title' ? 'title' : 'content'
    const response = await hotelApi.rewriteProductCopy(copyDraft.value.id, { field, current_text: String(asset[key] || ''), context: `${copyDraft.value.product.product_name}；素材类型：${asset.asset_type || ''}` })
    asset[key] = response.data.replacement_text
  } catch (error) { showToast(errorMessage(error)) }
  finally { copyRewriting.value = false }
}

async function rewriteDetailCopy(target: any, field: string, label: string) {
  if (!copyDraft.value) return
  copyRewriting.value = true
  try {
    const response = await hotelApi.rewriteProductCopy(copyDraft.value.id, { field: 'detail_text', current_text: String(target[field] || ''), context: `${copyDraft.value.product.product_name}；详情模块：${label}` })
    target[field] = response.data.replacement_text
  } catch (error) { showToast(errorMessage(error)) }
  finally { copyRewriting.value = false }
}

async function saveVisitorCopy() {
  if (!copyDraft.value) return
  copySaving.value = true
  try {
    const { product, resources, assets, days, details, id } = copyDraft.value
    const visitor_copy = {
      resource_names: Object.fromEntries(resources.map((resource: AnyRecord) => [`${resource.resource_type}:${resource.resource_id}`, resource.resource_name || ''])),
      resource_descriptions: Object.fromEntries(resources.map((resource: AnyRecord) => [`${resource.resource_type}:${resource.resource_id}`, resource.description || ''])),
      itinerary: days.map((day: AnyRecord) => ({
        day_index: day.day_index,
        title: day.title,
        summary: day.summary,
        items: (day.items || []).map((item: AnyRecord) => ({ title: item.title, description: item.description })),
      })),
      detail_sections: {
        intro: details.intro,
        experience_details: (details.experience_details || []).map((item: AnyRecord) => ({ feature: item.feature, tips: item.tips })),
        spend_notes: details.spend_notes,
        tips: details.tips,
      },
    }
    const response = await hotelApi.updateProduct(Number(id), {
      product_name: product.product_name,
      marketing_title: product.marketing_title,
      marketing_content: product.marketing_content,
      recommendation_reason: product.recommendation_reason,
      risk_message: product.risk_message,
      visitor_copy,
      marketing_assets: assets.map((asset: AnyRecord) => ({ asset_type: asset.asset_type, platform: asset.platform, title: asset.title, content: asset.content })),
    })
    proposals.value = proposals.value.map((proposal) => Number(proposal.product_id) === Number(id)
      ? { ...proposal, product: { ...(proposal.product as AnyRecord), ...(response.data as AnyRecord) } }
      : proposal)
    copyDraft.value = null
    showToast('游客端文案已保存')
  } catch (error) { showToast(errorMessage(error)) }
  finally { copySaving.value = false }
}

async function confirm(proposal: AnyRecord, action: 'DRAFT' | 'PUBLISH') {
  try {
    await hotelApi.confirmAiProposal(Number(proposal.id), action)
    proposals.value = proposals.value.filter((item) => Number(item.id) !== Number(proposal.id))
    sessionProposalIds.value = sessionProposalIds.value.filter((id) => id !== Number(proposal.id))
    resolvedCandidateCount.value += 1
    selectedStage.value = 3
    showToast(action === 'PUBLISH' ? '产品已发布并完成库存复核' : '已加入产品草稿，可以继续生成营销素材')
  } catch (error) { showToast(errorMessage(error)) }
}

// 微调历史与回滚：后端每次微调都会生成一条版本记录，这里把它暴露给运营。
const refinementHistory = ref<AnyRecord[]>([])
const historyLoading = ref(false)
async function loadRefinementHistory(productId: number | null | undefined) {
  if (!productId) return
  historyLoading.value = true
  try {
    const response = await hotelApi.productRefinements(Number(productId))
    refinementHistory.value = (response.data.items || []) as AnyRecord[]
  } catch { refinementHistory.value = [] }
  finally { historyLoading.value = false }
}

async function rollbackRefinement(item: AnyRecord) {
  const productId = Number(item.product_id || primarySpec.value?.product_id || 0)
  const refinementId = Number(item.id || 0)
  if (!productId || !refinementId) return
  try {
    const response = await hotelApi.rollbackRefinement(productId, refinementId)
    const product = response.data.product as AnyRecord | undefined
    if (product) applyRefinedProduct(product, `撤销：${item.instruction || '上一次调整'}`)
    await loadRefinementHistory(productId)
    showToast('已撤销这条调整，并记为新版本')
  } catch (error) { showToast(errorMessage(error)) }
}

async function clearConversation() {
  const conversation = activeConversation.value
  if (!conversation) return
  try {
    await hotelApi.clearAiConversation(Number(conversation.id))
    conversation.messages = []
    conversation.last_execution = null
    advisor.value = null
    previousPrimary.value = null
    changeNote.value = ''
    sessionProposalIds.value = []
    resolvedCandidateCount.value = 0
    refinements.value = []
    operationLog.value = []
    const key = operationStorageKey(activeConversationId.value)
    if (key) localStorage.removeItem(key)
    activeAdjust.value = ''
    showToast('已清空本轮方案与操作历史，可以重新描述需求')
  } catch (error) { showToast(errorMessage(error)) }
}

const quickCommands = ['价格降一点', '换成双人', '不要亲子', '换室内项目', '保持价格，提升体验']
// 客群选项：给具体口径，避免「换客群」变成一句含糊指令。
const crowdChoices = [
  { label: '亲子家庭', message: '客群改成亲子家庭，带孩子来住' },
  { label: '两人同行', message: '换成两人同行，情侣或朋友都可以' },
  { label: '朋友同行', message: '改成朋友同行，几个人一起出来玩' },
  { label: '独自出行', message: '改成独自出行，一个人慢慢玩' },
  { label: '本地周末客', message: '改成本地周末客，周末本地人出来放松' },
]

function ask(text: string) {
  brief.value = text
  return submit()
}

// 调价格必须带一个目标数字，后端才能真的重算，而不是只改显示。
async function applyPriceTarget() {
  const value = priceTarget.value.trim()
  if (!value) { showToast('请输入目标价格'); return }
  if (!/^\d+(\.\d+)?$/.test(value)) { showToast('目标价格请填数字'); return }
  priceTarget.value = ''
  activeAdjust.value = ''
  await ask(`价格做到 ${value} 以内`)
}

function growInput(event: Event) {
  const el = event.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 140)}px`
}

const CROWD_LABELS: Record<string, string> = {
  FAMILY: '亲子家庭',
  COUPLE: '两人同行',
  FRIENDS: '朋友同行',
  SOLO: '独自出行',
  LOCAL_WEEKEND: '本地周末客',
  ALL: '不限客群',
}

function crowdLabel(code: unknown) {
  const key = String(code || '').toUpperCase()
  if (CROWD_LABELS[key]) return CROWD_LABELS[key]
  return /^[A-Z_]+$/.test(key) ? '其他客群' : String(code || '')
}

function crowdListLabel(value: unknown) {
  return String(value || '').split(',').map((item) => crowdLabel(item.trim())).filter(Boolean).join('、')
}

function recommendationClass(item: AnyRecord) {
  const level = String(item.recommendation_level || '')
  if (level === 'recommended') return 'resource-card--recommended'
  if (level === 'not_recommended') return 'resource-card--not-recommended'
  return 'resource-card--caution'
}

function recommendationLabel(item: AnyRecord) {
  const label = String(item.recommendation_label || '')
  if (label) return label
  return item.recommendation_level === 'not_recommended' ? '不建议优先'
    : item.recommendation_level === 'recommended' ? '优先推荐' : '可选，需核对'
}

function categoryLabel(value: unknown) {
  const labels: Record<string, string> = { PERFORMANCE: '演出剧场', ENTERTAINMENT: '娱乐体验', PHOTO: '旅拍', NIGHTLIFE: '夜游', FOOD: '美食体验', SPORT: '运动体验', CULTURE: '文化体验' }
  const key = String(value || '').toUpperCase()
  return labels[key] || (/^[A-Z_]+$/.test(key) ? '其他类别' : String(value || '其他'))
}

function statusLabel(value: unknown) {
  const key = String(value || '').toUpperCase()
  const labels: Record<string, string> = { CONFIRMED: '已成交', HELD: '待确认', CANCELLED: '已取消', PENDING_CONFIRMATION: '待确认', ON_SALE: '在售', LOW_STOCK: '库存紧张', SOLD_OUT: '已售罄', PAUSED: '暂停销售', OFF_SHELF: '已下架', DRAFT: '草稿' }
  return labels[key] || (/^[A-Z_]+$/.test(key) ? '已处理' : String(value || '已处理'))
}

function statusTone(value: unknown) {
  const key = String(value || '').toUpperCase()
  if (['AVAILABLE', 'CONFIRMED', 'ON_SALE', 'ACTIVE', '已核验', '可售', '可组包', '可用'].includes(key)) return 'good'
  if (['HELD', 'PENDING_CONFIRMATION', 'PENDING', 'LOW_STOCK', 'STALE', '待确认', '库存紧张', '信息待更新', '未开放组包'].includes(key)) return 'warning'
  if (['CANCELLED', 'SOLD_OUT', 'PAUSED', 'OFF_SHELF', 'DISABLED', '已取消', '已售罄', '已下架', '已停用', '暂停使用', '暂无余量', '未启用', '未开放组包', '需复核'].includes(key)) return 'muted'
  return 'neutral'
}

function resourceAvailabilityLabel(row: AnyRecord) {
  const state = String(row.status || '').toUpperCase()
  if (state !== 'AVAILABLE') return ({ DISABLED: '已停用', PAUSED: '暂停使用', SOLD_OUT: '暂无余量', INACTIVE: '未启用' } as Record<string, string>)[state] || statusLabel(row.status)
  if (!row.package_enabled) return '未开放组包'
  return Number(row.remaining_capacity || 0) > 0 ? '可组包' : '暂无余量'
}

function serviceAvailabilityLabel(row: AnyRecord) {
  const state = String(row.status || '').toUpperCase()
  if (state !== 'AVAILABLE') return ({ DISABLED: '已停用', PAUSED: '暂停使用', SOLD_OUT: '暂无余量', INACTIVE: '未启用' } as Record<string, string>)[state] || statusLabel(row.status)
  return Number(row.available_quantity || 0) > 0 ? '可用' : '暂无余量'
}

function weatherScenarioLabel(row: AnyRecord) {
  if (!row.usable) return '待核验'
  const labels: Record<string, string> = { RAIN: '有雨', SUNNY: '晴', CLOUDY: '多云' }
  return labels[String(row.scenario || '')] || '待核验'
}

function weatherScenarioTone(row: AnyRecord) {
  if (!row.usable) return 'muted'
  return ({ RAIN: 'warning', SUNNY: 'good', CLOUDY: 'neutral' } as Record<string, string>)[String(row.scenario || '').toUpperCase()] || 'neutral'
}

function normalizePrimaryParty(primary: AnyRecord) {
  const defaults: Record<string, number> = { FAMILY: 3, COUPLE: 2, FRIENDS: 3, SOLO: 1, LOCAL_WEEKEND: 2 }
  const crowd = String(primary.crowd || '').toUpperCase()
  const expected = defaults[crowd]
  if (expected === undefined || Number(primary.party_size) === expected) return primary
  return { ...primary, party_size: expected, crowd_label: crowdLabel(crowd) }
}

function marginText(value: unknown) {
  const ratio = Number(value)
  if (!Number.isFinite(ratio)) return ''
  const percent = ratio <= 1 ? ratio * 100 : ratio
  return `${percent.toFixed(1)}%`
}

// 候选卡图片优先用合作资源图，其次房型图，避免所有卡片都用同一张房间照。
function proposalImage(proposal: AnyRecord) {
  const resources = (proposal?.product?.resources || []) as AnyRecord[]
  const partner = resources.find((item) => item?.resource_type === 'PARTNER_RESOURCE' && item?.image_url)
  const anyResource = resources.find((item) => item?.image_url)
  return String(partner?.image_url || anyResource?.image_url || '')
}

function experienceNames(proposal: AnyRecord) {
  const resources = (proposal?.product?.resources || []) as AnyRecord[]
  return resources
    .filter((row) => row.resource_type === 'PARTNER_RESOURCE')
    .map((row) => String(row.resource_name || ''))
    .filter(Boolean)
}

function hotelServiceNames(proposal: AnyRecord) {
  const resources = (proposal?.product?.resources || []) as AnyRecord[]
  return resources.filter((row) => row.resource_type === 'HOTEL_SERVICE').map((row) => String(row.resource_name || '')).filter(Boolean)
}

function candidateReason(proposal: AnyRecord) {
  const product = proposal?.product as AnyRecord | undefined
  if (!product) return ''
  const resources = (product.resources || []) as AnyRecord[]
  const room = resources.find((row) => row.resource_type === 'ROOM')
  const partners = resources.filter((row) => row.resource_type === 'PARTNER_RESOURCE')
  const services = resources.filter((row) => row.resource_type === 'HOTEL_SERVICE')
  const insight = (proposal.insight_snapshot || {}) as AnyRecord
  const topCrowds = (insight.top_crowds || []) as AnyRecord[]
  const bits: string[] = []
  if (room) bits.push(`房型「${room.resource_name}」可住 ${product.party_size} 人，1 晚`)
  for (const row of partners) {
    const window = row.start_time && row.end_time
      ? `${String(row.start_time).slice(0, 5)}–${String(row.end_time).slice(0, 5)}`
      : '按场次'
    bits.push(`体验「${row.resource_name}」${window}，每套占用 ${row.quantity_per_package} 席`)
  }
  for (const row of services) {
    const quantity = row.quantity_per_package || 1
    bits.push(`酒店服务「${row.resource_name}」每套 ${quantity} 份，已纳入容量校验`)
  }
  if (topCrowds.length) bits.push(`近 15 天${crowdLabel(topCrowds[0].target_crowd)}成交最集中（${topCrowds[0].confirmed_orders} 单）`)
  if (product.bottleneck_resource) bits.push(`可售上限受「${product.bottleneck_resource}」限制，本轮最多 ${product.sale_quantity} 套`)
  if (product.suggested_price !== undefined && product.unit_cost !== undefined) {
    bits.push(`建议售价 ¥${product.suggested_price}，单位成本 ¥${product.unit_cost}，毛利率 ${marginText(product.gross_margin)}`)
  }
  return bits.join('；') + '。'
}

// 「查看推荐依据」要能回答「为什么是它」，因此按房态、资源、定价、客群、校验逐项给出可核查的事实。
function candidateEvidenceRows(proposal: AnyRecord): AnyRecord[] {
  const product = proposal?.product as AnyRecord | undefined
  if (!product) return []
  const resources = (product.resources || []) as AnyRecord[]
  const room = resources.find((row) => row.resource_type === 'ROOM')
  const partners = resources.filter((row) => row.resource_type === 'PARTNER_RESOURCE')
  const services = resources.filter((row) => row.resource_type === 'HOTEL_SERVICE')
  const insight = (proposal?.insight_snapshot || {}) as AnyRecord
  const topCrowds = ((insight.top_crowds || []) as AnyRecord[])
  const rows: AnyRecord[] = []
  if (room) {
    const remaining = room.remaining_capacity ?? room.available_count ?? room.capacity ?? '—'
    rows.push({
      label: '房态与容量',
      text: `房型「${room.resource_name}」${product.target_date}${remaining === '—' || remaining === null || remaining === undefined ? '' : ` 余量 ${remaining} 间`}，可住 ${product.party_size} 人；按当日房间余量与体验席位核定本产品最多可售 ${product.sale_quantity ?? '—'} 套。`,
    })
  }
  for (const row of partners) {
    const window = row.start_time && row.end_time ? `${String(row.start_time).slice(0, 5)}–${String(row.end_time).slice(0, 5)}` : '按场次'
    const seat = row.quantity_per_package || 1
    const remain = row.remaining_capacity ?? row.available_quantity ?? '—'
    const hasRemain = remain !== '—' && remain !== null && remain !== undefined
    rows.push({
      label: '体验资源',
      text: `「${row.resource_name}」${window}，每套占用 ${seat} 席${hasRemain ? `，当期余量 ${remain} 份` : ''}${row.indoor === true ? '，室内体验，雨天可执行' : row.indoor === false ? '，户外体验，出行前复核天气' : ''}${row.settlement_price !== undefined ? `，结算价 ¥${row.settlement_price}/份` : ''}。`,
    })
  }
  for (const row of services) {
    rows.push({
      label: '酒店权益',
      text: `「${row.resource_name}」每套 ${row.quantity_per_package || 1} 份${row.available_quantity !== undefined ? `，当期余量 ${row.available_quantity} 份` : ''}${row.unit_cost !== undefined ? `，单份成本 ¥${row.unit_cost}` : ''}，已纳入容量校验。`,
    })
  }
  if (product.suggested_price !== undefined && product.unit_cost !== undefined) {
    rows.push({
      label: '价格与利润',
      text: `建议售价 ¥${product.suggested_price}，单位成本 ¥${product.unit_cost}，最低合法价 ${product.minimum_allowed_price !== undefined ? `¥${product.minimum_allowed_price}` : '按成本与最低毛利核定'}，毛利率 ${marginText(product.gross_margin) || '—'}；容量瓶颈：${product.bottleneck_resource || '未触发限制'}。`,
    })
  }
  if (topCrowds.length) {
    const top = topCrowds[0]
    const share = top.share === undefined || top.share === null ? '' : `，占比 ${top.share}%`
    rows.push({
      label: '客群依据',
      text: `近 15 天成交最集中的客群是${crowdLabel(top.target_crowd)}（${top.confirmed_orders} 单${share}），本产品目标客群为${crowdLabel(product.target_crowd)}。`,
    })
  } else {
    rows.push({
      label: '客群依据',
      text: `近 15 天没有可用的成交样本，本产品目标客群${crowdLabel(product.target_crowd)}来自房型可住人数与资源适配标签，不做历史成交推断。`,
    })
  }
  rows.push({
    label: '校验结论',
    text: `库存、资源名额、价格下限与利润已通过校验${product.sale_quantity ? `（可售 ${product.sale_quantity} 套）` : ''}；发布前会再按实时房态复核一次。`,
  })
  return rows
}

const roomTypeSummaries = computed<AnyRecord[]>(() => {
  const grouped = new Map<string, AnyRecord>()
  for (const room of roomEvidenceRows.value) {
    const key = displayValue(room.room_type, '未命名房型')
    const entry = grouped.get(key) || { room_type: key, available_count: 0, dates: new Set<string>(), max_guests: 0 }
    entry.available_count += Number(room.available_count || 0)
    entry.dates.add(String(room.available_date || ''))
    entry.max_guests = Math.max(entry.max_guests, Number(room.max_guests || 0))
    grouped.set(key, entry)
  }
  const rows: AnyRecord[] = [...grouped.values()].map((item) => ({ ...item, date_count: item.dates.size }))
  return rows.sort((a, b) => Number(b.available_count || 0) - Number(a.available_count || 0))
})
function topThreeWithTies(rows: AnyRecord[], valueOf: (row: AnyRecord) => number) {
  const sorted = rows.slice().sort((a, b) => valueOf(b) - valueOf(a))
  if (sorted.length <= 3) return sorted
  const cutoff = valueOf(sorted[2])
  return sorted.filter((row, index) => index < 3 || valueOf(row) === cutoff)
}
function competitionRank(rows: AnyRecord[], index: number, valueOf: (row: AnyRecord) => number) {
  return rows.slice(0, index).filter((row) => valueOf(row) > valueOf(rows[index])).length + 1
}
function naturalCountGroups(rows: AnyRecord[], labelOf: (row: AnyRecord) => string, countOf: (row: AnyRecord) => number, unit: string) {
  const groups = new Map<number, string[]>()
  for (const row of rows) {
    const count = Number(countOf(row) || 0)
    const labels = groups.get(count) || []
    labels.push(labelOf(row))
    groups.set(count, labels)
  }
  return [...groups.entries()].sort((a, b) => b[0] - a[0]).map(([count, labels]) =>
    labels.length === 1 ? `${labels[0]}（${count}${unit}）` : `${labels.join('、')}并列（各${count}${unit}）`,
  ).join('；')
}
function naturalProductSales(rows: AnyRecord[]) {
  if (!rows.length) return '暂无可按产品拆分的成交'
  const rankedRows = topThreeWithTies(rows, (row) => Number(row.confirmed_orders || 0))
  const counts = new Set(rankedRows.map((row) => Number(row.confirmed_orders || 0)))
  if (counts.size === 1 && rankedRows.length > 3) {
    const names = rankedRows.map((row) => `「${String(row.product_name || '未命名套餐')}」`).join('、')
    return `近15天成交比较分散，${rankedRows.length}款套餐各成交${Number(rankedRows[0].confirmed_orders || 0)}单，包括${names}，目前还没有明显领先的套餐。`
  }
  const groups = naturalCountGroups(rankedRows, (row) => `「${String(row.product_name || '未命名套餐')}」`, (row) => Number(row.confirmed_orders || 0), '单')
  return `近期成交较多的套餐包括${groups}。`
}
function naturalExperienceSales(rows: AnyRecord[]) {
  if (!rows.length) return '暂无套餐体验与订单的关联统计'
  const counts = new Set(rows.map((row) => Number(row.confirmed_orders || 0)))
  if (counts.size === 1 && rows.length > 3) {
    const names = rows.map((row) => String(row.name || '未命名体验')).join('、')
    return `套餐关联成交较分散：${names}各关联${Number(rows[0].confirmed_orders || 0)}单，目前还看不出哪项体验明显领先。`
  }
  const groups = naturalCountGroups(rows, (row) => String(row.name || '未命名体验'), (row) => Number(row.confirmed_orders || 0), '单')
  return `成交套餐关联较多的体验包括${groups}。`
}
const topInventorySlots = computed<AnyRecord[]>(() => topThreeWithTies(roomEvidenceRows.value, (row) => Number(row.available_count || 0)))
const recentCrowdRanks = computed<AnyRecord[]>(() => {
  const rows = ((recentOrderSummary.value.top_crowds || []) as AnyRecord[]).slice().sort((a, b) => Number(b.confirmed_orders || 0) - Number(a.confirmed_orders || 0))
  return topThreeWithTies(rows, (row) => Number(row.confirmed_orders || 0))
})
const crowdRankText = computed(() => recentCrowdRanks.value.length
  ? naturalCountGroups(recentCrowdRanks.value, (row) => crowdLabel(row.target_crowd), (row) => Number(row.confirmed_orders || 0), '单')
  : '暂无已确认订单客群样本')
const recentExperienceRanks = computed<AnyRecord[]>(() => (recentOrderSummary.value.top_experiences || []) as AnyRecord[])
const resourceNameStats = computed<AnyRecord[]>(() => {
  const grouped = new Map<string, AnyRecord>()
  for (const row of sellableResourceEvidenceRows.value) {
    const name = String(row.name || '未命名体验')
    const item = grouped.get(name) || { name, category: row.category, dates: new Set<string>(), max_capacity: 0, product_count: 0, recent_confirmed_orders: 0, indoor: Boolean(row.indoor), best_date: String(row.available_date || '') }
    item.dates.add(String(row.available_date || ''))
    if (Number(row.remaining_capacity || 0) > item.max_capacity) {
      item.max_capacity = Number(row.remaining_capacity || 0)
      item.best_date = String(row.available_date || '')
    }
    item.product_count = Math.max(item.product_count, Number(row.product_count || 0))
    item.recent_confirmed_orders = Math.max(item.recent_confirmed_orders, Number(row.recent_confirmed_orders || 0))
    grouped.set(name, item)
  }
  const sales = new Map(recentExperienceRanks.value.map((row) => [String(row.name || ''), Number(row.confirmed_orders || 0)]))
  const rows: AnyRecord[] = [...grouped.values()].map((item) => ({ ...item, date_count: item.dates.size, linked_confirmed_orders: sales.get(item.name) ?? item.recent_confirmed_orders }))
  return rows.sort((a, b) => Number(b.linked_confirmed_orders || 0) - Number(a.linked_confirmed_orders || 0) || Number(b.product_count || 0) - Number(a.product_count || 0) || Number(b.date_count || 0) - Number(a.date_count || 0) || Number(b.max_capacity || 0) - Number(a.max_capacity || 0))
})
const topResourceNames = computed<AnyRecord[]>(() => resourceNameStats.value.slice(0, 3))
const leastPromotedResource = computed<AnyRecord | null>(() => resourceNameStats.value.slice().sort((a, b) => a.linked_confirmed_orders - b.linked_confirmed_orders || a.product_count - b.product_count || a.date_count - b.date_count)[0] || null)
const rainyForecasts = computed<AnyRecord[]>(() => weatherUsableRows.value.filter((row) => String(row.scenario || '').toUpperCase() === 'RAIN'))
const sunnyForecasts = computed<AnyRecord[]>(() => weatherUsableRows.value.filter((row) => String(row.scenario || '').toUpperCase() === 'SUNNY'))
const indoorResourceNames = computed(() => [...new Set(sellableResourceEvidenceRows.value.filter((row) => row.indoor).map((row) => String(row.name || '')).filter(Boolean))].slice(0, 5))
const outdoorResourceNames = computed(() => [...new Set(sellableResourceEvidenceRows.value.filter((row) => !row.indoor).map((row) => String(row.name || '')).filter(Boolean))].slice(0, 5))
const leastAssociatedExperience = computed<AnyRecord | null>(() => recentExperienceRanks.value.slice().sort((a, b) => Number(a.confirmed_orders || 0) - Number(b.confirmed_orders || 0))[0] || null)
const upcomingWeekdayDates = computed(() => [...new Set(roomEvidenceRows.value.map((row) => String(row.available_date || '')).filter((value) => value && ![0, 6].includes(new Date(`${value}T00:00:00`).getDay())))].sort())
const upcomingWeekendDates = computed(() => [...new Set(roomEvidenceRows.value.map((row) => String(row.available_date || '')).filter((value) => value && [0, 6].includes(new Date(`${value}T00:00:00`).getDay())))].sort())
const familyRoomDates = computed(() => [...new Set(roomEvidenceRows.value.filter((row) => Number(row.max_guests || 0) >= 3 || /亲子|家庭/.test(displayValue(row.room_type))).map((row) => String(row.available_date || '')).filter(Boolean))].sort())
const knowledgeRows = computed<AnyRecord[]>(() => (overview.value.knowledge || []) as AnyRecord[])
const verifiedKnowledgeRows = computed(() => knowledgeRows.value.filter((row) => String(row.verification_status || '').toUpperCase() === 'ACTIVE'))
const knowledgeReviewDueIn = computed<number | null>(() => {
  const remaining = verifiedKnowledgeRows.value.map((row) => Number(row.review_window_days || 0) - Number(row.source_age_days || 0)).filter(Number.isFinite)
  return remaining.length ? Math.max(0, Math.min(...remaining)) : null
})
const inventoryDateRange = computed(() => {
  const dates = [...new Set(roomEvidenceRows.value.map((row) => String(row.available_date || '')).filter(Boolean))].sort()
  return dates.length ? `${dates[0]} 至 ${dates[dates.length - 1]}` : '未来日期暂无房态记录'
})
const roomTypeSummaryText = computed(() => roomTypeSummaries.value.map((row) => `${displayValue(row.room_type, '房型')}（${row.available_count}间）`).join('、') || '暂无可售房型')
const topInventoryText = computed(() => topInventorySlots.value.slice(0, 3).map((row) => {
  const count = Number(row.available_count ?? row.remaining)
  const quantity = Number.isFinite(count) ? `余${count}间` : '余量待核实'
  return `${displayDate(row.available_date)}的${displayValue(row.room_type, '房型')}${quantity}`
}).join('；') || '暂无库存集中点')
const weekendDatesText = computed(() => upcomingWeekendDates.value.map(displayDate).join('、') || '未来17天没有可售周末日期')
const weekdayDatesText = computed(() => upcomingWeekdayDates.value.map(displayDate).join('、') || '未来17天没有可售工作日日期')

const overviewConclusion = computed(() => {
  if (!dataReady.value) return loadError.value ? '经营数据暂未读取成功，可重试后查看完整诊断。' : '正在读取经营数据，诊断结论会随数据返回逐步更新。'
  const focus = focusRoom.value
  const orders = Number(recentOrderSummary.value.confirmed_count ?? recentConfirmedRows.value.length ?? 0)
  const leadCrowd = recentCrowdRanks.value[0]
  const inventoryText = focus
    ? `未来${pressure.value.window_days ?? 17}天（${inventoryDateRange.value}）各日期共有${roomEvidenceTotal.value}间可售房间，覆盖${roomEvidenceDateCount.value}个日期和${roomEvidenceTypeCount.value}种房型；${roomTypeSummaryText.value}。目前重点关注${displayDate(focus.target_date)}的${displayValue(focus.room_type, '重点房型')}，还余${Number(focus.remaining || 0)}间。`
    : `未来${pressure.value.window_days ?? 17}天共有${roomEvidenceTotal.value}间可售房间，覆盖${roomEvidenceDateCount.value}个日期和${roomEvidenceTypeCount.value}种房型。`
  const salesText = evidenceState('orders') === 'ready'
    ? orders ? `近15天确认${orders}单，客群前三为${crowdRankText.value}。` : '近15天暂无确认订单，不推断主力客群。'
    : evidenceState('orders') === 'error' ? '近15天订单数据暂不可用' : '近15天订单和客群正在采集'
  const weatherText = weatherFetchState.value === 'ready'
    ? `未来15天有${rainyForecasts.value.length}个有效降雨日${rainyForecasts.value.length ? `（${rainyForecasts.value.map((row) => row.target_date).join('、')}）` : ''}，晴天${sunnyForecasts.value.length}天${sunnyForecasts.value.length ? `（${sunnyForecasts.value.map((row) => row.target_date).join('、')}）` : ''}。`
    : weatherFetchState.value === 'error' ? '天气接口暂不可用，建议组合保留室内体验' : '未来15天天气正在采集'
  const recommendation = leadCrowd && focus
    ? `经营方向上，工作日可围绕近期成交较多的${crowdLabel(leadCrowd.target_crowd)}安排轻体验，并选择当天有房、有体验名额的组合；周末家庭房有库存的日期包括${familyRoomDates.value.filter((date) => [0, 6].includes(new Date(`${date}T00:00:00`).getDay())).slice(0, 4).map(displayDate).join('、') || '暂无'}，适合补充亲子方案。`
    : '建议从仍有房的日期开始，结合当天可售体验、客群成交和天气，形成一款优先方案及有差异的备选。'
  return `${inventoryText}${salesText}${weatherText}${recommendation}`
})

const overviewCards = computed<AnyRecord[]>(() => {
  const orders = Number(recentOrderSummary.value.confirmed_count ?? recentConfirmedRows.value.length ?? 0)
  const crowd = recentCrowdRanks.value[0]
  const weatherNumber = 15
  return [
    { key: 'inventory', label: '库存现状', value: dataReady.value ? `${roomEvidenceTotal.value} 间可售房间` : '读取中', detail: `${roomEvidenceDateCount.value}个日期 · ${roomEvidenceTypeCount.value}种房型${roomTypeSummaries.value.length ? `；${roomTypeSummaries.value.map((row) => `${displayValue(row.room_type, '房型')}（${row.available_count}间）`).join('、')}` : ''}${focusRoom.value ? `；重点 ${displayValue(focusRoom.value.room_type, '房型')} · ${displayDate(focusRoom.value.target_date)}余${Number(focusRoom.value.remaining || 0)}间` : ''}`, source: 'inventory' },
    { key: 'orders', label: '近期客群', value: evidenceState('orders') === 'ready' ? `${orders} 笔确认订单` : evidenceStateLabel('orders'), detail: evidenceState('orders') === 'loading' || evidenceState('orders') === 'pending' ? '正在读取近15天订单' : evidenceState('orders') === 'error' ? '订单接口暂不可用' : orders && crowd ? `成交客群：${crowdRankText.value}` : '暂无确认订单样本', source: 'orders' },
    { key: 'resources', label: '体验与服务资源', value: evidenceState('resources') === 'ready' ? `${sellableResourceEvidenceRows.value.length} 条可组包体验记录` : evidenceStateLabel('resources'), detail: evidenceState('resources') === 'ready' ? `酒店服务 ${sellableServiceEvidenceRows.value.length} 条；高频体验 ${topResourceNames.value.slice(0, 2).map((item) => item.name).join('、') || '暂无'}` : '正在核对日期、名额和结算信息', source: 'resources' },
    { key: 'weather', label: '天气趋势', value: weatherFetchState.value === 'ready' ? `杭州未来${weatherNumber}天` : weatherFetchState.value === 'error' ? '获取失败' : '获取中', detail: weatherStatusText.value, source: 'weather' },
  ]
})

const diagnosisSteps = computed<AnyRecord[]>(() => {
  const confirmed = Number(recentOrderSummary.value.confirmed_count ?? recentConfirmedRows.value.length ?? 0)
  const firstCrowd = recentCrowdRanks.value[0]
  const allDone = evidenceSettledCount.value === evidenceSections.length
  const rankedProductText = naturalProductSales((recentOrderSummary.value.top_products || []) as AnyRecord[])
  const topExperienceRows = topThreeWithTies(recentExperienceRanks.value, (row) => Number(row.confirmed_orders || 0))
  const experienceText = naturalExperienceSales(topExperienceRows)
  const rainText = rainyForecasts.value.map((row) => displayDate(row.target_date)).join('、') || '无有效降雨预报日'
  const sunText = sunnyForecasts.value.map((row) => displayDate(row.target_date)).join('、') || '无有效晴天预报日'
  const knowledgeNames = knowledgeRows.value.slice(0, 8).map((row) => String(row.name || '')).filter(Boolean).join('、')
  const knowledgeStatusCounts = {
    active: verifiedKnowledgeRows.value.length,
    stale: knowledgeRows.value.filter((row) => String(row.verification_status || '').toUpperCase() === 'STALE').length,
    review: knowledgeRows.value.filter((row) => String(row.verification_status || '').toUpperCase() === 'VERIFY_REQUIRED').length,
  }
  const focusedResourceRows = sellableResourceEvidenceRows.value.filter((row) => String(row.available_date || '') === String(focusRoom.value?.target_date || ''))
    .slice().sort((a, b) => Number(b.remaining_capacity || 0) - Number(a.remaining_capacity || 0)).slice(0, 3)
  const allSourcesReady = evidenceReadyCount.value === evidenceSections.length
  const focusRoomAlreadyListed = focusRoom.value && topInventorySlots.value.some((row) => String(row.available_date) === String(focusRoom.value?.target_date) && displayValue(row.room_type) === displayValue(focusRoom.value?.room_type))
  const inventoryImpact = focusRoom.value
    ? `当前剩余房间较多的日期和房型有：${topInventoryText.value}${focusRoomAlreadyListed ? '' : `；另需关注${displayDate(focusRoom.value.target_date)}的${displayValue(focusRoom.value.room_type, '重点房型')}（余${Number(focusRoom.value.remaining || 0)}间）`}。${focusedResourceRows.length ? `同日还有${focusedResourceRows.map((row) => `${displayValue(row.name, '体验')}（余${Number(row.remaining_capacity || 0)}份）`).join('、')}可搭配，适合组成明确日期的住宿体验套餐。` : '该日期暂未找到可组包体验，可优先考虑房间和体验都有余量的日期。'}`
    : '当前没有可售房间记录，需先补齐库存后再生成住宿组合。'
  const orderImpact = confirmed
    ? `${firstCrowd ? `近期成交客群以${crowdRankText.value}为主。` : ''}${rankedProductText}。未来可售工作日包括${upcomingWeekdayDates.value.slice(0, 6).map(displayDate).join('、') || '暂无'}；有房周末包括${upcomingWeekendDates.value.map(displayDate).join('、') || '暂无'}，家庭房可售日期为${familyRoomDates.value.filter((date) => [0, 6].includes(new Date(`${date}T00:00:00`).getDay())).slice(0, 5).map(displayDate).join('、') || '暂无'}。工作日适合优先推出双人轻体验；周末若家庭房与亲子体验同日有余量，可补充亲子方案。`
    : '近15天没有已确认订单，无法按成交客群排序；先依据可售库存、已开放体验和天气安排做小批量方案。'
  const resourceImpact = `${topResourceNames.value.length ? `套餐中近期成交关联较多的体验有${naturalCountGroups(topResourceNames.value, (row) => String(row.name || '未命名体验'), (row) => Number(row.linked_confirmed_orders || 0), '单')}；目前${topResourceNames.value.map((row) => `${row.name}有${row.date_count}个可售日期、单日最多${row.max_capacity}份`).join('，')}。` : '当前没有可售且开放组包的合作体验。'}${leastPromotedResource.value ? `关联成交较少的是${leastPromotedResource.value.name}（${leastPromotedResource.value.linked_confirmed_orders}单），但仍有${leastPromotedResource.value.date_count}个可售日期；可以完善体验介绍、适合人群和参与方式，再安排到有房日期，帮助游客理解它的价值。` : ''}酒店服务有${sellableServiceEvidenceRows.value.length}条可用日期记录，只有与房间、体验日期一致的服务适合放入同一套餐。`
  const weatherImpact = `${rainyForecasts.value.length ? `有雨日期为${rainText}，更适合把${indoorResourceNames.value.length ? indoorResourceNames.value.join('、') : '当日可售的室内体验'}安排为主要活动；城市漫步等户外项目可缩短停留或调整到晴天。` : '未来15天有效预报没有标记降雨日。'}${sunnyForecasts.value.length ? `晴天日期为${sunText}，可优先安排${outdoorResourceNames.value.length ? outdoorResourceNames.value.join('、') : '当日有余量的户外体验'}。` : '未来15天暂无有效晴天记录。'}${indoorResourceNames.value.length ? `${indoorResourceNames.value.join('、')}不受户外降雨直接影响，可作为组合中的稳定体验。` : ''}`
  const knowledgeImpact = `知识库有${knowledgeTotal.value}条地点记录，已核验${knowledgeStatusCounts.active}条、信息待更新${knowledgeStatusCounts.stale}条、需复核${knowledgeStatusCounts.review}条${knowledgeNames ? `，包括${knowledgeNames}${knowledgeTotal.value > 8 ? '等' : ''}` : ''}。${knowledgeReviewDueIn.value === null ? '记录没有注明复核周期，暂时无法推算复核日期。' : knowledgeReviewDueIn.value === 0 ? '最近一批记录已到复核时间，建议核对开放时间和预约信息。' : `最近一批已核验记录将在${knowledgeReviewDueIn.value}天后进入复核时间。`}目前订单能关联到套餐体验，但没有和单个目的地建立对应关系，因此可以总结套餐包含哪些地点，不能据此判断游客最喜欢或最少选择的目的地。`
  const summaryResult = allSourcesReady
    ? `${overviewConclusion.value}${experienceText}。知识库中${knowledgeStatusCounts.active}条地点信息已核验，${knowledgeStatusCounts.stale + knowledgeStatusCounts.review}条仍需跟进。`
    : `经营数据已返回${evidenceReadyCount.value}/${evidenceSections.length}类；所有分类加载完成后会汇总库存、订单、资源、天气与知识。`
  const summaryImpact = focusRoom.value
    ? `如果希望延续近期${firstCrowd ? crowdLabel(firstCrowd.target_crowd) : '主要客群'}的成交表现，可把${displayDate(focusRoom.value.target_date)}的${displayValue(focusRoom.value.room_type, '可售房型')}（余${Number(focusRoom.value.remaining || 0)}间）与${focusedResourceRows.map((row) => `${row.name}（余${row.remaining_capacity}份）`).join('、') || '当天仍有名额的体验'}组合，作为具体的主推方案。降雨日期${rainText}宜安排${indoorResourceNames.value.slice(0, 2).join('、') || '当日可售室内体验'}；周末家庭房有余量时，再搭配适合亲子参与的体验。`
    : '先补齐有效房态，再从近期已确认客群、可售体验和15天天气中选取有具体数据支持的方向。'
  return [
    { key: 'inventory', title: '房态与库存', state: evidenceState('inventory'), source: '客房库存接口 · 未来17天逐日房型可售数与参考价', result: evidenceState('inventory') === 'ready' ? `未来${roomEvidenceDateCount.value}个有房日期（${inventoryDateRange.value}）共有${roomEvidenceTotal.value}间可售房间；各房型余量为${roomTypeSummaryText.value}。余量相对较多的日期和房型包括：${topInventoryText.value}。` : evidenceState('inventory') === 'error' ? '房态暂不可用，本轮不会基于缺失库存作产品判断。' : '正在读取未来日期的房型、余量与参考价。', impact: inventoryImpact },
    { key: 'orders', title: '近期成交与客群', state: evidenceState('orders'), source: '游客订单 · 最近15天已确认订单及产品目标客群', result: evidenceState('orders') === 'ready' ? confirmed ? `近15天共有${confirmed}笔确认订单，客群分布为${crowdRankText.value}。${rankedProductText}` : '近15天暂无确认订单，当前没有足够样本判断主要客群。' : evidenceState('orders') === 'error' ? '订单数据暂不可用，本轮不推断客群偏好。' : '正在统计近15天确认订单、金额与客群。', impact: orderImpact },
    { key: 'resources', title: '体验与酒店资源', state: evidenceState('resources'), source: '合作资源、酒店服务、产品组成关系及最近15天确认订单', result: evidenceState('resources') === 'ready' ? `未来15天有${sellableResourceEvidenceRows.value.length}条可组包体验日期记录、${sellableServiceEvidenceRows.value.length}条可用酒店服务日期记录。成交关联较多的体验有${naturalCountGroups(topResourceNames.value, (row) => String(row.name || '未命名体验'), (row) => Number(row.linked_confirmed_orders || 0), '单') || '暂无'}。${leastPromotedResource.value ? `目前关联较少的是${leastPromotedResource.value.name}（${leastPromotedResource.value.linked_confirmed_orders}单）` : ''}` : evidenceState('resources') === 'error' ? '资源数据暂不可用，暂不将体验写入方案。' : '正在核对合作体验、酒店服务的日期余量和成本。', impact: resourceImpact },
    { key: 'weather', title: '天气与路线', state: evidenceState('weather'), source: '杭州逐日天气预报服务 · 未来15天', result: weatherFetchState.value === 'loading' || weatherFetchState.value === 'idle' ? '正在获取杭州未来15天逐日天气。' : weatherFetchState.value === 'error' ? '天气接口未返回，当前不使用猜测天气；方案需保留室内替代路线。' : `未来15天读取${weatherEvidenceRows.value.length}天，其中${weatherUsableRows.value.length}天可用；降雨风险：${rainText}；晴天：${sunText}。`, impact: weatherImpact },
    { key: 'knowledge', title: '目的地知识', state: evidenceState('knowledge'), source: '文旅知识库 · 地点、开放信息、来源与核验时间', result: evidenceState('knowledge') === 'ready' ? `地点知识共${knowledgeTotal.value}条：已核验${knowledgeStatusCounts.active}条、待更新${knowledgeStatusCounts.stale}条、待核验${knowledgeStatusCounts.review}条。地点样例：${knowledgeNames || '暂无登记地点'}${knowledgeTotal.value > 8 ? '等' : ''}。` : evidenceState('knowledge') === 'error' ? '知识库暂不可用，路线说明只采用当前已核对数据。' : '正在读取地点、开放与预约知识。', impact: knowledgeImpact },
    { key: 'summary', title: '综合经营判断', state: allDone ? (evidenceReadyCount.value === evidenceSections.length ? 'ready' : 'partial') : evidenceSettledCount.value ? 'loading' : 'pending', source: '客房库存、确认订单、合作资源、天气服务、文旅知识库', result: summaryResult, impact: summaryImpact },
  ]
})

function syncDiagnosisCollapsedHeight() {
  const grid = diagnosisGridRef.value
  if (!grid) return
  const collapsedHeights = Array.from(grid.querySelectorAll<HTMLElement>('.diagnosis-step')).map((card) => {
    const discovery = card.querySelector<HTMLElement>('.diagnosis-step__discovery')
    if (!discovery) return 0
    const cardRect = card.getBoundingClientRect()
    const discoveryRect = discovery.getBoundingClientRect()
    const style = window.getComputedStyle(card)
    const paddingBottom = Number.parseFloat(style.paddingBottom) || 0
    const borderBottom = Number.parseFloat(style.borderBottomWidth) || 0
    return Math.ceil(discoveryRect.bottom - cardRect.top + paddingBottom + borderBottom)
  })
  const maxHeight = Math.max(0, ...collapsedHeights)
  if (maxHeight) grid.style.setProperty('--diagnosis-collapsed-height', `${maxHeight}px`)
}

watch(diagnosisSteps, () => { void nextTick(syncDiagnosisCollapsedHeight) }, { flush: 'post' })
const handleDiagnosisResize = () => { void nextTick(syncDiagnosisCollapsedHeight) }
onMounted(() => {
  window.addEventListener('resize', handleDiagnosisResize)
  void nextTick(syncDiagnosisCollapsedHeight)
})
onBeforeUnmount(() => window.removeEventListener('resize', handleDiagnosisResize))

const operatingAdvice = computed<AnyRecord>(() => {
  const plan = advicePlan.value
  if (!plan) {
    const focus = focusRoom.value
    return {
      title: '先完善可售房态，再生成具体组合',
      finding: '当前没有可用于主推的可售日期与房型组合。',
      action: '补齐可售库存后，系统会把具体房型、体验场次、天气和近期客群一起纳入方案。',
      reason: '目前缺少可核对的日期或体验组合，因此暂不拼接没有数据支持的产品建议。',
      prompt: '结合当前经营数据重新寻找有房态、有体验名额的日期和房型，并把最匹配的一组放在产品方案第一位。',
      target_date: focus?.target_date || '',
      room_type: focus?.room_type || '',
      resource_names: [],
      source: 'inventory',
      basis: '当前房态与体验资源',
    }
  }

  const targetDate = String(plan.target_date || primarySpec.value?.target_date || '')
  const roomName = displayValue(plan.room_type || primarySpec.value?.room_type, '可售房型')
  const resourceNames = planExperienceNames(plan)
  const room = roomEvidenceRows.value.find((row) => String(row.available_date || '') === targetDate && displayValue(row.room_type) === roomName)
  const matchingResources = resourceEvidenceRows.value.filter((row) =>
    String(row.available_date || '') === targetDate && resourceNames.includes(String(row.name || '')),
  )
  const weather = weatherEvidenceRows.value.find((row) => String(row.target_date || '') === targetDate && row.usable)
  const crowd = recentCrowdRanks.value[0]
  const itinerary = String(planKey(plan)) === selectedPlanKey.value ? ((primarySpec.value?.itinerary_days || []) as AnyRecord[]) : []
  const itinerarySummary = itinerary.map((day) => {
    const names = ((day.items || []) as AnyRecord[])
      .filter((item) => !item.route_only && !/入住|退房|寄存|午餐|自由活动/.test(String(item.title || '')))
      .map((item) => String(item.title || ''))
      .filter(Boolean)
    return String(day.label || ('第' + day.day_index + '天')) + (names.length ? '安排' + names.join('、') : '保留住宿与自由活动时间')
  }).filter(Boolean).join('；')
  const knowledgeDetails = resourceNames.map((name) => {
    const row = knowledgeRows.value.find((item) => {
      const place = String(item.name || '')
      return place && (place.includes(name) || name.includes(place))
    })
    const detail = String(row?.description || row?.summary || row?.introduction || '').trim()
    return detail ? name + '：' + detail.slice(0, 54) + (detail.length > 54 ? '…' : '') : ''
  }).filter(Boolean)
  const experienceWindows = matchingResources.map((row) => String(row.name || '') + (
    row.start_time && row.end_time
      ? '安排在' + String(row.start_time).slice(0, 5) + '–' + String(row.end_time).slice(0, 5)
      : row.window ? '适合' + row.window + '衔接' : '场次需按资源信息确认'
  ))
  const roomCount = Number(room?.available_count ?? plan.remaining ?? primarySpec.value?.room_quantity ?? 0)
  const resourceCount = matchingResources.length
    ? Math.min(...matchingResources.map((row) => Number(row.remaining_capacity || 0)))
    : 0
  const crowdText = crowd ? '近15天' + crowdLabel(crowd.target_crowd) + '有' + Number(crowd.confirmed_orders || 0) + '笔确认订单' : '近期订单样本有限'
  const weatherText = weather?.scenario === 'RAIN'
    ? displayDate(targetDate) + '预报有雨，' + (matchingResources.some((row) => row.indoor) ? '室内体验可作为当天稳定的核心活动，户外部分需要留出调整空间' : '这组体验偏户外，建议缩短停留并准备室内备选')
    : weather?.scenario === 'SUNNY'
      ? displayDate(targetDate) + '预报晴好，户外体验可安排在主要游览时段'
      : displayDate(targetDate) + '的天气暂无可用预报，按场次和资源属性安排'
  const productName = planTitle(plan)
  const resourceText = resourceNames.join('、') || '当天可售的正式体验'
  const linkedKnowledgeText = knowledgeDetails.length
    ? '知识库补充了体验地点的特色：' + knowledgeDetails.join('；')
    : '当前地点知识没有与这组体验直接对应的介绍，建议方案文案以资源本身已核验的内容为准'
  const itineraryText = itinerarySummary || '行程可先办理入住或寄存行李，再在' + (experienceWindows.join('、') || plan.window || '已核定的体验时段') + '安排' + resourceText + '；其他未排定的时段保留给用餐、转场和自由活动。'
  const matchedCrowdLabel = crowd ? crowdLabel(crowd.target_crowd) : displayValue(plan.crowd_label || primarySpec.value?.crowd_label, '目标客群')
  const reasons = [
    displayDate(targetDate) + '的' + roomName + '当前可售' + roomCount + '间，房型与日期明确；' + (resourceNames.map((name) => {
      const row = matchingResources.find((item) => String(item.name || '') === name)
      return row ? name + '当日余' + Number(row.remaining_capacity || 0) + '份' : name
    }).join('，') || '体验名额将在生成时再次校验') + '。',
    crowdText + '，因此以' + matchedCrowdLabel + '作为主要表达方向有近期成交作参考；' + weatherText + '。',
    linkedKnowledgeText + '。' + itineraryText,
  ].filter(Boolean)
  const finding = displayDate(targetDate) + '安排' + roomName + '（余' + roomCount + '间）' + (resourceNames.length ? '，搭配' + resourceNames.join('、') : '') + '；' + crowdText + '。'
  const action = itineraryText + '这组方案把住宿和' + resourceText + '放在同一条行程里，建议突出体验内容与地点特色；' + weatherText + '。'
  const reason = reasons.join(' ')
  const sourceNames = ['逐日房态', '近期确认订单', '合作体验资源', '天气预报'].concat(knowledgeDetails.length ? ['文旅知识库'] : [])
  return {
    title: displayDate(targetDate) + ' · ' + roomName + ' × ' + (resourceNames.join(' × ') || '正式体验'),
    finding,
    action,
    reason,
    prompt: '采用产品方向「' + productName + '」。请固定日期' + targetDate + '、房型' + roomName + '，完整保留体验' + (resourceNames.join('、') || '当前方案中的体验') + '，并将这一组合放在产品方案第一位。主推理由结合' + crowdText + '、当天房态、体验时间和地点知识说明选择原因；行程说明住宿、体验和自由时段如何衔接，并按天气说明需要准备的调整。不得自行新增未核验的体验权益。',
    target_date: targetDate,
    room_type: roomName,
    resource_names: resourceNames,
    source: sourceNames.join('、'),
    basis: roomName + '可售' + roomCount + '间 · ' + (resourceCount ? '体验余量至少' + resourceCount + '份' : resourceNames.length + '项体验') + ' · ' + matchedCrowdLabel,
  }
})
function candidateRelation(proposal: AnyRecord) {
  const names = experienceNames(proposal)
  const product = proposal?.product as AnyRecord | undefined
  const current = ((primarySpec.value?.experiences as AnyRecord[]) || []).map((item) => String(item.name || '')).filter(Boolean)
  const roomName = String(((product?.resources || []) as AnyRecord[]).find((item) => item.resource_type === 'ROOM')?.resource_name || '')
  const sameFrame = product?.target_date === primarySpec.value?.target_date && roomName === String(primarySpec.value?.room_type || '')
  if (!sameFrame) return '替代日期 / 房型'
  if (current.length && current.length === names.length && current.every((name) => names.includes(name))) return '沿用当前资源'
  if (current.length && current.every((name) => names.includes(name))) return '沿用当前资源 · 已增加体验'
  if (current.some((name) => names.includes(name))) return '保留部分体验 · 替换其余资源'
  if (names.length) return '替换体验资源'
  return '替代路线'
}

// 预览与发布阶段只展示本轮生成的产品，不再把历史待确认队列铺到页面上。
const candidateCards = computed<AnyRecord[]>(() => proposals.value
  .filter((proposal) => sessionProposalIds.value.includes(Number(proposal.id)))
  .slice(0, 1)
  .map((proposal) => ({
    key: `candidate-${proposal.id}`,
    proposal,
    product_id: Number(proposal.product_id),
    name: proposal.product?.product_name || '待确认候选',
    price: proposal.product?.suggested_price || '',
    date: proposal.product?.target_date || '',
    crowd_label: crowdLabel(proposal.product?.target_crowd),
    party: proposal.product?.party_size || '',
    quantity: proposal.product?.sale_quantity ?? '',
    margin_label: marginText(proposal.product?.gross_margin),
    cost: proposal.product?.unit_cost ?? '',
    floor_price: proposal.product?.minimum_allowed_price ?? '',
    experiences: experienceNames(proposal),
    services: hotelServiceNames(proposal),
    relation: candidateRelation(proposal),
    reason: candidateReason(proposal),
    image: proposalImage(proposal),
    itinerary: proposal.product?.day_plan || proposal.product?.route_plan || [],
    raw: proposal,
  })))
const copyFields = [
  { key: 'product_name', label: '产品名称' },
  { key: 'marketing_title', label: '游客端标题' },
  { key: 'marketing_content', label: '产品介绍', multiline: true },
  { key: 'recommendation_reason', label: '推荐理由', multiline: true },
  { key: 'risk_message', label: '出行提示', multiline: true },
]
function visitorPreviewUrl(card: AnyRecord) {
  return `/visitor/products/${card.product_id}?preview=1&embedded=1&v=${card.raw?.product?.updated_at || card.raw?.created_at || card.product_id}`
}

// 「换资源」只列同日期、同房型、同客群下的其它合作资源，不改变产品框架。
const resourceSwaps = computed<AnyRecord[]>(() => {
  const primary = primarySpec.value
  if (!primary) return []
  return (((primary.resource_options as AnyRecord[]) || []))
    .filter((item) => !item.is_current)
    .slice()
    .sort((a: AnyRecord, b: AnyRecord) => Number(b.recommendation_score || 0) - Number(a.recommendation_score || 0)
      || Number(a.estimated_price || 0) - Number(b.estimated_price || 0))
})
const budgetShortfall = computed<AnyRecord | null>(() => (primarySpec.value?.budget_shortfall as AnyRecord) || null)

const logicByTitle = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {}
  for (const item of ((primarySpec.value?.logic as AnyRecord[]) || [])) out[String(item.title || '')] = String(item.text || '')
  return out
})

function planBadgeClass(item: AnyRecord) {
  if (item.is_current) return 'is-current'
  if (String(item.label) === '更高容量') return 'is-capacity'
  if (String(item.label) === '更适合雨天') return 'is-rain'
  return 'is-cheaper'
}

function planReason(item: AnyRecord) {
  if (item.is_current && !item.is_ai_primary) return '按你的上一轮调整保留当前组合'
  const label = String(item.label || '')
  if (label === 'AI主推' || label === '主推') return '综合需求、容量与价格最平衡'
  if (label === '更低成本') return '总价更低，适合控制成交门槛'
  if (label === '更适合雨天') return '室内资源优先，天气波动影响较小'
  if (label === '更高容量') return '资源容量更足，适合快速消化库存'
  if (label === '体验增强') return '增加一项正式体验，提高产品丰富度'
  if (label === '换房型') return '换到另一种房型，错峰消化库存'
  return '保持日期与客群，提供另一种组合方向'
}

// 输入框上方说明「正在调整哪个方案」，精确到房型 × 体验。
const currentObjectLabel = computed(() => {
  const primary = primarySpec.value
  if (!primary) return '新方案规划'
  const experiences = ((primary.experiences as AnyRecord[]) || []).map((item) => item.name).filter(Boolean).join(' + ')
  const services = ((primary.services as AnyRecord[]) || []).map((item) => item.name).filter(Boolean).join(' + ')
  const composition = [experiences, services].filter(Boolean).join(' + ')
  return `当前方案 · ${primary.target_date} · ${primary.room_type}${composition ? ` × ${composition}` : ''}`
})

const AUTO_BRIEF = '结合已读取的房态、近15天确认订单、合作资源、天气和地点知识，给出最适合当前经营目标的产品方向；只用真实可售数据。如果没有可用组合，请说明具体原因和需要补充的数据。'

async function autoStart(directive = '', expected?: { targetDate: string; roomType: string; resourceNames: string[] }) {
  submitting.value = true
  processingMessage.value = '正在结合房态、近15日成交、合作资源与经营分析关注点生成方案方向…'
  try {
    const conversationId = await ensureConversation()
    const requestBrief = directive ? `${AUTO_BRIEF}\n\n经营建议优先方向：${directive}` : AUTO_BRIEF
    const response = await hotelApi.advisor(Number(conversationId), requestBrief, true)
    const data = response.data
    const nextAdvisor = data.advisor as AnyRecord | undefined
    const nextPrimary = (nextAdvisor?.primary as AnyRecord) || null
    if (!nextPrimary?.target_date || !nextPrimary?.room_type) {
      const reason = String(nextAdvisor?.judgement?.text || nextAdvisor?.answer || '').trim()
      showToast(reason || 'AI暂未返回包含日期和房型的完整方案，请重新分析后再采用建议。')
      return false
    }
    if (expected) {
      const actualResources = ((nextPrimary.experiences || []) as AnyRecord[]).map((item) => String(item.name || '')).filter(Boolean)
      const mismatch = String(nextPrimary.target_date) !== expected.targetDate
        || displayValue(nextPrimary.room_type) !== expected.roomType
        || expected.resourceNames.some((name) => !actualResources.includes(name))
      if (mismatch) {
        showToast('当前可售房态或体验名额与建议不一致，已保留原方案；请重新分析后采用最新建议。')
        return false
      }
    }
    mergeConversation(data.conversation as AnyRecord)
    advisor.value = nextAdvisor || null
    adviceVariant.value = 0
    previousPrimary.value = nextPrimary
    targetInventoryKey.value = `${nextPrimary.target_date}|${nextPrimary.room_type}`
    selectedStage.value = 2
    advisorAnalysisSignature.value = analysisSignature()
    advisorLoadedThisVisit.value = true
    return true
  } catch (error) { showToast(errorMessage(error)); return false }
  finally { submitting.value = false }
}

let foldHoverTimer: ReturnType<typeof setTimeout> | undefined
function openFoldOnHover(event: MouseEvent) {
  const fold = event.currentTarget as HTMLDetailsElement
  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches || fold.open) return
  if (foldHoverTimer) clearTimeout(foldHoverTimer)
  foldHoverTimer = setTimeout(() => {
    if (!fold.open) {
      fold.dataset.hoverOpened = 'true'
      fold.open = true
    }
  }, 180)
}
function closeFoldOnHover(event: MouseEvent) {
  const fold = event.currentTarget as HTMLDetailsElement
  if (foldHoverTimer) clearTimeout(foldHoverTimer)
  foldHoverTimer = undefined
  if (fold.dataset.hoverOpened === 'true') {
    fold.open = false
    delete fold.dataset.hoverOpened
  }
}

onMounted(async () => {
  selectedStage.value = 1
  await load()
  // 房态、订单、资源、天气和知识库共同构成经营诊断依据；进入页面即并行采集。
  void Promise.allSettled(evidenceSections.map((section) => ensureEvidence(section)))
})
</script>

<template>
  <section class="ai-ops">
    <div v-toolbar class="head-actions">
      <span v-if="loadedAt" class="muted">数据更新 {{ loadedAt }}</span>
      <el-button size="small" plain :loading="submitting || loading" @click="refreshData">刷新经营数据</el-button>
      <el-button size="small" plain @click="historyOpen = true">操作历史<template v-if="operationLog.length">（{{ operationLog.length }}）</template></el-button>
    </div>
    <!-- ① 流程步骤 -->
    <nav class="stage-bar" aria-label="产品生成流程">
      <ol>
        <li v-for="s in stages" :key="s.id" :class="{ active: stageIndex === s.id, done: stageIndex > s.id, available: s.id <= availableStage }">
          <button type="button" :disabled="s.id > availableStage" @click="selectStage(s.id)">
            <i>{{ stageIndex > s.id ? '✓' : s.id }}</i>
            <div><b>{{ s.label }}</b></div>
          </button>
        </li>
      </ol>
    </nav>

    <!-- 处理中只在页面内提示：步骤条、经营数据与输入区保持可见可操作。 -->
    <div v-if="submitting" class="work-status" role="status">
      <span class="recompute-spinner" />
      <div>
        <b>{{ processingMessage }}</b>
        <small v-if="primarySpec">正在根据新条件重新计算，当前方案会保留到新结果返回；失败时不会清空已有方案。</small>
        <small v-else>读取过程中仍可查看经营数据、切换步骤或直接输入新的要求。</small>
      </div>
    </div>

    <!-- ② Step 1：经营概览、具体诊断与完整数据依据。 -->
    <section v-if="stageIndex === 1" class="operations-overview" aria-labelledby="operations-overview-title">
      <div class="operations-overview__head">
        <div>
          <span class="section-kicker">STAYSCAPE · HOTEL OPERATIONS</span>
          <h2 id="operations-overview-title">AI经营概览</h2>
          <p>{{ overviewConclusion }}</p>
        </div>
        <span class="operations-overview__progress" :class="{ 'is-loading': evidenceSettledCount < evidenceSections.length }">
          {{ evidenceSettledCount < evidenceSections.length ? `正在采集 ${evidenceReadyCount}/${evidenceSections.length} 类数据` : `已分析 ${evidenceReadyCount}/${evidenceSections.length} 类数据` }}
        </span>
      </div>
      <div class="operations-overview__grid">
        <article v-for="item in overviewCards" :key="item.key" class="operations-insight">
          <span class="operations-insight__label">{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.detail }}</small>
        </article>
      </div>
    </section>

    <div v-if="loadError" class="panel empty-state">经营数据暂时无法读取：{{ loadError }} <el-button type="primary" @click="load">重新加载</el-button></div>

    <!-- ③ 经营分析：数据、判断与产品影响留在各自证据页签中 -->
    <section v-if="stageIndex === 1" class="panel stage-panel stage-panel--analysis">
      <section class="operations-diagnosis" aria-labelledby="operations-diagnosis-title">
        <div class="operations-section-heading">
          <div><span class="section-kicker">WHY THIS DIRECTION</span><h2 id="operations-diagnosis-title">AI经营诊断</h2></div>
          <p>悬停、聚焦或点击卡片，查看完整判断与经营建议。</p>
        </div>
        <div ref="diagnosisGridRef" class="diagnosis-grid" aria-live="polite">
          <article v-for="item in diagnosisSteps" :key="item.key" tabindex="0" :aria-expanded="expandedDiagnosisKey === item.key" class="diagnosis-step" :class="[`is-${item.state}`, { 'diagnosis-step--conclusion': item.key === 'summary', 'is-open': expandedDiagnosisKey === item.key }]" @click="expandedDiagnosisKey = expandedDiagnosisKey === item.key ? '' : item.key" @keydown.enter.prevent="expandedDiagnosisKey = expandedDiagnosisKey === item.key ? '' : item.key">
            <header><h3>{{ item.title }}</h3><span class="diagnosis-state" :class="`diagnosis-state--${item.state}`">{{ diagnosisStateLabel(item) }}</span></header>
            <div class="diagnosis-step__discovery"><b class="diagnosis-step__label">发现</b><p>{{ item.result }}</p></div>
            <div class="diagnosis-step__details">
              <div><b class="diagnosis-step__label">经营影响</b><p class="diagnosis-step__impact">{{ item.impact }}</p></div>
              <small class="diagnosis-step__source">数据来源：{{ item.source }}</small>
            </div>
          </article>
        </div>
      </section>

      <section class="evidence-fold operations-evidence">
        <div class="evidence-tabs" role="tablist" aria-label="经营数据分类">
          <button type="button" role="tab" :aria-selected="panel === 'inventory'" :class="{ active: panel === 'inventory' }" @click="selectEvidence('inventory')">房态数据</button>
          <button type="button" role="tab" :aria-selected="panel === 'resources'" :class="{ active: panel === 'resources' }" @click="selectEvidence('resources')">合作资源</button>
          <button type="button" role="tab" :aria-selected="panel === 'orders'" :class="{ active: panel === 'orders' }" @click="selectEvidence('orders')">订单数据</button>
          <button type="button" role="tab" :aria-selected="panel === 'weather'" :class="{ active: panel === 'weather' }" @click="selectEvidence('weather')">天气预测</button>
          <button type="button" role="tab" :aria-selected="panel === 'knowledge'" :class="{ active: panel === 'knowledge' }" @click="selectEvidence('knowledge')">知识库</button>
        </div>
        <div v-if="panel && evidenceLoadingSections.includes(panel)" class="evidence-loading">正在读取此分类的数据…</div>
        <div v-else-if="panel && evidenceErrors[panel]" class="evidence-loading evidence-loading--error">
          {{ evidenceErrors[panel] }} <el-button link type="primary" @click="retryEvidence">重试</el-button>
        </div>

        <div v-if="panel === 'inventory' && evidenceLoaded.includes('inventory')" class="evidence-body">
          <div class="chip-row">
            <span>未来 {{ pressure.window_days ?? 17 }} 天累计可售房间 {{ roomEvidenceTotal }} 间</span>
            <span>{{ roomEvidenceDateCount }} 个日期 · {{ roomEvidenceTypeCount }} 种房型</span>
            <span v-if="focusRoom">待售货值较高 {{ displayValue(focusRoom.room_type, '重点房型') }} {{ focusRoom.remaining }} 间（{{ focusRoom.target_date }}）</span>
            <span>余量状态按当前房态分布比较，不代表入住率预测</span>
          </div>
          <div class="evidence-controls">
            <label>筛选日期 <input v-model="evidenceDateFilters.inventory" type="date" @change="resetEvidencePage('inventory')"></label>
            <button v-if="evidenceDateFilters.inventory" type="button" @click="clearEvidenceDate('inventory')">清除</button>
            <span>当前 {{ filteredRoomRows.length }} 条房态</span>
          </div>
          <table v-if="roomEvidenceRows.length" class="reply-table reply-table--inventory">
            <thead><tr><th>日期</th><th>房型</th><th>当前余量</th><th>参考价</th><th>适合人数</th><th>余量状态</th></tr></thead>
            <tbody><tr v-for="row in evidencePageRows(filteredRoomRows, 'inventory')" :key="row.id"><td>{{ row.available_date }}</td><td>{{ displayValue(row.room_type, '未命名房型') }}</td><td>{{ row.available_count }} 间</td><td>¥{{ row.normal_price }}</td><td>{{ row.max_guests }} 人</td><td><span class="table-state" :class="`table-state--${inventoryAvailabilityState(row).tone}`">{{ inventoryAvailabilityState(row).label }}</span></td></tr><tr v-if="!filteredRoomRows.length"><td colspan="6" class="muted">该日期没有房态记录。</td></tr></tbody>
          </table>
          <div v-if="filteredRoomRows.length > evidencePageSize" class="evidence-pagination"><button type="button" :disabled="(evidencePages.inventory || 1) <= 1" @click="changeEvidencePage(filteredRoomRows, 'inventory', -1)">上一页</button><span>第 {{ evidencePages.inventory || 1 }} / {{ evidencePageCount(filteredRoomRows) }} 页</span><button type="button" :disabled="(evidencePages.inventory || 1) >= evidencePageCount(filteredRoomRows)" @click="changeEvidencePage(filteredRoomRows, 'inventory', 1)">下一页</button></div>
          <div class="evidence-analysis"><b>分析与产品影响</b><p>房态记录提供日期、房型、可售房间数、参考价和最多入住人数。产品方案会根据目标入住日期，核对房间余量与同日体验名额，确定可售套数。</p><small>数据来源：酒店逐日客房库存记录</small></div>
        </div>

        <div v-if="panel === 'resources' && evidenceLoaded.includes('resources')" class="evidence-body">
          <div class="chip-row"><span>合作资源 {{ sellableResourceEvidenceRows.length }} 条可售组包记录 / 共 {{ resourceEvidenceRows.length }} 条</span><span>酒店服务 {{ sellableServiceEvidenceRows.length }} 条可用记录 / 共 {{ serviceEvidenceRows.length }} 条</span><span>表格保留停用、售罄和未开放组包记录</span></div>
          <div class="evidence-controls">
            <label>筛选日期 <input v-model="evidenceDateFilters.resources" type="date" @change="resetEvidencePage('resources')"></label>
            <button v-if="evidenceDateFilters.resources" type="button" @click="clearEvidenceDate('resources')">清除</button>
            <span>体验 {{ filteredResourceRows.length }} 条 · 酒店服务 {{ filteredServiceRows.length }} 条</span>
          </div>
          <table v-if="resourceEvidenceRows.length" class="reply-table reply-table--resources">
            <thead><tr><th>日期</th><th>合作资源</th><th>库存 / 结算价</th><th>适配客群</th><th>关联产品</th><th>近15日成交</th></tr></thead>
            <tbody><tr v-for="row in evidencePageRows(filteredResourceRows, 'resources')" :key="row.id"><td>{{ row.available_date }}</td><td><b>{{ row.name }}</b><span class="table-state" :class="`table-state--${statusTone(resourceAvailabilityLabel(row))}`">{{ resourceAvailabilityLabel(row) }}</span><small class="table-subline">{{ row.merchant_name || row.category }} · {{ row.indoor ? '室内' : '户外' }} · {{ row.address || '地址未登记' }}</small></td><td>{{ row.remaining_capacity }} 份 · ¥{{ row.settlement_price }}</td><td>{{ crowdListLabel(row.suitable_crowds) }}</td><td>{{ row.product_count }} 个</td><td>{{ row.recent_confirmed_orders }} 单</td></tr><tr v-if="!filteredResourceRows.length"><td colspan="6" class="muted">没有符合日期的合作资源。</td></tr></tbody>
          </table>
          <div v-if="filteredResourceRows.length > evidencePageSize" class="evidence-pagination"><button type="button" :disabled="(evidencePages.resources || 1) <= 1" @click="changeEvidencePage(filteredResourceRows, 'resources', -1)">上一页</button><span>合作资源第 {{ evidencePages.resources || 1 }} / {{ evidencePageCount(filteredResourceRows) }} 页</span><button type="button" :disabled="(evidencePages.resources || 1) >= evidencePageCount(filteredResourceRows)" @click="changeEvidencePage(filteredResourceRows, 'resources', 1)">下一页</button></div>
          <h4 v-if="serviceEvidenceRows.length" class="evidence-subheading">酒店服务</h4>
          <table v-if="serviceEvidenceRows.length" class="reply-table reply-table--services"><thead><tr><th>日期</th><th>酒店服务</th><th>余量 / 成本</th><th>适用客群</th></tr></thead><tbody><tr v-for="row in evidencePageRows(filteredServiceRows, 'services')" :key="row.id"><td>{{ row.available_date }}</td><td><b>{{ row.name }}</b> <span class="table-state" :class="`table-state--${statusTone(serviceAvailabilityLabel(row))}`">{{ serviceAvailabilityLabel(row) }}</span></td><td>{{ row.available_quantity }} 份 · ¥{{ row.unit_cost }}</td><td>{{ crowdListLabel(row.suitable_crowds) }}</td></tr><tr v-if="!filteredServiceRows.length"><td colspan="4" class="muted">没有符合日期的酒店服务记录。</td></tr></tbody></table>
          <div v-if="filteredServiceRows.length > evidencePageSize" class="evidence-pagination"><button type="button" :disabled="(evidencePages.services || 1) <= 1" @click="changeEvidencePage(filteredServiceRows, 'services', -1)">上一页</button><span>酒店服务第 {{ evidencePages.services || 1 }} / {{ evidencePageCount(filteredServiceRows) }} 页</span><button type="button" :disabled="(evidencePages.services || 1) >= evidencePageCount(filteredServiceRows)" @click="changeEvidencePage(filteredServiceRows, 'services', 1)">下一页</button></div>
          <p v-if="!resourceEvidenceRows.length && !serviceEvidenceRows.length" class="muted">未来15天没有合作资源或酒店服务记录。</p>
          <div class="evidence-analysis"><b>分析与产品影响</b><p>同日名额决定体验可以组合的产品套数；可售、开放组包且成本有记录的资源才会进入推荐。近15日成交关联较高的体验可优先试投；关联较少的体验先完善介绍、适配客群和日期，再做小批量推广。酒店服务可用于补足住宿权益，生成时也会按对应日期余量和成本复核。</p><small>数据来源：合作资源、酒店服务、产品组成及确认订单记录</small></div>
        </div>

        <div v-if="panel === 'orders' && evidenceLoaded.includes('orders')" class="evidence-body">
          <div class="chip-row">
            <span>近 15 天已确认 {{ recentOrderSummary.confirmed_count ?? recentConfirmedRows.length }} 单</span>
            <span>成交 ¥{{ recentConfirmedRevenue }}</span>
            <span>订单最多客群 {{ crowdLabel(recentOrderSummary.top_crowds?.[0]?.target_crowd) || '暂无' }}</span>
            <span>平均订单 ¥{{ recentOrderSummary.average_order_value ?? '—' }}</span>
          </div>
          <div class="evidence-split">
            <div class="evidence-table-block"><h4 class="evidence-table-title">近期成交产品（全部）</h4><table class="reply-table reply-table--order-products"><thead><tr><th>产品</th><th>确认单</th><th>成交金额</th></tr></thead><tbody><tr v-for="row in evidencePageRows(recentOrderSummary.top_products || [], 'ordersProducts')" :key="row.product_id"><td>{{ row.product_name }}<small v-if="row.included_experiences?.length" class="table-subline">套餐体验：{{ row.included_experiences.join('、') }}</small></td><td>{{ row.confirmed_orders }}</td><td>¥{{ row.revenue }}</td></tr><tr v-if="!recentOrderSummary.top_products?.length"><td colspan="3" class="muted">近15日暂无成交产品</td></tr></tbody></table><div v-if="(recentOrderSummary.top_products || []).length > evidencePageSize" class="evidence-pagination"><button type="button" :disabled="(evidencePages.ordersProducts || 1) <= 1" @click="changeEvidencePage(recentOrderSummary.top_products || [], 'ordersProducts', -1)">上一页</button><span>{{ evidencePages.ordersProducts || 1 }} / {{ evidencePageCount(recentOrderSummary.top_products || []) }}</span><button type="button" :disabled="(evidencePages.ordersProducts || 1) >= evidencePageCount(recentOrderSummary.top_products || [])" @click="changeEvidencePage(recentOrderSummary.top_products || [], 'ordersProducts', 1)">下一页</button></div></div>
            <div class="evidence-table-block"><h4 class="evidence-table-title">近期客群结构（全部）</h4><table class="reply-table reply-table--order-crowds"><thead><tr><th>客群</th><th>确认单</th><th>占比</th></tr></thead><tbody><tr v-for="row in evidencePageRows(recentOrderSummary.top_crowds || [], 'ordersCrowds')" :key="row.target_crowd"><td>{{ crowdLabel(row.target_crowd) }}</td><td>{{ row.confirmed_orders }}</td><td>{{ row.share }}%</td></tr><tr v-if="!recentOrderSummary.top_crowds?.length"><td colspan="3" class="muted">暂无足够成交样本判断客群</td></tr></tbody></table><div v-if="(recentOrderSummary.top_crowds || []).length > evidencePageSize" class="evidence-pagination"><button type="button" :disabled="(evidencePages.ordersCrowds || 1) <= 1" @click="changeEvidencePage(recentOrderSummary.top_crowds || [], 'ordersCrowds', -1)">上一页</button><span>{{ evidencePages.ordersCrowds || 1 }} / {{ evidencePageCount(recentOrderSummary.top_crowds || []) }}</span><button type="button" :disabled="(evidencePages.ordersCrowds || 1) >= evidencePageCount(recentOrderSummary.top_crowds || [])" @click="changeEvidencePage(recentOrderSummary.top_crowds || [], 'ordersCrowds', 1)">下一页</button></div></div>
          </div>
          <div class="evidence-controls">
            <label>筛选日期 <input v-model="evidenceDateFilters.orders" type="date" @change="resetEvidencePage('orders')"></label>
            <button v-if="evidenceDateFilters.orders" type="button" @click="clearEvidenceDate('orders')">清除</button>
            <span>全部 {{ filteredOrderRows.length }} 条订单记录</span>
          </div>
          <h4 v-if="allOrderRows.length" class="evidence-table-title">全部订单记录</h4>
          <table v-if="allOrderRows.length" class="reply-table reply-table--orders">
            <thead><tr><th>产品</th><th>类别</th><th>金额</th><th>日期</th><th>状态</th></tr></thead>
            <tbody><tr v-for="row in evidencePageRows(filteredOrderRows, 'orders')" :key="row.id"><td>{{ row.product_name }}</td><td>{{ categoryLabel(row.category) }}</td><td>¥{{ row.amount }}</td><td>{{ String(row.confirmed_at || row.created_at || '').slice(0, 10) }}</td><td><span class="table-state" :class="`table-state--${statusTone(row.status)}`">{{ statusLabel(row.status) }}</span></td></tr><tr v-if="!filteredOrderRows.length"><td colspan="5" class="muted">该日期没有订单记录。</td></tr></tbody>
          </table>
          <div v-if="filteredOrderRows.length > evidencePageSize" class="evidence-pagination"><button type="button" :disabled="(evidencePages.orders || 1) <= 1" @click="changeEvidencePage(filteredOrderRows, 'orders', -1)">上一页</button><span>第 {{ evidencePages.orders || 1 }} / {{ evidencePageCount(filteredOrderRows) }} 页</span><button type="button" :disabled="(evidencePages.orders || 1) >= evidencePageCount(filteredOrderRows)" @click="changeEvidencePage(filteredOrderRows, 'orders', 1)">下一页</button></div>
          <div v-if="!allOrderRows.length" class="muted">当前没有订单记录。</div>
          <div class="evidence-analysis"><b>分析与产品影响</b><p v-if="recentOrderSummary.confirmed_count">近15天成交较多的是{{ crowdRankText }}，可以优先推出面向主要客群的住宿加体验组合。工作日房态为{{ weekdayDatesText }}；有房周末为{{ weekendDatesText }}，其中家庭房可售日期为{{ familyRoomDates.filter((date) => [0, 6].includes(new Date(`${date}T00:00:00`).getDay())).slice(0, 5).map(displayDate).join('、') || '暂无' }}，这些日期适合安排亲子房与同日家庭体验。上述判断来自已确认订单和逐日可售房态，属于当前数据下的产品安排建议。</p><p v-else>近15日暂无确认成交，可先结合当前房态、可用体验和天气安排首批产品；后续有更多订单后，再调整客群与体验组合。</p><small>数据来源：游客确认订单、订单提交时价格快照、已售产品客群和产品组成记录；历史订单缺少价格快照时按当前产品价估算（{{ recentOrderSummary.estimated_amount_count ?? 0 }}笔）。</small></div>
        </div>

        <div v-if="panel === 'weather' && evidenceLoaded.includes('weather')" class="evidence-body">
          <div class="chip-row"><span>{{ weatherStatusText }}</span><span v-if="weatherEvidenceRows.find((row) => row.usable)">来源：{{ weatherEvidenceRows.find((row) => row.usable)?.source_name }}</span><span>天气用于体验适配，不作为生成硬性限制</span></div>
          <div class="evidence-controls">
            <label>筛选日期 <input v-model="evidenceDateFilters.weather" type="date" @change="resetEvidencePage('weather')"></label>
            <button v-if="evidenceDateFilters.weather" type="button" @click="clearEvidenceDate('weather')">清除</button>
            <span>未来15天 {{ filteredWeatherRows.length }} 条预报</span>
          </div>
          <table class="reply-table reply-table--weather"><thead><tr><th>日期</th><th>天气</th><th>温度</th><th>降雨概率</th><th>路线建议</th></tr></thead><tbody><tr v-for="row in evidencePageRows(filteredWeatherRows, 'weather')" :key="row.target_date"><td>{{ row.target_date }}</td><td><span class="table-state" :class="`table-state--${weatherScenarioTone(row)}`">{{ weatherScenarioLabel(row) }}</span></td><td>{{ row.temperature_min ?? '—' }}–{{ row.temperature_max ?? '—' }}℃</td><td>{{ row.precipitation_probability == null ? '—' : `${row.precipitation_probability}%` }}</td><td>{{ !row.usable ? '暂不用于确定天气判断' : row.scenario === 'RAIN' ? `优先室内${indoorResourceNames.slice(0, 2).join('、') || '体验'}，户外留替代安排` : row.scenario === 'SUNNY' ? `可优先安排${outdoorResourceNames.slice(0, 2).join('、') || '户外体验'}，注意防晒补水` : '室内外均可，结合路线距离安排' }}</td></tr><tr v-if="!filteredWeatherRows.length"><td colspan="5" class="muted">该日期没有预报记录。</td></tr></tbody></table>
          <div v-if="filteredWeatherRows.length > evidencePageSize" class="evidence-pagination"><button type="button" :disabled="(evidencePages.weather || 1) <= 1" @click="changeEvidencePage(filteredWeatherRows, 'weather', -1)">上一页</button><span>第 {{ evidencePages.weather || 1 }} / {{ evidencePageCount(filteredWeatherRows) }} 页</span><button type="button" :disabled="(evidencePages.weather || 1) >= evidencePageCount(filteredWeatherRows)" @click="changeEvidencePage(filteredWeatherRows, 'weather', 1)">下一页</button></div>
          <div class="evidence-analysis"><b>分析与产品影响</b><p>降雨日期为{{ rainyForecasts.map((row) => displayDate(row.target_date)).join('、') || '无' }}，优先安排当日有名额的室内资源；晴天日期为{{ sunnyForecasts.map((row) => displayDate(row.target_date)).join('、') || '无' }}，可将钱江新城步行、湖滨漫游等已有户外资源放在这些日期。室内体验{{ indoorResourceNames.join('、') || '暂未登记' }}可穿插在天气敏感行程中。日预报只覆盖未来15天，实际组包时会再次检查日期与资源名额。</p><small>数据来源：杭州逐日天气服务、合作资源室内外标签与日期库存</small></div>
        </div>

        <div v-if="panel === 'knowledge' && evidenceLoaded.includes('knowledge')" class="evidence-body">
          <div class="chip-row"><span>地点知识 {{ knowledgeTotal }} 条 · 当前已加载 {{ knowledgeRows.length }} 条</span><span>已核验 {{ verifiedKnowledgeRows.length }} 条</span><span>订单按已售套餐关联体验统计，地点热度无结构化关联</span></div>
          <div class="evidence-controls">
            <label>筛选核验日期 <input v-model="evidenceDateFilters.knowledge" type="date" @change="resetEvidencePage('knowledge')"></label>
            <button v-if="evidenceDateFilters.knowledge" type="button" @click="clearEvidenceDate('knowledge')">清除</button>
            <span>当前 {{ filteredKnowledgeRows.length }} 条地点记录</span>
          </div>
          <table class="reply-table reply-table--knowledge">
            <thead><tr><th>地点</th><th>适用信息</th><th>开放 / 预约</th><th>核验与来源</th></tr></thead>
            <tbody><tr v-for="row in evidencePageRows(filteredKnowledgeRows, 'knowledge')" :key="row.id || row.name"><td><b>{{ row.name }}</b><small class="table-subline">{{ row.address || row.area }}</small></td><td>{{ row.category_label || row.category }} · {{ crowdListLabel(row.suitable_crowds) }} · {{ row.weather_adaptations_label || row.weather_adaptations || '天气未标注' }}</td><td>{{ row.opening_hours || '开放时间未登记' }}<small class="table-subline">{{ row.reservation_notice || '无预约说明' }}</small></td><td><span class="table-state" :class="`table-state--${statusTone(row.verification_status === 'ACTIVE' ? '已核验' : row.verification_status === 'STALE' ? '信息待更新' : '需复核')}`">{{ row.verification_status === 'ACTIVE' ? '已核验' : row.verification_status === 'STALE' ? '信息待更新' : '需复核' }}</span><small class="table-subline">{{ row.source_name || '来源未登记' }} · {{ row.verified_at || row.source_updated_at || '无核验日期' }}</small></td></tr><tr v-if="!filteredKnowledgeRows.length"><td colspan="4" class="muted">该核验日期没有地点记录。</td></tr></tbody>
          </table>
          <div v-if="filteredKnowledgeRows.length > evidencePageSize" class="evidence-pagination"><button type="button" :disabled="(evidencePages.knowledge || 1) <= 1" @click="changeEvidencePage(filteredKnowledgeRows, 'knowledge', -1)">上一页</button><span>第 {{ evidencePages.knowledge || 1 }} / {{ evidencePageCount(filteredKnowledgeRows) }} 页</span><button type="button" :disabled="(evidencePages.knowledge || 1) >= evidencePageCount(filteredKnowledgeRows)" @click="changeEvidencePage(filteredKnowledgeRows, 'knowledge', 1)">下一页</button></div>
          <div class="evidence-analysis"><b>分析与产品影响</b><p>知识库记录的地点包含{{ knowledgeRows.slice(0, 8).map((row) => row.name).join('、') || '暂无地点样本' }}{{ knowledgeRows.length > 8 ? '等' : '' }}；已核验{{ verifiedKnowledgeRows.length }}条。{{ knowledgeReviewDueIn === null ? '部分记录没有复核周期，需按来源更新时间人工检查。' : knowledgeReviewDueIn === 0 ? '最近一批记录已到复核窗口，请优先核验开放时间和预约说明。' : `最近一条已核验记录将在${knowledgeReviewDueIn}天内进入复核窗口。` }}这些地点信息可补足地址、开放时间和天气适配说明；因为地点与订单没有结构化对应关系，不能判断最受欢迎或最不受欢迎地点。</p><small>数据来源：文旅知识库记录、来源链接与核验时间</small></div>
        </div>
      </section>

      <section class="operations-advice" aria-labelledby="operations-advice-title">
        <div class="operations-section-heading">
          <div><span class="section-kicker">NEXT BEST ACTION</span><h2 id="operations-advice-title">AI经营建议</h2></div>
          <span class="operations-advice__basis">{{ operatingAdvice.basis }}</span>
        </div>
        <div class="operations-advice__body">
          <div class="operations-advice__copy">
            <h3>{{ operatingAdvice.title }}</h3>
            <dl class="operations-advice__facts">
              <div><dt>当前发现</dt><dd>{{ operatingAdvice.finding }}</dd></div>
              <div><dt>建议动作</dt><dd>{{ operatingAdvice.action }}</dd></div>
              <div><dt>判断依据</dt><dd>{{ operatingAdvice.reason }}</dd></div>
            </dl>
          </div>
          <div class="operations-advice__actions">
            <el-button type="primary" :disabled="!evidenceReadyCount || submitting" :loading="submitting" @click="adoptOperatingAdvice">采用建议</el-button>
            <el-button plain :disabled="submitting" :loading="submitting" @click="reanalyzeOperations">重新分析</el-button>
          </div>
        </div>
      </section>
    </section>

    <!-- ③ Step 2：产品方案。方向比较 + 当前方案调整，满意后生成候选。 -->
    <section v-if="stageIndex === 2" class="panel stage-panel">
      <div class="stage-panel__head"><h2>推荐方向</h2></div>
      <div v-if="generationRoomOptions.length" class="date-room-picker">
        <div class="date-room-picker__label"><b>生成目标</b><span>先选日期，再选当日可售房型</span></div>
        <el-select id="generation-date" v-model="generationDate" class="workbench-select" filterable placeholder="选择日期" @change="changeGenerationInventory">
          <el-option v-for="date in generationDates" :key="date" :value="date" :label="date" />
        </el-select>
        <el-select id="generation-room-type" v-model="generationRoomType" class="workbench-select" filterable placeholder="选择房型" @change="changeGenerationInventory">
          <el-option v-for="room in generationRoomsForDate" :key="room.id" :value="room.room_type" :label="`${room.room_type} · 余 ${room.available_count} 间`" />
        </el-select>
      </div>
      <div v-if="loading" class="local-loading">正在读取房态、订单与合作资源…</div>

      <section v-if="changeNote && !submitting" class="change-note">
        <b>本轮调整</b>
        <ul v-if="changeDetails.length">
          <li v-for="item in changeDetails" :key="item.label">
            <strong>{{ item.label }}</strong>
            <div><del>{{ item.before }}</del><span>→</span><b>{{ item.after }}</b></div>
          </li>
        </ul>
        <p v-else>{{ changeNote }}</p>
      </section>

      <div v-if="plans.length" class="plan-grid">
        <article v-for="item in plans" :key="`${item.label}-${item.name}`" class="plan-card" :class="{ 'is-current': item.is_current, [planBadgeClass(item)]: true }">
          <header>
            <div class="plan-badges">
              <span v-if="item.is_ai_primary" class="plan-badge plan-badge--ai">AI主推</span>
              <span v-if="item.label !== 'AI主推' || item.is_current" class="plan-badge">{{ item.is_current ? '当前选择' : item.label }}</span>
            </div>
            <b>¥{{ item.estimated_price }}</b>
          </header>
          <h3>{{ planTitle(item) }}</h3>
          <p class="muted">{{ item.target_date }}（{{ item.weekday }}）<template v-if="item.window"> · {{ item.window }}</template><template v-if="item.indoor"> · 室内</template></p>
          <p class="plan-capacity-line">房型余量 <b>{{ item.remaining }} 间</b><span>·</span>最多可售 <b>{{ item.max_sellable }} 套</b></p>
          <p class="plan-fit-note" :class="{ caution: String(item.fit_label || '').startsWith('需核对'), negative: item.fit_label === '不建议优先' }"><b>{{ item.is_ai_primary ? '主推原因' : '备选特点' }}</b><span>{{ concisePlanReason(item) }}</span></p>
          <el-button v-if="!item.is_current" class="plan-card__select" size="small" plain :disabled="submitting" @click="ask(item.message)">切换为当前方案</el-button>
        </article>
      </div>
      <p v-else-if="!submitting" class="muted">{{ judgement.text || '当前没有可推荐的组合，可以调整日期、客群、体验或价格目标后继续。' }}</p>

      <div v-if="!plans.length && !primarySpec" class="empty-candidate">
        <h3>{{ submitting ? '正在读取房态、订单与合作资源…' : '还没有方案' }}</h3>
        <p>{{ judgement.text || '系统保留当前经营数据；你可以换日期、客群、体验或价格目标后重新计算。' }}</p>
        <div class="option-row">
          <button type="button" @click="ask('换一个日期')">换日期</button>
          <button type="button" @click="ask('换成两人同行')">换客群</button>
          <button type="button" @click="ask('换一个室内体验')">换体验</button>
          <button type="button" @click="ask('预算降低到 700 以内')">调整价格目标</button>
          <button type="button" :disabled="submitting" @click="ask('重新读取房态和合作资源，重新计算当前方案')">刷新资源并重算</button>
          <router-link class="ghost-link" to="/hotel/rooms">维护客房库存</router-link>
          <router-link class="ghost-link" to="/hotel/resources">维护合作资源</router-link>
        </div>
      </div>

      <!-- 当前选择直接展开在推荐方向容器内，避免重复一张“当前方案”大卡。 -->
      <div v-if="primarySpec" class="selected-plan-detail">
        <div class="selected-plan-detail__head">
          <div>
            <span class="section-kicker">当前选择</span>
            <h3>{{ planTitle(primarySpec) }}</h3>
            <p class="selected-plan-product-name">游客端名称：{{ primarySpec.product_name }}</p>
            <p class="muted">{{ primarySpec.target_date }}（{{ primarySpec.weekday }}） · {{ primarySpec.crowd_label }} · {{ primarySpec.room_type }}</p>
          </div>
        </div>
        <article class="decision-card" :class="{ 'is-busy': submitting, 'is-flash': cardFlash }">
          <div class="decision-card__top">
            <div class="decision-card__head">
              <p class="decision-card__include"><b>产品组成：</b>{{ primarySpec.room_type }} 1 晚<template v-for="exp in primarySpec.experiences" :key="exp.name"> · {{ exp.name }}<template v-if="exp.window">（{{ exp.window }}）</template></template><template v-for="service in (primarySpec.services || [])" :key="service.id || service.name"> · {{ service.name }} × {{ service.quantity || primarySpec.party_size }}</template></p>
              <p v-if="primarySpec.route_note" class="decision-card__route">路线调整：{{ primarySpec.route_note }}</p>
            </div>
          </div>

          <div class="figure-row">
            <span>建议售价 <b>¥{{ primarySpec.price }}</b></span>
            <span>可售 <b>{{ primarySpec.max_sellable }} 套</b></span>
            <span>毛利率 <b>{{ primarySpec.margin }}%</b></span>
            <span>预计单套利润 <b>¥{{ primarySpec.unit_profit ?? (Number(primarySpec.price || 0) - Number(primarySpec.cost || 0)).toFixed(2) }}</b></span>
          </div>

          <div v-if="budgetShortfall" class="budget-note">
            <p>当前条件下没有 ¥{{ budgetShortfall.requested }} 以内、且满足最低利润要求的组合，最低可售价为 ¥{{ budgetShortfall.lowest }}。</p>
            <div class="option-row"><button v-for="option in budgetShortfall.options" :key="option.label" type="button" @click="ask(option.message)">{{ option.label }}</button></div>
          </div>

          <div v-if="primarySpec.structure" class="product-structure">
            <div v-for="section in primarySpec.structure" :key="section.label" class="structure-row">
              <b>{{ section.label }}</b>
              <span v-for="item in section.items" :key="item.name">{{ item.name }}<template v-if="item.quantity"> × {{ item.quantity }}</template><template v-if="item.window"> · {{ item.window }}</template></span>
            </div>
          </div>

          <section v-if="primarySpec.itinerary_days?.length" class="advanced-fold itinerary-fold">
            <h4>完整行程与转场（{{ primarySpec.itinerary_days.length }} 天）</h4>
            <div class="itinerary-days">
            <article v-for="day in primarySpec.itinerary_days" :key="day.day_index" class="itinerary-day">
              <header><b>{{ day.label }} · {{ day.title }}</b><span>{{ day.date }}</span></header>
              <p class="itinerary-day__summary">{{ day.summary }}</p>
              <div v-for="(item, index) in day.items" :key="String(day.day_index) + '-' + String(index)" class="itinerary-entry">
                <time>{{ item.time || '时间待确认' }}</time>
                <div>
                  <template v-for="leg in [routeLegForStop(day.day_index, item.title)]" :key="`${day.day_index}-${item.title}-route`">
                    <div v-if="leg" class="route-leg-inline"><b>转场</b><span>{{ leg.from_stop }} → {{ leg.to_stop }} · {{ leg.distance_label || '交通机动' }}<template v-if="leg.minutes"> · 预留约 {{ leg.minutes }} 分钟</template></span><small>{{ leg.note }}</small></div>
                  </template>
                  <strong>{{ item.title }}</strong>
                  <span v-if="item.route_only" class="route-only-badge">路线建议 · 非套餐权益</span>
                  <p>{{ item.description }}</p>
                  <!-- 不再逐条折叠「路线详情」：地点、时长、区域直接一行显示，核验提示单独一行。 -->
                  <p v-if="item.address || item.duration_text || item.area" class="itinerary-entry__meta">
                    <span v-if="item.address">{{ item.address }}</span>
                    <span v-if="item.duration_text">{{ item.duration_text }}</span>
                    <span v-if="item.area">{{ item.area }}</span>
                  </p>
                  <p v-if="item.notes" class="itinerary-entry__verify" :class="{ 'itinerary-entry__verify--warning': item.schedule_conflict }">{{ item.notes }}</p>
                </div>
              </div>
              <template v-for="leg in [routeReturnLeg(day.day_index, day.items.length - 1, day.items.length)]" :key="`${day.day_index}-return-route`">
                <div v-if="leg" class="route-leg-inline route-leg-inline--return"><b>返程</b><span>{{ leg.from_stop }} → {{ leg.to_stop }} · {{ leg.distance_label || '交通机动' }}<template v-if="leg.minutes"> · 预留约 {{ leg.minutes }} 分钟</template></span><small>{{ leg.note }}</small></div>
              </template>
            </article>
            </div>
          </section>

          <section v-if="primarySpec.cost_breakdown?.length || primarySpec.blocks?.length" class="reason-fold decision-more">
            <h4>价格与收益</h4>
            <div class="key-evidence">
              <div><span>单位成本</span><b>¥{{ primarySpec.cost }}</b></div>
              <div><span>最低合法价</span><b>¥{{ primarySpec.floor_price }}</b></div>
              <div><span>建议售价</span><b>¥{{ primarySpec.price }}</b></div>
              <div><span>容量瓶颈</span><b>{{ primarySpec.bottleneck || '已通过' }}</b></div>
            </div>
            <div v-if="primarySpec.cost_breakdown?.length" class="calculation-list">
              <div v-for="item in primarySpec.cost_breakdown" :key="item.label"><span>{{ item.label }}</span><b>¥{{ item.value }}</b></div>
            </div>
            <p v-if="primarySpec.pricing_basis?.length" class="muted">定价依据：{{ primarySpec.pricing_basis.join('；') }}</p>
          </section>

          <div class="decision-card__actions">
            <el-button type="primary" :disabled="submitting || Boolean(budgetShortfall)" @click="generateFromPlan(primarySpec)">{{ primarySpec.product_id ? '继续优化当前产品' : '生成候选产品' }}</el-button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'resources' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'resources' ? '' : 'resources'">换资源</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'price' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'price' ? '' : 'price'">调价格</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'crowd' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'crowd' ? '' : 'crowd'">换客群</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'route' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'route' ? '' : 'route'">改路线</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'service' && resourceTab === 'experience' }" :disabled="submitting" @click="openResourceTab('experience')">增加体验 · {{ allExperienceCards.length }}</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'service' && resourceTab === 'hotel' }" :disabled="submitting" @click="openResourceTab('hotel')">酒店权益 · {{ availableHotelPerks.length }}</button>
          </div>

          <div v-if="activeAdjust === 'price'" class="adjust-panel">
            <div class="adjust-panel__head"><b>调整建议售价</b><span class="muted">当前 ¥{{ primarySpec.price }}，最低合法价 ¥{{ primarySpec.floor_price }}；改价会重新跑容量与利润校验</span></div>
            <div class="option-row"><button type="button" @click="ask(`价格按最低合法价 ${primarySpec.floor_price} 来`)">按最低合法价 ¥{{ primarySpec.floor_price }}</button><button type="button" @click="ask('价格降到 650 以内')">降到 650 以内</button><button type="button" @click="ask('价格降到 600 以内')">降到 600 以内</button></div>
            <div class="price-input"><input v-model="priceTarget" inputmode="numeric" placeholder="输入目标价，例如 620" /><el-button size="small" type="primary" :disabled="submitting" @click="applyPriceTarget">按这个价格重算</el-button></div>
          </div>

          <div v-if="activeAdjust === 'crowd'" class="adjust-panel"><div class="adjust-panel__head"><b>切换目标客群</b><span class="muted">仅修改目标客群，房型、体验与酒店权益保持不变；若原资源的客群标签不匹配，会明确提示核对</span></div><div class="option-row"><button v-for="item in crowdChoices" :key="item.label" type="button" @click="ask(item.message)">{{ item.label }}</button></div></div>

          <div v-if="activeAdjust === 'resources'" class="adjust-panel">
            <div class="adjust-panel__head"><b>替换当前合作资源</b><span class="muted">保持日期、房型和客群，只替换核心体验；绿色为优先推荐，黄色需要核对，换完会重新跑容量与利润校验。替换候选需同时符合当前日期、房型、客群和场次，因此可能少于可增加的体验。</span></div>
            <div v-if="resourceSwaps.length" class="alt-grid">
              <article v-for="item in resourceSwaps" :key="`swap-${item.name}`" class="alt-card resource-diagnosis-card" :class="recommendationClass(item)">
                <div class="resource-card__head">
                  <span class="section-kicker">{{ item.window || '按场次' }}<template v-if="item.fit_label"> · {{ item.fit_label }}</template></span>
                  <span class="recommendation-badge" :class="recommendationClass(item)">{{ recommendationLabel(item) }}</span>
                </div>
                <h3>{{ item.name }}</h3>
                <p class="muted">换后预估价 ¥{{ item.estimated_price }}<template v-if="item.price_delta && Number(item.price_delta) !== 0">（{{ Number(item.price_delta) > 0 ? '涨' : '降' }} ¥{{ Math.abs(Number(item.price_delta)).toFixed(2) }}）</template> · 可售 {{ item.sets }} 套 · 单人成本 ¥{{ item.settlement_price }}</p>
                <div class="alt-card__details"><p v-if="item.address" class="resource-fit-note">地点：{{ item.address }}</p><p v-if="item.fit_reason" class="resource-fit-note">{{ item.fit_reason }}</p></div>
                <el-button class="alt-card__action" size="small" plain @click="ask(`${primarySpec.target_date} 的 ${primarySpec.room_type} 换成 ${item.name}`)">换成这个体验</el-button>
              </article>
            </div>
            <p v-else class="muted">当前日期与房型下没有其它可用合作资源：可以到合作资源池为该日期补充资源并允许组包，或换一个日期再看。</p>
          </div>

          <div v-if="activeAdjust === 'route'" class="adjust-panel"><div class="adjust-panel__head"><b>选择路线调整方式</b><span class="muted">先选安排，再由 AI 按场次和天气重新校验。</span></div><div class="option-row"><button type="button" @click="ask('路线留出更多自由时间，晚上体验结束后直接回酒店')">留出自由时间</button><button type="button" @click="ask('优先室内路线，减少户外移动')">优先室内路线</button><button type="button" @click="ask('保持当前体验，只调整先后顺序')">只调先后顺序</button></div></div>

          <div v-if="activeAdjust === 'service'" class="adjust-panel resource-add-panel">
            <div class="adjust-panel__head"><b>{{ resourceTab === 'hotel' ? '酒店权益' : '增加体验' }}</b><span class="muted">{{ resourceTab === 'hotel' ? '与体验分开核算；已加入的酒店服务也会列出，可查看说明或取消。' : '体验需符合当前日期、可售名额与时间安排；已加入的项目保留在列表中，可以查看或取消。' }}</span></div>
            <template v-if="resourceTab === 'experience'">
              <p class="resource-list-note">当前方案中的体验和可追加体验都会显示。替换体验会保留其他已选项目；若候选场次与现有安排冲突，会在卡片详情中标出。</p>
              <div v-if="allExperienceCards.length" class="alt-grid">
                <article v-for="item in allExperienceCards" :key="'experience-' + (item.id || item.name)" class="alt-card resource-diagnosis-card" :class="[recommendationClass(item), { 'is-selected': item.is_selected }]">
                  <div class="resource-card__head"><span class="section-kicker">体验<template v-if="item.fit_label"> · {{ item.fit_label }}</template></span><span class="recommendation-badge" :class="recommendationClass(item)">{{ item.is_selected ? '已选' : recommendationLabel(item) }}</span></div>
                  <h3>{{ item.name }}</h3>
                  <p class="muted">{{ item.is_selected ? '当前方案已包含' : '可售 ' + (item.sets ?? item.remaining_capacity ?? '—') + ' 套' }}<template v-if="item.window"> · {{ item.window }}</template><template v-if="resourceDurationText(item)"> · {{ resourceDurationText(item) }}</template><template v-if="item.settlement_price !== undefined"> · 单人成本 ¥{{ item.settlement_price }}</template></p>
                  <div class="alt-card__details"><p class="resource-fit-note">{{ resourceScheduleAdvice(item) }}</p><p v-if="item.address" class="resource-fit-note">地点：{{ item.address }}</p><p v-if="item.fit_reason" class="resource-fit-note">{{ item.fit_reason }}</p></div>
                  <el-button class="alt-card__action" size="small" plain :disabled="item.is_selected ? selectedExperienceCards.length <= 1 : item.addable === false" @click="ask(item.is_selected ? '去掉体验：' + item.name : '增加体验：' + item.name)">{{ item.is_selected ? (selectedExperienceCards.length <= 1 ? '保留核心体验' : '取消选择') : item.addable === false ? '暂不可加入' : '增加这项体验' }}</el-button>
                </article>
              </div>
              <p v-else class="muted">当前日期没有可追加的组包体验。体验资源需在合作资源池维护对应日期、可售名额并开启组包。</p>
              <div v-if="itineraryOptionalPlaces.length" class="optional-route-list"><b>行程中的空闲时间可选地点</b><p>这些地点来自当前方案行程与知识库建议，不计入套餐；新增体验时可优先参考已有空档，也可以由游客自行选择。</p><div v-for="place in itineraryOptionalPlaces" :key="place.title + place.day_label" class="optional-route-item"><span>{{ place.day_label }} · {{ place.title }} <small>{{ place.time }}<template v-if="place.duration_text"> · {{ place.duration_text }}</template></small></span><small>{{ place.address || place.area || '地点详情见行程' }} · 空闲时间可选</small></div></div>
            </template>
            <template v-else>
              <p class="resource-list-note">酒店权益与体验分开核算。已加入的早餐、行李寄存等服务也会显示；取消或增加后，系统会重新核对容量和成本。</p>
              <div v-if="availableHotelPerks.length" class="alt-grid">
                <article v-for="item in availableHotelPerks" :key="'hotel-perk-' + (item.id || item.name)" class="alt-card resource-diagnosis-card" :class="[recommendationClass(item), { 'is-selected': item.is_selected }]">
                  <div class="resource-card__head"><span class="section-kicker">酒店权益<template v-if="item.fit_label"> · {{ item.fit_label }}</template></span><span class="recommendation-badge" :class="recommendationClass(item)">{{ item.is_selected ? '已选' : recommendationLabel(item) }}</span></div>
                  <h3>{{ item.name }}</h3>
                  <p class="muted">{{ item.is_selected ? '当前方案已包含' : '可售 ' + (item.sets ?? item.available_quantity ?? '—') + ' 套' }}<template v-if="item.window"> · {{ item.window }}</template><template v-if="item.unit_cost !== undefined"> · 单人成本 ¥{{ item.unit_cost }}</template></p>
                  <div class="alt-card__details"><p class="resource-fit-note">{{ item.fit_reason || '酒店内服务可与入住和周边体验衔接。' }}</p><p v-if="item.address" class="resource-fit-note">地点：{{ item.address }}</p></div>
                  <el-button class="alt-card__action" size="small" plain :disabled="!item.is_selected && item.addable === false" @click="ask(item.is_selected ? '移除酒店权益：' + item.name : '增加酒店权益：' + item.name)">{{ item.is_selected ? '取消选择' : item.addable === false ? '暂不可加入' : '增加这项权益' }}</el-button>
                </article>
              </div>
              <p v-else class="muted">当前日期没有已启用且有余量的酒店权益。到酒店服务中为该日期配置权益后，可在这里与套餐一起核算。</p>
            </template>
          </div>

          <section class="reason-fold reason-fold--open">
            <h4>推荐依据与风险</h4>
            <div class="detail-tabs"><button type="button" :class="{ active: detailTab === 'basis' }" @click="detailTab = 'basis'">经营价值</button><button type="button" :class="{ active: detailTab === 'value' }" @click="detailTab = 'value'">收益与容量</button><button type="button" :class="{ active: detailTab === 'risk' }" @click="detailTab = 'risk'">风险与限制</button><button type="button" :class="{ active: detailTab === 'compare' }" @click="detailTab = 'compare'">方案比较</button></div>
            <div class="detail-body"><template v-if="detailTab === 'basis'"><p v-for="item in (primarySpec.reason_sections || [])" :key="item.label"><b>{{ item.label }}：</b>{{ item.text }}</p><p v-if="!primarySpec.reason_sections?.length">{{ logicByTitle['推荐逻辑'] || '按当前房态、近期成交、合作体验和地点知识综合判断。' }}</p></template><template v-else-if="detailTab === 'value'"><p>{{ logicByTitle['酒店经营价值'] || '按建议售价、单位成本和最大可售量计算收益。' }}</p></template><template v-else-if="detailTab === 'risk'"><p>{{ logicByTitle['风险与约束'] || '容量、场次与天气变化会在生成候选时再次复核。' }}</p></template><template v-else><p>{{ primarySpec.not_chosen || '本轮没有其它更高优先级的组合。' }}</p></template></div>
          </section>
        </article>
      </div>
    </section>

    <!-- ④ Step 3：预览与发布。候选由产品方案生成后直接进入这里确认与发布。 -->
    <section v-if="stageIndex === 3" class="panel stage-panel">
      <div class="stage-panel__head">
        <h2>游客端预览与发布</h2>
        <span class="muted">产品文案、资源与价格已在上一步确认</span>
      </div>
      <p v-if="primarySpec" class="source-plan">来源方案：{{ primarySpec.product_name }} · {{ primarySpec.room_type }} × {{ primaryExperience?.name || '当前体验' }} · ¥{{ primarySpec.price }}</p>
      <div v-if="!candidateCards.length && resolvedCandidateCount" class="panel empty-state">本轮产品已完成确认，可前往产品库继续制作营销内容。</div>
      <p v-if="!candidateCards.length && !resolvedCandidateCount" class="muted">还没有候选产品：回到「产品方案」调整好方向后点击「生成候选产品」，这里会直接给出预览、文案与发布入口。</p>
      <div class="candidate-grid">
        <article v-for="card in candidateCards" :key="card.key" class="candidate-card">
          <div class="candidate-card__body">
            <header>
              <h3>{{ card.name }}</h3>
              <b>¥{{ card.price }}</b>
            </header>
            <p class="muted">{{ card.date }} · {{ card.crowd_label }} · {{ card.party }} 人<template v-if="card.quantity !== ''"> · 可售 {{ card.quantity }} 套</template></p>
            <div class="badge-row">
              <span>✓ 库存通过</span>
              <span>✓ 资源通过</span>
              <span>✓ 利润通过</span>
            </div>
            <div class="candidate-card__actions">
              <el-button size="small" type="primary" @click="confirm(card.raw, 'PUBLISH')">确认并发布</el-button>
              <el-button size="small" plain @click="confirm(card.raw, 'DRAFT')">保存为草稿</el-button>
              <el-button size="small" plain @click="previewCardKey === card.key ? previewCardKey = '' : previewCardKey = String(card.key)">{{ previewCardKey === card.key ? '收起预览' : '预览游客端' }}</el-button>
              <el-button size="small" plain @click="continueEditing(card)">继续调整此候选</el-button>
              <el-button size="small" plain @click="editVisitorCopy(card)">{{ Number(copyDraft?.id) === Number(card.product_id) ? '收起文案编辑' : '微调游客文案' }}</el-button>
            </div>
            <iframe v-if="previewCardKey === card.key" class="visitor-preview-frame" :src="visitorPreviewUrl(card)" title="游客端商品完整预览" loading="lazy" scrolling="auto" @load="resizeVisitorPreview" />
            <details class="batch-apply-fold" @mouseenter="openFoldOnHover" @mouseleave="closeFoldOnHover">
              <summary>批量应用到其他日期与房型</summary>
              <p class="muted">只创建房间余量、入住人数和同名资源都满足条件的草稿；不满足的目标会列出原因。</p>
              <el-select v-model="batchRoomIds" multiple filterable collapse-tags collapse-tags-tooltip placeholder="选择日期与房型" class="batch-room-select">
                <el-option v-for="room in batchRoomOptions" :key="room.id" :value="Number(room.id)" :label="`${room.available_date} · ${room.room_type} · 余 ${room.available_count} 间`" />
              </el-select>
              <el-button size="small" type="primary" :loading="batchApplying" @click="applyBatch(card)">生成批量草稿</el-button>
              <div v-if="batchResult" class="batch-result">
                <p v-if="batchResult.created_count">已创建 {{ batchResult.created_count }} 个草稿：{{ batchCreatedText(batchResult) }}</p>
                <p v-for="item in batchResult.skipped" :key="`${item.target_date}-${item.room_inventory_id || item.room_type}`">未生成 {{ item.target_date }} {{ item.room_type || '' }}：{{ item.reason }}</p>
              </div>
            </details>
            <section v-if="copyDraft && Number(copyDraft.id) === Number(card.product_id)" class="copy-editor">
              <header><b>游客端文案微调</b><span>保存后直接更新上方预览</span></header>
              <article v-for="field in copyFields" :key="field.key" class="copy-field">
                <label>{{ field.label }}</label>
                <el-input v-model="copyDraft.product[field.key]" :type="field.multiline ? 'textarea' : 'text'" :rows="field.multiline ? 3 : 1" />
                <el-button size="small" plain :loading="copyRewriting" @click="rewriteMainCopy(field.key)">AI生成替换文字</el-button>
              </article>
              <details class="copy-subsection" @mouseenter="openFoldOnHover" @mouseleave="closeFoldOnHover"><summary>体验名称与介绍</summary>
                <article v-for="resource in copyDraft.resources" :key="`${resource.resource_type}:${resource.resource_id}`" class="copy-field">
                  <label>体验名称 · {{ resource.address || '酒店地址' }}</label>
                  <el-input v-model="resource.resource_name" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteResourceName(resource)">AI生成替换文字</el-button>
                  <label>体验介绍</label>
                  <el-input v-model="resource.description" type="textarea" :rows="2" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteResourceCopy(resource)">AI生成替换文字</el-button>
                </article>
              </details>
              <details v-if="copyDraft.assets?.length" class="copy-subsection" @mouseenter="openFoldOnHover" @mouseleave="closeFoldOnHover"><summary>营销素材</summary>
                <article v-for="asset in copyDraft.assets" :key="asset.asset_type" class="copy-field">
                  <label>{{ asset.platform || asset.asset_type }} · 标题</label>
                  <el-input v-model="asset.title" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteAssetCopy(asset, 'marketing_asset_title')">AI生成替换文字</el-button>
                  <label>正文</label>
                  <el-input v-model="asset.content" type="textarea" :rows="3" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteAssetCopy(asset, 'marketing_asset_content')">AI生成替换文字</el-button>
                </article>
              </details>
              <details v-if="copyDraft.details" class="copy-subsection" @mouseenter="openFoldOnHover" @mouseleave="closeFoldOnHover"><summary>商品详情文案</summary>
                <article v-for="(text, index) in copyDraft.details.intro" :key="`intro-${index}`" class="copy-field">
                  <label>商品详情介绍</label>
                  <el-input v-model="copyDraft.details.intro[index]" type="textarea" :rows="2" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteDetailCopy(copyDraft.details.intro, String(index), '商品介绍')">AI生成替换文字</el-button>
                </article>
                <article v-for="(item, index) in copyDraft.details.experience_details" :key="`detail-${index}`" class="copy-field">
                  <label>{{ item.name }} · 体验亮点</label>
                  <el-input v-model="item.feature" type="textarea" :rows="2" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteDetailCopy(item, 'feature', `${item.name}体验亮点`)">AI生成替换文字</el-button>
                  <label>到场提示</label>
                  <el-input v-model="item.tips" type="textarea" :rows="2" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteDetailCopy(item, 'tips', `${item.name}到场提示`)">AI生成替换文字</el-button>
                </article>
                <article v-for="(text, index) in copyDraft.details.spend_notes" :key="`spend-${index}`" class="copy-field">
                  <label>费用说明</label>
                  <el-input v-model="copyDraft.details.spend_notes[index]" type="textarea" :rows="2" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteDetailCopy(copyDraft.details.spend_notes, String(index), '费用说明')">AI生成替换文字</el-button>
                </article>
                <article v-for="(text, index) in copyDraft.details.tips" :key="`tip-${index}`" class="copy-field">
                  <label>出行提示</label>
                  <el-input v-model="copyDraft.details.tips[index]" type="textarea" :rows="2" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteDetailCopy(copyDraft.details.tips, String(index), '出行提示')">AI生成替换文字</el-button>
                </article>
              </details>
              <details class="copy-subsection" @mouseenter="openFoldOnHover" @mouseleave="closeFoldOnHover"><summary>每日行程文案</summary>
                <article v-for="day in copyDraft.days" :key="day.day_index" class="copy-day">
                  <b>{{ day.label }} · {{ day.date }}</b>
                  <div class="copy-field">
                    <label>当天标题</label>
                    <el-input v-model="day.title" />
                    <el-button size="small" plain :loading="copyRewriting" @click="rewriteDayCopy(day, 'itinerary_title')">AI替换标题</el-button>
                    <label>当日概述</label>
                    <el-input v-model="day.summary" type="textarea" :rows="2" />
                    <el-button size="small" plain :loading="copyRewriting" @click="rewriteDayCopy(day, 'itinerary_summary')">AI替换概述</el-button>
                  </div>
                  <div v-for="item in day.items" :key="`${item.time}-${item.title}`" class="copy-field">
                    <label>{{ item.time }} · {{ item.address || '酒店地址' }}</label>
                    <el-input v-model="item.title" />
                    <el-button size="small" plain :loading="copyRewriting" @click="rewriteItineraryCopy(item, 'itinerary_title')">AI替换标题</el-button>
                    <el-input v-model="item.description" type="textarea" :rows="2" />
                    <el-button size="small" plain :loading="copyRewriting" @click="rewriteItineraryCopy(item, 'itinerary_description')">AI替换说明</el-button>
                  </div>
                </article>
              </details>
              <p class="muted">文字调整只影响游客端内容，不修改房态、资源、地址、价格或产品包含权益。</p>
              <div class="copy-editor__actions"><el-button type="primary" :loading="copySaving" @click="saveVisitorCopy">保存并刷新预览</el-button><el-button plain @click="copyDraft = null">取消</el-button></div>
            </section>
            <details class="reason-fold" @mouseenter="openFoldOnHover" @mouseleave="closeFoldOnHover">
              <summary>查看推荐依据</summary>
              <ul class="reason-list">
                <li v-for="row in candidateEvidenceRows(card.raw)" :key="row.label"><b>{{ row.label }}：</b>{{ row.text }}</li>
              </ul>
            </details>
          </div>
        </article>
      </div>
    </section>

    <!-- 微调记录：说清改的是哪一层、第几版，并支持撤销 -->
    <section v-if="refinementHistory.length || refinements.length" class="panel stage-panel">
      <div class="stage-panel__head">
        <h2>微调记录</h2>
        <span class="muted">内容层只改文案；权益层每次都会重新校验容量、成本与利润，可撤销</span>
      </div>
      <template v-if="refinementHistory.length">
        <div v-for="item in refinementHistory" :key="`h-${item.id}`" class="refine-row">
          <div class="refine-row__head">
            <strong class="refine-row__instruction">{{ item.instruction || '方案调整' }}</strong>
            <span class="refine-meta">
              <em v-if="item.layer_label">{{ item.layer_label }}</em>
              <em>v{{ item.version }}</em>
              <em v-if="item.created_at">{{ String(item.created_at).slice(0, 16).replace('T', ' ') }}</em>
            </span>
          </div>
          <p v-if="item.message" class="muted">{{ item.message }}</p>
          <table v-if="item.changes?.length" class="reply-table">
            <thead><tr><th>字段</th><th>修改前</th><th>修改后</th></tr></thead>
            <tbody><tr v-for="row in item.changes" :key="row.field"><td>{{ row.label }}</td><td class="muted">{{ row.before }}</td><td>{{ row.after }}</td></tr></tbody>
          </table>
          <el-button size="small" plain :loading="historyLoading" @click="rollbackRefinement(item)">撤销这次调整</el-button>
        </div>
      </template>
      <template v-else>
        <div v-for="(item, index) in refinements" :key="`l-${index}`" class="refine-row">
          <div class="refine-row__head">
            <strong class="refine-row__instruction">{{ item.instruction || '方案调整' }}</strong>
            <span class="refine-meta">
              <em v-if="item.layer_label">{{ item.layer_label }}</em>
              <em v-if="item.version">v{{ item.version }}</em>
            </span>
          </div>
          <p v-if="item.message" class="muted">{{ item.message }}</p>
          <table v-if="item.changes?.length" class="reply-table">
            <thead><tr><th>字段</th><th>修改前</th><th>修改后</th></tr></thead>
            <tbody><tr v-for="row in item.changes" :key="row.field"><td>{{ row.label }}</td><td class="muted">{{ row.before }}</td><td>{{ row.after }}</td></tr></tbody>
          </table>
          <p v-else class="muted">本轮未产生字段变化。</p>
        </div>
      </template>
    </section>

    <!-- ⑤ 无论有没有方案，输入区都固定可用：有方案是调整，没有方案就是规划。 -->
    <form v-if="stageIndex !== 1" class="composer" @submit.prevent="submit()">
      <div class="composer__context">
        <span v-if="stageIndex === 1 && !primarySpec" class="context-chip">补充经营关注点（选填）· 也可直接查看上方诊断与建议</span>
        <span v-else-if="editingProduct" class="context-chip is-editing">正在微调：{{ editingProduct.name }} · 只改这个已生成产品（改权益会重新校验容量与价格）</span>
        <span v-else-if="primarySpec" class="context-chip is-editing">正在调整方案：{{ currentObjectLabel }} · 会重新计算价格、容量与行程</span>
        <span v-else class="context-chip is-editing">正在规划新方案 · 说明日期、客群或预算即可</span>
        <button v-if="editingProduct" type="button" class="ghost-link" @click="stopEditing">改为重算方案</button>
        <button v-if="advisor || operationLog.length || analysisMessages.length" type="button" class="ghost-link" @click="clearConversation">重新开始</button>
      </div>
      <div class="composer__quick">
        <button v-for="cmd in (stageIndex === 1 && !primarySpec ? operatingQuestions : quickCommands)" :key="cmd" type="button" @click="stageIndex === 1 && !primarySpec ? askOperatingQuestion(cmd) : ask(cmd)">{{ cmd }}</button>
      </div>
      <div class="composer__main">
        <textarea v-model="brief" rows="1" :placeholder="stageIndex === 1 && !primarySpec ? '补充经营问题或目标，例如：优先消化周中库存，或避免安排雨天户外体验' : '例如：价格控制在 700 以内；换成更适合两人的体验；把下午路线改轻松一些'" @input="growInput" @keydown.enter.exact.prevent="submit()" />
        <button type="submit" :disabled="!brief.trim() || submitting">{{ stageIndex === 1 && !primarySpec ? '纳入经营分析' : primarySpec ? '调整方案' : '规划方案' }}</button>
      </div>
    </form>
  </section>

  <!-- 操作历史：只记录「指令 → 变化」，不保留聊天式对话 -->
  <el-drawer v-model="historyOpen" title="操作历史" size="380px">
    <div v-if="operationGroups.length" class="log-list">
      <div v-for="(group, groupIndex) in operationGroups" :key="`log-group-${groupIndex}`" class="log-group">
        <div class="log-group__head"><b>{{ group.title }}</b><span>{{ group.items[group.items.length - 1]?.at }}<template v-if="group.items.length > 1"> · {{ group.items.length }} 步</template></span></div>
        <div v-for="(item, index) in group.items" :key="`log-${groupIndex}-${index}`" class="log-item">
          <span class="log-time">{{ item.at }}</span>
          <b>{{ item.title || operationTitle(item.instruction) }}</b>
          <small v-if="item.instruction">{{ item.instruction }}</small>
          <div v-if="item.changes?.length" class="log-diffs"><span v-for="change in item.changes" :key="change.label"><b>{{ change.label }}</b> <del>{{ change.before }}</del> → {{ change.after }}</span></div>
          <p v-else>{{ item.change || '已按这条指令重算当前方案。' }}</p>
        </div>
      </div>
    </div>
    <p v-else class="muted">还没有操作记录。用输入框或按钮调整一次方案后，这里会显示「指令 → 变化」。</p>
  </el-drawer>
</template>

<style scoped src="./aiOperations.css"></style>
