<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { showToast } from 'vant'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import { validationChangeNote } from './productGenerationState.mjs'

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
const submitting = ref(false)
const processingMessage = ref('正在读取经营数据…')
const loadedAt = ref('')
const selectedStage = ref<number | null>(null)
// 只允许一个「经营证据」分类展开，避免页面被多块原始数据同时撑长。
const panel = ref<'' | 'inventory' | 'resources' | 'orders' | 'weather' | 'knowledge' | 'trace'>('')
const evidenceFold = ref<HTMLDetailsElement | null>(null)
// 本次会话真正生成出来的候选（用于「候选确认」阶段，不再展示历史待确认队列）。
const sessionProposalIds = ref<number[]>([])
const resolvedCandidateCount = ref(0)
// 主方案下方「调整这个方案」的展开状态：替代资源默认不展示。
const activeAdjust = ref<'' | 'resources' | 'price' | 'crowd' | 'route' | 'service'>('')
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
const signals = computed(() => Array.isArray(overview.value.operations_insights?.recommendation_signals) ? overview.value.operations_insights.recommendation_signals : [])
const pressure = computed<AnyRecord>(() => (overview.value.inventory_pressure as AnyRecord) || {})
const focusRoom = computed<AnyRecord | null>(() => (pressure.value.focus_room as AnyRecord) || null)
const insights = computed<AnyRecord>(() => (overview.value.operations_insights as AnyRecord) || {})
const availableServices = computed<AnyRecord[]>(() => {
  const services = (primarySpec.value?.service_options || insights.value.available_services || []) as AnyRecord[]
  return services.filter((item) => Number(item.available_quantity ?? item.availableQuantity ?? 0) > 0)
})
const availableAddResources = computed<AnyRecord[]>(() => [
  ...((primarySpec.value?.add_resource_options || []) as AnyRecord[]).map((item) => ({ ...item, kind: '体验' })),
  ...availableServices.value.map((item) => ({
    ...item,
    kind: '酒店权益',
    name: item.name || item.service_name,
    recommendation_score: Number(item.recommendation_score ?? 55),
    recommendation_level: item.recommendation_level || 'caution',
    recommendation_label: item.recommendation_label || '可选权益',
  })),
].sort((a: AnyRecord, b: AnyRecord) => Number(b.recommendation_score || 0) - Number(a.recommendation_score || 0)
  || Number(b.sets ?? b.available_quantity ?? 0) - Number(a.sets ?? a.available_quantity ?? 0)))
const weatherLabel = computed(() => {
  const scenario = String(overview.value.weather?.scenario || '')
  const base = { RAIN: '有降雨', SUNNY: '晴天', CLOUDY: '多云' }[scenario] || '天气读取中'
  const low = overview.value.weather?.temperature_min
  const high = overview.value.weather?.temperature_max
  return low !== null && low !== undefined && high !== null && high !== undefined
    ? `${base} ${Math.round(low)}–${Math.round(high)}℃`
    : base
})
const knowledgeTotal = computed(() => Number(overview.value.knowledge_total ?? (overview.value.knowledge || []).length ?? 0))
const primarySpec = computed<AnyRecord | null>(() => (advisor.value?.primary as AnyRecord) || null)
const judgement = computed<AnyRecord>(() => (advisor.value?.judgement as AnyRecord) || {})
const primaryExperience = computed<AnyRecord | null>(() => ((primarySpec.value?.experiences as AnyRecord[]) || [])[0] || null)
// 推荐卡和当前选择只保留一份状态：当前主方案的日期、房型和第一项体验
// 决定哪张卡显示“当前选择”，后端返回的 is_current 只作为兼容旧快照的兜底。
const rawPlans = computed<AnyRecord[]>(() => ((judgement.value.plans as AnyRecord[]) || []).slice(0, 4))
function planKey(item: AnyRecord) {
  return [item.target_date, item.room_type, item.resource_name].map((value) => String(value || '')).join('|')
}
const selectedPlanKey = computed(() => {
  const primary = primarySpec.value
  return primary ? planKey({ target_date: primary.target_date, room_type: primary.room_type, resource_name: primary.experiences?.[0]?.name }) : ''
})
function currentPlanCard() {
  const primary = primarySpec.value
  if (!primary) return null
  const experienceNames = ((primary.experiences || []) as AnyRecord[]).map((item) => String(item.name || '')).filter(Boolean)
  return {
    label: '当前选择',
    name: String(primary.room_type || '') + ' × ' + (experienceNames.join('、') || '待选体验'),
    target_date: primary.target_date,
    weekday: primary.weekday,
    crowd_label: primary.crowd_label,
    party_size: primary.party_size,
    room_type: primary.room_type,
    resource_name: experienceNames[0] || '',
    address: primary.experiences?.[0]?.address || '',
    window: primary.experiences?.map((item: AnyRecord) => item.window).filter(Boolean).join('、'),
    estimated_price: primary.price,
    remaining: primary.room_quantity,
    max_sellable: primary.max_sellable,
    fit_label: primary.selection_notice ? '需留意' : '当前方案',
    fit_reason: [primary.conclusion, primary.route_reason, primary.selection_notice].filter(Boolean).join('；'),
    is_current: true,
    is_ai_primary: false,
    message: '',
  } as AnyRecord
}
const plans = computed<AnyRecord[]>(() => {
  const selected = currentPlanCard()
  const list: AnyRecord[] = rawPlans.value.map((item) => ({
    ...item,
    is_current: selectedPlanKey.value ? planKey(item) === selectedPlanKey.value : Boolean(item.is_current),
    is_ai_primary: Boolean(item.is_ai_primary) || item.label === 'AI主推',
  }))
  if (!selected) return list
  const selectedIndex = list.findIndex((item) => item.is_current)
  if (selectedIndex < 0) return [selected, ...list].slice(0, 4)
  const original: AnyRecord = list[selectedIndex]
  list[selectedIndex] = { ...original, ...selected, label: original.label, is_ai_primary: original.is_ai_primary } as AnyRecord
  return list
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
const executionSummary = computed<AnyRecord[]>(() => {
  const provided = judgement.value.execution_summary
  if (Array.isArray(provided) && provided.length) return provided as AnyRecord[]

  // Keep the analysis summary visible even when an older or partial advisor
  // response omits execution_summary. Every fallback value comes from the
  // loaded operating data, and unavailable checks are stated explicitly.
  const windowDays = Number(pressure.value.window_days ?? 17)
  const roomCombinations = generationRoomOptions.value.length
  const remainingRooms = Number(pressure.value.unsold_room_nights ?? 0)
  const confirmedCount = recentConfirmedRows.value.length
  const crowd = crowdLabel(insights.value.top_crowds?.[0]?.target_crowd)
  const resourceRows = (insights.value.available_partner_resources || []) as AnyRecord[]
  const resourceCount = Number(pressure.value.available_resource_count ?? resourceRows.length)
  const primary = primarySpec.value

  return [
    {
      label: '\u623f\u6001\u5df2\u8bfb\u53d6',
      value: `\u672a\u6765 ${windowDays} \u5929\uff0c${roomCombinations} \u4e2a\u6709\u4f59\u91cf\u7684\u300c\u623f\u578b \xd7 \u65e5\u671f\u300d\u7ec4\u5408\uff1b\u5f85\u6d88\u5316 ${remainingRooms} \u95f4`,
    },
    {
      label: '\u8fd1\u671f\u9700\u6c42\u5df2\u5206\u6790',
      value: confirmedCount
        ? `\u8fd1 14 \u5929\u5df2\u786e\u8ba4 ${confirmedCount} \u5355\uff0c\u6210\u4ea4 \xa5${recentConfirmedRevenue.value}${crowd ? `\uff1b\u8ba2\u5355\u4e3b\u8981\u5ba2\u7fa4\uff1a${crowd}` : ''}`
        : '\u8fd1 14 \u5929\u65e0\u5df2\u786e\u8ba4\u6210\u4ea4\uff0c\u6682\u4e0d\u636e\u6b64\u5224\u65ad\u4e3b\u529b\u5ba2\u7fa4',
    },
    {
      label: '\u5408\u4f5c\u8d44\u6e90\u5df2\u5339\u914d',
      value: `\u53ef\u7528\u5408\u4f5c\u8d44\u6e90 ${resourceCount} \u9879\uff0c\u5176\u4e2d ${resourceRows.length} \u9879\u5df2\u8fdb\u5165\u5f53\u524d\u5206\u6790\u7ed3\u679c`,
    },
    {
      label: primary ? '\u4ef7\u683c\u4e0e\u5bb9\u91cf\u5df2\u6821\u9a8c' : '\u65b9\u6848\u6821\u9a8c\u72b6\u6001',
      value: primary
        ? `\u5efa\u8bae\u552e\u4ef7 \xa5${primary.price ?? '\u2014'}\uff1b\u5355\u4f4d\u6210\u672c \xa5${primary.unit_cost ?? '\u2014'}\uff1b\u6700\u4f4e\u5408\u6cd5\u4ef7 \xa5${primary.minimum_allowed_price ?? '\u2014'}\uff1b\u6700\u591a\u53ef\u552e ${primary.max_sellable ?? '\u2014'} \u5957`
        : '\u5f53\u524d\u5c1a\u65e0\u5b8c\u6574\u63a8\u8350\uff0c\u672c\u8f6e\u672a\u5b8c\u6210\u4ef7\u683c\u4e0e\u5bb9\u91cf\u6821\u9a8c\uff1b\u53ef\u5728\u4ea7\u54c1\u65b9\u6848\u9009\u62e9\u65e5\u671f\u3001\u623f\u578b\u540e\u7ee7\u7eed\u8c03\u6574',
    },
  ]
})
function routeForDay(dayIndex: number) {
  return ((primarySpec.value?.route_plan || []) as AnyRecord[]).find((item) => Number(item.day_index) === Number(dayIndex)) || null
}

const stages = [
  { id: 1, label: '经营分析', hint: '房态、需求与资源' },
  { id: 2, label: '产品方案', hint: '调整组合与行程' },
  { id: 3, label: '预览与发布', hint: '检查游客端展示' },
]
const availableStage = computed(() => {
  if (resolvedCandidateCount.value > 0 || sessionProposalIds.value.length > 0) return 3
  // Product planning remains available when analysis has no recommendation.
  // The stepper reports progress; it must not block operators from changing
  // the date, room type, audience, or resource filters.
  return 2
})
const stageIndex = computed(() => Math.min(selectedStage.value || availableStage.value, availableStage.value))
function selectStage(id: number) {
  if (id <= availableStage.value) selectedStage.value = id
}

async function load() {
  loading.value = true
  try {
    const [facts, tasks, pending, orderData, rooms] = await Promise.all([
      hotelApi.aiOverview(),
      hotelApi.aiConversations(),
      hotelApi.aiProposals('PENDING_CONFIRMATION'),
      hotelApi.ordersOverview(),
      hotelApi.rooms(),
    ])
    overview.value = facts.data
    conversations.value = tasks.data
    proposals.value = pending.data
    orders.value = orderData.data
    inventoryRooms.value = rooms.data as AnyRecord[]
    const latest = conversations.value[0] as AnyRecord | undefined
    if (latest && !activeConversationId.value) {
      activeConversationId.value = Number(latest.id)
      const key = operationStorageKey(activeConversationId.value)
      if (key) { try { operationLog.value = JSON.parse(localStorage.getItem(key) || '[]') } catch { operationLog.value = [] } }
      const stored = (latest.last_execution as AnyRecord | undefined)?.answer
      // 只恢复与当前协议一致的快照：必须带主推方案、资源候选和多方案列表，
      // 任何旧结构都交给自动开场重新生成，避免界面出现空缺或过期字段。
      const storedPrimary = (stored as AnyRecord | undefined)?.primary as AnyRecord | undefined
      const storedJudgement = (stored as AnyRecord | undefined)?.judgement as AnyRecord | undefined
      // 协议版本必须与后端一致，否则旧快照会让页面显示过期结构的数据。
      const contractOk = storedJudgement?.contract_version === ADVISOR_CONTRACT_VERSION
        && Boolean(storedPrimary?.resource_options)
        && Boolean((storedJudgement?.plans as unknown[] | undefined)?.length)
      if (stored && typeof stored === 'object' && contractOk) advisor.value = stored as AnyRecord
      const restoredPrimary = (advisor.value?.primary as AnyRecord) || null
      if (restoredPrimary) {
        const normalized = normalizePrimaryParty(restoredPrimary)
        advisor.value = { ...(advisor.value || {}), primary: normalized }
        previousPrimary.value = normalized
        targetInventoryKey.value = `${normalized.target_date}|${normalized.room_type}`
      }
      if (String(latest.last_execution?.step || '') === 'GENERATED') {
        sessionProposalIds.value = proposals.value
          .filter((item) => Number(item.conversation_id) === Number(latest.id))
          .map((item) => Number(item.id))
      }
    }
    const now = new Date()
    loadedAt.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  } catch (error) { showToast(errorMessage(error)) }
  finally { loading.value = false }
}

const orderRows = computed<AnyRecord[]>(() => (Array.isArray(orders.value.orders) ? orders.value.orders as AnyRecord[] : []))
function localDateKey(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}
const recentOrderRows = computed<AnyRecord[]>(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const start = new Date(today)
  start.setDate(start.getDate() - 13)
  const startKey = localDateKey(start)
  const todayKey = localDateKey(today)
  return orderRows.value.filter((row) => String(row.target_date || '') >= startKey && String(row.target_date || '') <= todayKey)
})
const recentConfirmedRows = computed<AnyRecord[]>(() => recentOrderRows.value.filter((row) => row.status === '已成交' || row.status === 'CONFIRMED'))
const recentConfirmedRevenue = computed(() => recentConfirmedRows.value.reduce((total, row) => total + Number(row.amount || 0), 0).toFixed(2))
function batchCreatedText(result: AnyRecord) {
  return ((result.created || []) as AnyRecord[]).map((item) => `${item.target_date} ${item.room_type}`).join('、')
}
const historyMessages = computed<AnyRecord[]>(() => {
  const messages = activeConversation.value?.messages
  return Array.isArray(messages) ? messages : []
})

async function applySalesCommand(text: string) {
  const response = await hotelApi.salesCommand(text)
  orders.value = (await hotelApi.ordersOverview()).data
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
  activeAdjust.value = ''
  flashCard()
  logOperation(instruction, changeNote.value, changes, nextPrimary)
}

function applyRefinedProduct(refinedProduct: AnyRecord | undefined, instruction: string) {
  if (!refinedProduct) return
  const current = primarySpec.value || {}
  const nextPrimary: AnyRecord = {
    ...current,
    product_id: refinedProduct.id,
    product_name: refinedProduct.product_name || current.product_name,
    target_date: refinedProduct.target_date || current.target_date,
    crowd: refinedProduct.target_crowd || current.crowd,
    crowd_label: crowdLabel(refinedProduct.target_crowd || current.crowd),
    party_size: refinedProduct.party_size ?? current.party_size,
    price: refinedProduct.suggested_price ?? current.price,
    max_sellable: refinedProduct.sale_quantity ?? current.max_sellable,
  }
  const changes = primaryDiffs(previousPrimary.value, nextPrimary)
  changeDetails.value = changes
  changeNote.value = describeChange(previousPrimary.value, nextPrimary)
  previousPrimary.value = nextPrimary
  advisor.value = { ...(advisor.value || {}), primary: nextPrimary }
  activeAdjust.value = ''
  flashCard()
  logOperation(instruction, changeNote.value, changes, nextPrimary)
}

async function submit() {
  const text = brief.value.trim()
  if (!text) { showToast('请用一句话说明想怎么调整方案'); return }
  submitting.value = true
  processingMessage.value = '正在根据你的要求重新计算方案…'
  try {
    if (editingProduct.value) {
      const response = await hotelApi.refineProduct(Number(editingProduct.value.id), text)
      refinements.value.push({ instruction: text, ...response.data })
      applyRefinedProduct(response.data.product as AnyRecord | undefined, text)
      brief.value = ''
      return
    }
    if (/(暂停|停售|下架|恢复|上架|开售|开启销售)/.test(text)) {
      await applySalesCommand(text)
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

// 「生成候选产品」把当前方案变成真正待确认的产品。
async function generateFromPlan(primary: AnyRecord) {
  if (!primary) return
  if (primary.product_id) {
    startEditing({ product_id: primary.product_id, name: primary.product_name })
    return
  }
  const experience = (primary.experiences || [])[0]?.name || ''
  submitting.value = true
  processingMessage.value = '正在生成游客端产品预览…'
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
    selectedStage.value = created.length ? 3 : 2
  } catch (error) { showToast(errorMessage(error)) }
  finally { submitting.value = false }
}

async function changeGenerationInventory() {
  const [targetDate, roomType] = targetInventoryKey.value.split('|')
  if (!targetDate || !roomType) return
  await ask(`改为 ${targetDate} 的 ${roomType}`)
}

function toggleEvidence(section: typeof panel.value) {
  panel.value = panel.value === section ? '' : section
  if (panel.value && evidenceFold.value) evidenceFold.value.open = true
}

function selectEvidence(section: typeof panel.value) {
  panel.value = section
  if (evidenceFold.value) evidenceFold.value.open = true
}

function resizeVisitorPreview(event: Event) {
  const frame = event.target as HTMLIFrameElement | null
  const doc = frame?.contentDocument
  if (!frame || !doc) return
  const resize = () => {
    const height = Math.max(doc.body?.scrollHeight || 0, doc.documentElement?.scrollHeight || 0, 600)
    frame.style.height = `${height}px`
    doc.documentElement.style.overflow = 'hidden'
    if (doc.body) doc.body.style.overflow = 'hidden'
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
  if (topCrowds.length) bits.push(`近 14 天${crowdLabel(topCrowds[0].target_crowd)}成交最集中（${topCrowds[0].confirmed_orders} 单）`)
  if (product.bottleneck_resource) bits.push(`可售上限受「${product.bottleneck_resource}」限制，本轮最多 ${product.sale_quantity} 套`)
  if (product.suggested_price !== undefined && product.unit_cost !== undefined) {
    bits.push(`建议售价 ¥${product.suggested_price}，单位成本 ¥${product.unit_cost}，毛利率 ${marginText(product.gross_margin)}`)
  }
  return bits.join('；') + '。'
}

function candidateRelation(proposal: AnyRecord) {
  const names = experienceNames(proposal)
  const product = proposal?.product as AnyRecord | undefined
  const current = ((primarySpec.value?.experiences as AnyRecord[]) || []).map((item) => String(item.name || '')).filter(Boolean)
  const roomName = String(((product?.resources || []) as AnyRecord[]).find((item) => item.resource_type === 'ROOM')?.resource_name || '')
  const sameFrame = product?.target_date === primarySpec.value?.target_date && roomName === String(primarySpec.value?.room_type || '')
  if (!sameFrame) return '替代日期或路线'
  if (current.length && current.length === names.length && current.every((name) => names.includes(name))) return '沿用当前组合'
  if (current.length && current.every((name) => names.includes(name))) return '沿用当前体验 · 增加资源'
  if (current.some((name) => names.includes(name))) return '保留部分体验 · 调整资源'
  if (names.length) return '替换体验资源'
  return '替代路线'
}

// 候选确认阶段只展示本轮生成的产品，不再把历史待确认队列铺到页面上。
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
  return (((primary.resource_options as AnyRecord[]) || [])).filter((item) => !item.is_current)
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

const AUTO_BRIEF = '重新读取未来17天房态、近14天订单和合作资源，按当前已选方向重新计算；如果没有可用组合，请说明具体原因和需要补充的数据'

async function autoStart() {
  submitting.value = true
  processingMessage.value = '正在读取经营数据并更新推荐…'
  try {
    const conversationId = await ensureConversation()
    const response = await hotelApi.advisor(Number(conversationId), AUTO_BRIEF, true)
    const data = response.data
    mergeConversation(data.conversation as AnyRecord)
    advisor.value = data.advisor as AnyRecord
    const nextPrimary = (advisor.value?.primary as AnyRecord) || null
    previousPrimary.value = nextPrimary
    if (nextPrimary && !targetInventoryKey.value) targetInventoryKey.value = `${nextPrimary.target_date}|${nextPrimary.room_type}`
  } catch (error) { showToast(errorMessage(error)) }
  finally { submitting.value = false }
}

onMounted(async () => { await load(); await autoStart() })
</script>

<template>
  <section class="ai-ops">
    <header class="page-head">
      <div class="head-actions">
        <span v-if="loadedAt" class="muted">数据更新 {{ loadedAt }}</span>
        <el-button size="small" plain :loading="submitting" @click="selectedStage = null; autoStart()">刷新可用资源</el-button>
        <el-button size="small" plain @click="historyOpen = true">操作历史<template v-if="operationLog.length">（{{ operationLog.length }}）</template></el-button>
      </div>
    </header>
    <div v-if="submitting" class="recompute-popover" role="status"><span class="recompute-spinner" />{{ processingMessage }}</div>

    <!-- ① 流程步骤 -->
    <nav class="stage-bar" aria-label="产品生成流程">
      <ol>
        <li v-for="s in stages" :key="s.id" :class="{ active: stageIndex === s.id, done: stageIndex > s.id, available: s.id <= availableStage }">
          <button type="button" :disabled="s.id > availableStage" @click="selectStage(s.id)">
            <i>{{ stageIndex > s.id ? '✓' : s.id }}</i>
            <div><b>{{ s.label }}</b><small>{{ s.hint }}</small></div>
          </button>
        </li>
      </ol>
    </nav>

    <!-- ② 经营状态 -->
    <section class="fact-strip">
      <button type="button" class="fact-card" :class="{ active: panel === 'inventory' }" @click="toggleEvidence('inventory')">
        <span>待消化房量</span>
        <strong>{{ pressure.unsold_room_nights ?? 0 }} 间</strong>
        <small>未来 {{ pressure.window_days ?? 17 }} 天 · {{ pressure.room_type_count ?? 0 }} 种房型</small>
      </button>
      <button type="button" class="fact-card" :class="{ active: panel === 'inventory' }" @click="toggleEvidence('inventory')">
        <span>重点库存</span>
        <strong>{{ focusRoom?.room_type || '—' }} {{ focusRoom?.remaining ?? 0 }} 间</strong>
        <small>{{ focusRoom?.target_date || '暂无数据' }}</small>
      </button>
      <button type="button" class="fact-card" :class="{ active: panel === 'resources' }" @click="toggleEvidence('resources')">
        <span>可用合作资源</span>
        <strong>{{ pressure.available_resource_count ?? 0 }} 个</strong>
        <small>重点日期可组包</small>
      </button>
      <div class="fact-actions">
        <span class="weather-chip">杭州 · {{ weatherLabel }}</span>
        <span v-if="overview.weather && overview.weather.usable === false" class="fact-warn">天气未核验，方案仍可生成并附天气提示</span>
      </div>
    </section>

    <!-- ③ 经营分析：证据与本轮执行摘要 -->
    <section class="panel stage-panel">
      <details ref="evidenceFold" class="evidence-fold">
        <summary>经营证据<span class="muted"> · 房态、合作资源、订单、天气、知识库</span></summary>
        <div class="evidence-tabs">
          <button type="button" :class="{ active: panel === 'inventory' }" @click="selectEvidence('inventory')">房态</button>
          <button type="button" :class="{ active: panel === 'resources' }" @click="selectEvidence('resources')">合作资源</button>
          <button type="button" :class="{ active: panel === 'orders' }" @click="selectEvidence('orders')">订单</button>
          <button type="button" :class="{ active: panel === 'weather' }" @click="selectEvidence('weather')">天气</button>
          <button type="button" :class="{ active: panel === 'knowledge' }" @click="selectEvidence('knowledge')">知识库</button>
        </div>

        <p v-if="!panel" class="muted">房态、资源容量、天气与利润校验分别来自客房库存、合作资源、天气服务和财务规则。点上面的分类展开原始数据。</p>

        <div v-if="panel === 'inventory'" class="evidence-body">
          <div class="chip-row">
            <span>未来 {{ pressure.window_days ?? 17 }} 天待消化 {{ pressure.unsold_room_nights ?? 0 }} 间</span>
            <span>有房日期 {{ pressure.date_count ?? 0 }} 个 · 房型 {{ pressure.room_type_count ?? 0 }} 种</span>
            <span v-if="focusRoom">压力最高 {{ focusRoom.room_type }} {{ focusRoom.remaining }} 间（{{ focusRoom.target_date }}）</span>
          </div>
          <table v-if="advisor?.inventory?.length" class="reply-table">
            <thead><tr><th>日期</th><th>房型</th><th>剩余</th><th>参考价</th></tr></thead>
            <tbody><tr v-for="row in advisor.inventory.slice(0, 12)" :key="row.date + row.room_type"><td>{{ String(row.date).slice(5) }} {{ row.weekday }}</td><td>{{ row.room_type }}</td><td>{{ row.remaining }} 间</td><td>¥{{ row.price }}</td></tr></tbody>
          </table>
        </div>

        <div v-if="panel === 'resources'" class="evidence-body">
          <table v-if="insights.available_partner_resources?.length" class="reply-table">
            <thead><tr><th>合作资源</th><th>名额</th><th>室内</th><th>适配客群</th></tr></thead>
            <tbody><tr v-for="row in insights.available_partner_resources" :key="row.name"><td>{{ row.name }}</td><td>{{ row.remaining_capacity }}</td><td>{{ row.indoor ? '是' : '否' }}</td><td>{{ crowdListLabel(row.suitable_crowds) }}</td></tr></tbody>
          </table>
          <p v-else class="muted">重点日期暂无可组包的合作资源。</p>
        </div>

        <div v-if="panel === 'orders'" class="evidence-body">
          <div class="chip-row">
            <span>近 14 天已确认 {{ recentConfirmedRows.length }} 单</span>
            <span>成交 ¥{{ recentConfirmedRevenue }}</span>
            <span>订单最多客群 {{ crowdLabel(insights.top_crowds?.[0]?.target_crowd) || '暂无' }}</span>
          </div>
          <ul v-if="signals.length" class="signal-list"><li v-for="(signal, index) in signals" :key="index">{{ signal.message }}</li></ul>
          <table class="reply-table">
            <thead><tr><th>产品</th><th>类别</th><th>金额</th><th>日期</th><th>状态</th></tr></thead>
            <tbody><tr v-for="row in recentOrderRows.slice(0, 8)" :key="row.product_name + row.target_date"><td>{{ row.product_name }}</td><td>{{ categoryLabel(row.category) }}</td><td>¥{{ row.amount }}</td><td>{{ row.target_date }}</td><td>{{ statusLabel(row.status) }}</td></tr><tr v-if="!recentOrderRows.length"><td colspan="5" class="muted">近 14 天没有出行记录。</td></tr></tbody>
          </table>
          <p class="muted">仅使用汇总经营数据，不含游客个人信息。</p>
        </div>

        <div v-if="panel === 'weather'" class="evidence-body">
          <div class="chip-row">
            <span>天气：{{ weatherLabel }}</span>
            <span>气温：{{ overview.weather?.temperature_min ?? '—' }}–{{ overview.weather?.temperature_max ?? '—' }}℃</span>
            <span>降雨概率：{{ overview.weather?.precipitation_probability ?? '—' }}%</span>
            <span>核验状态：{{ overview.weather?.usable ? '已核验' : '待确认' }}</span>
          </div>
          <p>{{ overview.weather?.advisory || '天气信息读取中。' }}</p>
        </div>

        <div v-if="panel === 'knowledge'" class="evidence-body">
          <p class="muted">知识库共 {{ knowledgeTotal }} 条，含开放时间、预约提示与来源，只作为行程参考，不构成套餐权益。</p>
          <table class="reply-table">
            <thead><tr><th>地点</th><th>类别</th><th>区域</th></tr></thead>
            <tbody><tr v-for="row in (overview.knowledge || []).slice(0, 8)" :key="row.name"><td>{{ row.name }}</td><td>{{ row.category_label || row.category }}</td><td>{{ row.area }}</td></tr></tbody>
          </table>
        </div>
      </details>
    </section>

    <!-- AI 执行摘要 -->
    <section class="panel stage-panel">
      <details class="evidence-fold">
        <summary>AI 执行摘要<span class="muted"> · 这一轮读了什么、校验了什么</span></summary>
        <ul class="summary-list">
            <li v-for="item in executionSummary" :key="item.label"><b>✓ {{ item.label }}</b><span>{{ item.value }}</span></li>
        </ul>
        <details v-if="judgement.trace?.length" class="tech-fold">
          <summary>查看技术详情</summary>
          <ol class="trace-list">
            <li v-for="step in judgement.trace" :key="step.tool" :class="step.status">
              <b>{{ step.tool_label || step.tool }}</b><span>{{ step.detail }}</span><em>{{ step.status === 'ok' ? '已通过' : step.status === 'pass' ? '已通过' : '需注意' }}</em>
            </li>
          </ol>
          <p class="muted">技术详情保留原始工具标识，供开发与评审核对。</p>
        </details>
      </details>
    </section>

    <!-- ③ Step 2：推荐方向。进入候选确认后收起，避免两个业务阶段同时出现。 -->
    <section v-if="stageIndex === 2" class="panel stage-panel">
      <div class="stage-panel__head">
        <h2>推荐方向</h2>
        <span v-if="!primarySpec" class="muted">先选一个方向，再让它变成正式候选</span>
      </div>
      <div v-if="generationRoomOptions.length" class="date-room-picker">
        <div class="date-room-picker__label"><b>生成目标</b><span>先选日期，再选当日可售房型</span></div>
        <el-select id="generation-date" v-model="generationDate" filterable placeholder="选择日期" @change="changeGenerationInventory">
          <el-option v-for="date in generationDates" :key="date" :value="date" :label="date" />
        </el-select>
        <el-select id="generation-room-type" v-model="generationRoomType" filterable placeholder="选择房型" @change="changeGenerationInventory">
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
          <h3>{{ item.name }}</h3>
          <p class="muted">{{ item.target_date }}（{{ item.weekday }}）<template v-if="item.window"> · {{ item.window }}</template><template v-if="item.indoor"> · 室内</template></p>
          <ul>
            <li class="plan-capacity-line">房型余量 <b>{{ item.remaining }} 间</b><span>·</span>最多可售 <b>{{ item.max_sellable }} 套</b></li>
          </ul>
          <p class="plan-fit-note" :class="{ caution: String(item.fit_label || '').startsWith('需核对'), negative: item.fit_label === '不建议优先' }"><b>{{ item.fit_label || (item.is_current ? '当前方案' : '推荐依据') }}</b>{{ item.fit_reason || planReason(item) }}</p>
          <span v-if="item.is_current" class="plan-current">当前选择 · 详情与调整入口已展开</span>
          <el-button v-else size="small" plain :disabled="submitting" @click="ask(item.message)">切换为当前方案</el-button>
        </article>
      </div>
      <p v-else-if="!submitting" class="muted">{{ judgement.text || '当前没有可推荐的组合，可以调整日期、客群、体验或价格目标后继续。' }}</p>

      <div v-if="!plans.length && !primarySpec" class="empty-candidate">
        <div>✦</div>
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
            <h3>{{ primarySpec.product_name }}</h3>
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
            <span>毛利率 {{ primarySpec.margin }}%</span>
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

          <div v-if="primarySpec.itinerary_days?.length" class="itinerary-days">
            <article v-for="day in primarySpec.itinerary_days" :key="day.day_index" class="itinerary-day">
              <header><b>{{ day.label }} · {{ day.title }}</b><span>{{ day.date }}</span></header>
              <p class="itinerary-day__summary">{{ day.summary }}</p>
              <div v-for="(item, index) in day.items" :key="String(day.day_index) + '-' + String(index)" class="itinerary-entry">
                <time>{{ item.time || '时间待确认' }}</time>
                <div>
                  <strong>{{ item.title }}</strong>
                  <span v-if="item.route_only" class="route-only-badge">路线建议 · 非套餐权益</span>
                  <p>{{ item.description }}</p>
                  <small>{{ [item.address, item.duration_text, item.area].filter(Boolean).join(' · ') }}</small>
                  <small v-if="item.notes" class="itinerary-entry__note">出行前核验：{{ item.notes }}</small>
                </div>
              </div>
              <div v-if="routeForDay(day.day_index)?.legs?.length" class="route-transfer-list">
                <p v-for="leg in (routeForDay(day.day_index)?.legs || [])" :key="leg.from_stop + leg.to_stop">
                  {{ leg.from_stop }} → {{ leg.to_stop }} · {{ leg.distance_label || '交通机动' }}<template v-if="leg.minutes"> · 预留约 {{ leg.minutes }} 分钟</template><template v-else> · 具体地点待定，暂不估算耗时</template>
                  <small>{{ leg.note }}</small>
                </p>
              </div>
            </article>
          </div>

          <details v-if="primarySpec.cost_breakdown?.length || primarySpec.blocks?.length" class="reason-fold decision-more">
            <summary>价格与收益</summary>
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
          </details>

          <p v-if="primarySpec.conclusion" class="conclusion"><b>AI建议：</b>{{ primarySpec.conclusion }}</p>

          <div class="decision-card__actions">
            <el-button type="primary" :disabled="submitting || Boolean(budgetShortfall)" @click="generateFromPlan(primarySpec)">{{ primarySpec.product_id ? '继续优化当前产品' : '生成候选产品' }}</el-button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'resources' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'resources' ? '' : 'resources'">换资源</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'price' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'price' ? '' : 'price'">调价格</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'crowd' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'crowd' ? '' : 'crowd'">换客群</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'route' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'route' ? '' : 'route'">改路线</button>
            <button type="button" class="ghost-link" :class="{ active: activeAdjust === 'service' }" :disabled="submitting" @click="activeAdjust = activeAdjust === 'service' ? '' : 'service'">增加资源</button>
          </div>

          <div v-if="activeAdjust === 'price'" class="adjust-panel">
            <div class="adjust-panel__head"><b>调整建议售价</b><span class="muted">当前 ¥{{ primarySpec.price }}，最低合法价 ¥{{ primarySpec.floor_price }}；改价会重新跑容量与利润校验</span></div>
            <div class="option-row"><button type="button" @click="ask(`价格按最低合法价 ${primarySpec.floor_price} 来`)">按最低合法价 ¥{{ primarySpec.floor_price }}</button><button type="button" @click="ask('价格降到 650 以内')">降到 650 以内</button><button type="button" @click="ask('价格降到 600 以内')">降到 600 以内</button></div>
            <div class="price-input"><input v-model="priceTarget" inputmode="numeric" placeholder="输入目标价，例如 620" /><el-button size="small" type="primary" :disabled="submitting" @click="applyPriceTarget">按这个价格重算</el-button></div>
          </div>

          <div v-if="activeAdjust === 'crowd'" class="adjust-panel"><div class="adjust-panel__head"><b>切换目标客群</b><span class="muted">仅修改目标客群，房型、体验与酒店权益保持不变；若原资源的客群标签不匹配，会明确提示核对</span></div><div class="option-row"><button v-for="item in crowdChoices" :key="item.label" type="button" @click="ask(item.message)">{{ item.label }}</button></div></div>

          <div v-if="activeAdjust === 'resources'" class="adjust-panel"><div class="adjust-panel__head"><b>替换当前合作资源</b><span class="muted">保持日期、房型和客群，只替换核心体验；增加第二项体验请使用“增加资源”。</span></div><div v-if="resourceSwaps.length" class="alt-grid"><article v-for="item in resourceSwaps" :key="`swap-${item.name}`" class="alt-card"><h3>{{ item.name }}</h3><p class="muted">{{ item.window || '按场次' }} · 仍可支撑 {{ item.sets }} 套 · 预估价 ¥{{ item.estimated_price }}</p><p v-if="item.address" class="resource-fit-note">地点：{{ item.address }}</p><p class="alt-card__why">{{ item.indoor ? '室内体验，雨天不受影响。' : '户外体验，出发前会再核对天气。' }}每人结算 ¥{{ item.settlement_price }}。</p><el-button size="small" plain @click="ask(`${primarySpec.target_date} 的 ${primarySpec.room_type} 换成 ${item.name}`)">换成这个体验</el-button></article></div><p v-else class="muted">当前日期与房型下没有其它可用合作资源。</p></div>

          <div v-if="activeAdjust === 'route'" class="adjust-panel"><div class="adjust-panel__head"><b>选择路线调整方式</b><span class="muted">先选安排，再由 AI 按场次和天气重新校验。</span></div><div class="option-row"><button type="button" @click="ask('路线留出更多自由时间，晚上体验结束后直接回酒店')">留出自由时间</button><button type="button" @click="ask('优先室内路线，减少户外移动')">优先室内路线</button><button type="button" @click="ask('保持当前体验，只调整先后顺序')">只调先后顺序</button></div></div>

          <div v-if="activeAdjust === 'service'" class="adjust-panel"><div class="adjust-panel__head"><b>选择要增加的体验或酒店权益</b><span class="muted">按客群、场次、天气、余量和路线匹配度排序；绿色优先推荐，红色表示不建议优先。</span></div><div v-if="availableAddResources.length" class="alt-grid"><article v-for="item in availableAddResources" :key="`${item.kind}-${item.id || item.name}`" class="alt-card" :class="recommendationClass(item)"><div class="resource-card__head"><span class="section-kicker">{{ item.kind }}<template v-if="item.fit_label"> · {{ item.fit_label }}</template></span><span class="recommendation-badge" :class="recommendationClass(item)">{{ recommendationLabel(item) }}</span></div><h3>{{ item.name }}</h3><p class="muted">可售 {{ item.sets ?? item.available_quantity ?? '—' }} 套<template v-if="item.window"> · {{ item.window }}</template> · 单人成本 ¥{{ item.settlement_price ?? item.unit_cost ?? '—' }}</p><p v-if="item.address" class="resource-fit-note">地点：{{ item.address }}</p><p v-if="item.fit_reason" class="resource-fit-note">{{ item.fit_reason }}</p><el-button size="small" plain :disabled="item.addable === false" @click="ask(item.kind === '体验' ? `增加体验：${item.name}` : `增加酒店服务：${item.name}`)">{{ item.is_selected ? '已加入' : item.addable === false ? '暂不可加入' : `增加这项${item.kind}` }}</el-button></article></div><p v-else class="muted">当前日期没有已启用组包的合作体验或酒店权益。请在合作资源池添加资源并允许组包，再刷新方案。</p></div>

          <details class="reason-fold"><summary>展开推荐依据与风险</summary><div class="detail-tabs"><button type="button" :class="{ active: detailTab === 'basis' }" @click="detailTab = 'basis'">经营价值</button><button type="button" :class="{ active: detailTab === 'value' }" @click="detailTab = 'value'">收益与容量</button><button type="button" :class="{ active: detailTab === 'risk' }" @click="detailTab = 'risk'">风险与限制</button><button type="button" :class="{ active: detailTab === 'compare' }" @click="detailTab = 'compare'">方案比较</button></div><div class="detail-body"><template v-if="detailTab === 'basis'"><p v-for="item in (primarySpec.reason_sections || [])" :key="item.label"><b>{{ item.label }}：</b>{{ item.text }}</p><p v-if="!primarySpec.reason_sections?.length">{{ logicByTitle['推荐逻辑'] || '按当前房态、近 14 天成交与合作资源容量综合判断。' }}</p></template><template v-else-if="detailTab === 'value'"><p>{{ logicByTitle['酒店经营价值'] || '按建议售价与最大可售量计算收益。' }}</p></template><template v-else-if="detailTab === 'risk'"><p>{{ logicByTitle['风险与约束'] || '容量、场次与天气变化会触发自动复检。' }}</p></template><template v-else><p>{{ primarySpec.not_chosen || '本轮没有其它更高优先级的组合。' }}</p></template></div></details>
        </article>
      </div>
    </section>

    <!-- ⑤ Step 3：候选确认。这里不再显示产品方案编辑控件。 -->
    <section v-if="stageIndex === 3" class="panel stage-panel">
      <div class="stage-panel__head">
        <h2>游客端预览</h2>
        <span class="muted">方案已在上一阶段完成调整；这里检查成品展示并发布</span>
      </div>
      <p v-if="primarySpec" class="source-plan">来源方案：{{ primarySpec.product_name }} · {{ primarySpec.room_type }} × {{ primaryExperience?.name || '当前体验' }} · ¥{{ primarySpec.price }}</p>
      <div v-if="!candidateCards.length && resolvedCandidateCount" class="panel empty-state">本轮产品已完成确认，可前往产品库继续制作营销内容。</div>
      <div class="candidate-grid">
        <article v-for="card in candidateCards" :key="card.key" class="candidate-card">
          <div class="candidate-card__body">
            <header>
              <h3>{{ card.name }}</h3>
              <b>¥{{ card.price }}</b>
            </header>
            <span class="candidate-relation">{{ card.relation }}</span>
            <p class="muted">{{ card.date }} · {{ card.crowd_label }} · {{ card.party }} 人<template v-if="card.quantity !== ''"> · 可售 {{ card.quantity }} 套</template></p>
            <p v-if="card.experiences.length" class="candidate-card__exp">正式体验：{{ card.experiences.join('、') }}</p>
            <p v-if="card.services.length" class="candidate-card__exp">酒店权益：{{ card.services.join('、') }}</p>
            <p class="candidate-card__figures">成本 ¥{{ card.cost }} · 最低合法价 ¥{{ card.floor_price }}<template v-if="card.margin_label"> · 毛利率 {{ card.margin_label }}</template></p>
            <iframe class="visitor-preview-frame" :src="visitorPreviewUrl(card)" title="游客端商品完整预览" loading="lazy" scrolling="no" @load="resizeVisitorPreview" />
            <div class="badge-row">
              <span>✓ 库存通过</span>
              <span>✓ 资源通过</span>
              <span>✓ 利润通过</span>
            </div>
            <div class="candidate-card__actions">
              <el-button size="small" type="primary" @click="confirm(card.raw, 'PUBLISH')">确认并发布</el-button>
              <el-button size="small" plain @click="confirm(card.raw, 'DRAFT')">保存为草稿</el-button>
              <el-button size="small" plain @click="editVisitorCopy(card)">{{ Number(copyDraft?.id) === Number(card.product_id) ? '收起文案编辑' : '微调游客文案' }}</el-button>
            </div>
            <details class="batch-apply-fold">
              <summary>批量应用到其他日期与房型</summary>
              <p class="muted">只创建房量、人数和同名资源都满足条件的草稿；不满足的目标会列出原因。</p>
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
              <details class="copy-subsection"><summary>体验名称与介绍</summary>
                <article v-for="resource in copyDraft.resources" :key="`${resource.resource_type}:${resource.resource_id}`" class="copy-field">
                  <label>体验名称 · {{ resource.address || '酒店地址' }}</label>
                  <el-input v-model="resource.resource_name" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteResourceName(resource)">AI生成替换文字</el-button>
                  <label>体验介绍</label>
                  <el-input v-model="resource.description" type="textarea" :rows="2" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteResourceCopy(resource)">AI生成替换文字</el-button>
                </article>
              </details>
              <details v-if="copyDraft.assets?.length" class="copy-subsection"><summary>营销素材</summary>
                <article v-for="asset in copyDraft.assets" :key="asset.asset_type" class="copy-field">
                  <label>{{ asset.platform || asset.asset_type }} · 标题</label>
                  <el-input v-model="asset.title" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteAssetCopy(asset, 'marketing_asset_title')">AI生成替换文字</el-button>
                  <label>正文</label>
                  <el-input v-model="asset.content" type="textarea" :rows="3" />
                  <el-button size="small" plain :loading="copyRewriting" @click="rewriteAssetCopy(asset, 'marketing_asset_content')">AI生成替换文字</el-button>
                </article>
              </details>
              <details v-if="copyDraft.details" class="copy-subsection"><summary>商品详情文案</summary>
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
              <details class="copy-subsection"><summary>每日行程文案</summary>
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
            <details class="reason-fold">
              <summary>查看推荐依据</summary>
              <p>{{ card.reason }}</p>
            </details>
          </div>
        </article>
      </div>
    </section>

    <!-- 微调记录 -->
    <section v-if="refinements.length" class="panel stage-panel">
      <div class="stage-panel__head"><h2>微调记录</h2><span class="muted">旧版本保留在版本记录里，可回退</span></div>
      <div v-for="(item, index) in refinements" :key="`refine-${index}`" class="refine-row">
        <p><span class="layer-badge">{{ item.layer_label }}</span>{{ item.message }}</p>
        <table v-if="item.changes?.length" class="reply-table">
          <thead><tr><th>字段</th><th>修改前</th><th>修改后</th></tr></thead>
          <tbody><tr v-for="row in item.changes" :key="row.field"><td>{{ row.label }}</td><td class="muted">{{ row.before }}</td><td>{{ row.after }}</td></tr></tbody>
        </table>
        <div v-if="item.checks?.length" class="chip-row"><span v-for="check in item.checks" :key="check.label">{{ check.label }}：{{ check.value }}</span></div>
      </div>
    </section>

    <!-- ⑧ 吸底输入区 -->
    <form class="composer" @submit.prevent="submit()">
      <div class="composer__context">
        <span v-if="editingProduct" class="context-chip is-editing">正在微调：{{ editingProduct.name }}<button type="button" @click="stopEditing">结束</button></span>
        <span v-else class="context-chip">正在调整：{{ currentObjectLabel }}</span>
        <button v-if="advisor || operationLog.length" type="button" class="ghost-link" @click="clearConversation">重新开始</button>
      </div>
      <div class="composer__quick">
        <button v-for="cmd in quickCommands" :key="cmd" type="button" @click="ask(cmd)">{{ cmd }}</button>
      </div>
      <div class="composer__main">
        <textarea v-model="brief" rows="1" :placeholder="editingProduct ? '例如：价格做到 700 以内；或者换个更适合两个人的体验' : '例如：价格低一点 / 换成双人 / 不要亲子 / 改成 9 月 27 日'" @input="growInput" @keydown.enter.exact.prevent="submit()" />
        <button type="submit" :disabled="!brief.trim() || submitting">调整方案</button>
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

<style scoped>
/* 正文控制在易读宽度内，超宽屏不出现横跨整屏的中文长行。 */
.ai-ops { display: grid; gap: 14px; width: 100%; min-width: 0; max-width: 1280px; margin-inline: auto; box-sizing: border-box; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.page-head__text strong { display: block; font-size: 15px; }
.page-head__text p { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
.head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

/* 步骤条 */
.stage-bar ol { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 0; padding: 0; list-style: none; }
.stage-bar li { min-width: 0; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); }
.stage-bar li button { display: flex; width: 100%; align-items: center; gap: 9px; padding: 9px 12px; border: 0; border-radius: inherit; background: transparent; color: var(--ink); text-align: left; cursor: pointer; }
.stage-bar li button:disabled { cursor: default; }
.stage-bar li.available button:hover { background: #f8fbf9; }
.stage-bar i { display: grid; place-items: center; width: 22px; height: 22px; flex: 0 0 auto; border-radius: 50%; background: var(--panel-soft); color: var(--muted); font-size: 11px; font-style: normal; }
.stage-bar b { display: block; font-size: 12.5px; }
.stage-bar small { display: block; margin-top: 2px; color: var(--muted); font-size: 10px; }
.stage-bar li.active { border-color: var(--teal); background: #f1f8f4; }
.stage-bar li.active i { background: var(--teal-dark); color: #fff; }
.stage-bar li.done i { background: #dcece4; color: var(--teal-dark); }

/* 经营指标 */
.fact-strip { display: flex; align-items: stretch; gap: 8px; flex-wrap: wrap; }
.fact-card { flex: 1 1 168px; min-width: 0; display: grid; gap: 2px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); color: var(--ink); text-align: left; cursor: pointer; transition: border-color .18s, background .18s; }
.fact-card:hover { border-color: var(--teal); }
.fact-card.active { border-color: var(--teal); background: #f1f8f4; }
.fact-card span { color: var(--muted); font-size: 10px; }
.fact-card strong { font-family: var(--font-mono); font-size: 16px; overflow-wrap: anywhere; }
.fact-card small { color: var(--muted); font-size: 10px; }
.fact-actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.weather-chip { padding: 5px 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 11px; white-space: nowrap; }
.fact-warn { padding: 4px 9px; border-radius: 999px; background: #fff6e5; color: #9a6b2a; font-size: 10px; white-space: nowrap; }

/* 分区容器 */
.stage-panel { display: grid; gap: 12px; }
.stage-panel__head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.stage-panel__head h2 { margin: 0; font-size: 15px; }
.recompute-popover { position: fixed; z-index: 100; top: 18px; left: 50%; display: flex; align-items: center; gap: 10px; max-width: min(92vw, 460px); padding: 12px 18px; border: 1px solid #d9e8e1; border-radius: 999px; background: rgba(255,255,255,.97); box-shadow: 0 12px 35px rgba(26,55,45,.16); color: #245e51; font-size: 12px; transform: translateX(-50%); }
.recompute-spinner { width: 15px; height: 15px; flex: 0 0 auto; border: 2px solid #d8eae2; border-top-color: #267664; border-radius: 50%; animation: recompute-spin .7s linear infinite; }
@keyframes recompute-spin { to { transform: rotate(360deg); } }
.change-note { display: grid; gap: 7px; margin: 0; padding: 10px 12px; border: 1px solid #d4e7dc; border-radius: 9px; background: #f5faf7; color: #2f6f60; font-size: 11.5px; line-height: 1.65; }
.change-note > b { font-size: 12px; }
.change-note ul { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.change-note li { display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 8px; align-items: start; padding-top: 6px; border-top: 1px solid #e1eee7; }
.change-note li > strong { color: #53665d; font-weight: 600; }
.change-note li > div { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: 6px; align-items: start; }
.change-note del { color: #8a7777; text-decoration-color: #a77f7f; }
.change-note li > div b { color: #245e51; }
.change-note p { margin: 0; }

/* 方案方向卡：固定列数，方案数量变化时卡片宽度不变，避免点击后整块布局跳动。 */
.plan-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.plan-card { display: grid; gap: 6px; min-height: 196px; padding: 12px; border: 1px solid var(--line); border-radius: 11px; background: var(--paper); align-content: start; }
.plan-card header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.plan-badges { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.plan-card header b { color: var(--teal-dark); font-family: var(--font-mono); font-size: 15px; }
.plan-badge { padding: 2px 9px; border-radius: 999px; background: var(--panel-soft); color: var(--muted); font-size: 10px; }
.plan-badge--ai { background: #e9f2ff; color: #3f5f91; }
.plan-card h3 { margin: 0; font-size: 13.5px; line-height: 1.4; }
.plan-card ul { display: grid; gap: 2px; margin: 0; padding-left: 16px; color: #45524c; font-size: 11px; line-height: 1.6; }
.plan-card .plan-capacity-line { display: flex; gap: 5px; padding-left: 0; list-style: none; white-space: nowrap; }
.plan-capacity-line b { color: #34483f; font-weight: 650; }
.plan-fit-note,.resource-fit-note { margin: 0; color: #486158; font-size: 11px; line-height: 1.6; }
.plan-fit-note b { margin-right: 5px; color: var(--teal-dark); }
.plan-fit-note.caution,.resource-fit-note { color: #8a642c; }
.plan-fit-note.caution b { color: #8a642c; }
.plan-fit-note.negative { color: #98524a; }
.plan-fit-note.negative b { color: #98524a; }
.plan-card.is-current { border-color: var(--teal); background: #f6fbf8; }
.plan-card.is-current .plan-badge { background: var(--teal-dark); color: #fff; }
.plan-card.is-cheaper .plan-badge { background: #eaf4ef; color: #2f6f60; }
.plan-card.is-capacity .plan-badge { background: #eef2fb; color: #44548a; }
.plan-card.is-rain .plan-badge { background: #eaf1f7; color: #3c6a92; }
.plan-current { display: grid; place-items: center; min-height: 32px; color: var(--teal-dark); font-size: 11.5px; font-weight: 650; }
.plan-card :deep(.el-button) { width: 100%; }

/* 当前选择直接展开在推荐方向面板内 */
.selected-plan-detail { display: grid; gap: 9px; padding-top: 4px; }
.selected-plan-detail__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.selected-plan-detail__head h3 { margin: 2px 0 3px; font-size: 15px; }
.selected-plan-detail__head p { margin: 0; font-size: 11.5px; }
.section-kicker { color: var(--teal-dark); font-size: 10px; font-weight: 700; letter-spacing: .08em; }
.product-structure { display: grid; gap: 6px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); }
.structure-row { display: grid; grid-template-columns: 74px minmax(0, 1fr); gap: 8px; align-items: start; font-size: 11px; line-height: 1.6; }
.structure-row > b { color: var(--muted); font-size: 10px; }
.structure-row > span { color: #33443c; }
.itinerary-days { display: grid; gap: 9px; }
.itinerary-day { display: grid; gap: 7px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: #f8fbf9; }
.itinerary-day > header { display: flex; justify-content: space-between; gap: 9px; color: var(--teal-dark); font-size: 11px; }
.itinerary-day > header span { color: var(--muted); font-family: var(--font-mono); }
.itinerary-day__summary { margin: 0; color: var(--muted); font-size: 10px; line-height: 1.5; }
.itinerary-entry { display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 9px; padding: 7px 0; border-top: 1px solid #e8eeea; }
.itinerary-entry > time { color: var(--teal-dark); font-family: var(--font-mono); font-size: 10px; }
.itinerary-entry strong { color: var(--ink); font-size: 11px; }
.itinerary-entry p { margin: 3px 0; color: #55635d; font-size: 10px; line-height: 1.5; }
.itinerary-entry small { display: block; margin-top: 3px; color: var(--muted); font-size: 9px; line-height: 1.5; }
.itinerary-entry__note { color: #8a642c !important; }
.route-only-badge { display: inline-block; margin-left: 6px; padding: 2px 6px; border-radius: 999px; background: #eaf2ed; color: #426452; font-size: 9px; }
.route-transfer-list { display: grid; gap: 5px; padding-top: 5px; border-top: 1px dashed var(--line); }
.route-transfer-list p { margin: 0; color: #50615a; font-size: 9px; line-height: 1.55; }
.route-transfer-list small { display: block; color: var(--muted); font-size: 9px; }
.calculation-list { display: grid; gap: 4px; margin-top: 9px; padding-top: 8px; border-top: 1px dashed var(--line); }
.calculation-list > div { display: flex; justify-content: space-between; gap: 8px; color: #55635d; font-size: 11px; }
.calculation-list b { color: var(--ink); font-family: var(--font-mono); }

/* 当前方案卡 */
.decision-card { display: grid; gap: 12px; padding: 14px; border: 1px solid var(--teal); border-radius: 12px; background: linear-gradient(180deg, #f6fbf8, #fff 45%); }
.decision-card__top { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; }
.decision-card__top > img { width: 100%; height: 100%; min-height: 132px; object-fit: cover; border-radius: 9px; }
.decision-card__ph { display: grid; place-items: center; min-height: 132px; border-radius: 9px; background: var(--panel-soft); color: var(--teal); font-size: 22px; }
.decision-card__head h3 { margin: 0 0 5px; font-size: 17px; line-height: 1.4; }
.decision-card__head p { margin: 0 0 2px; font-size: 12px; }
.decision-card__include { color: #45524c; }
.figure-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: center; gap: 8px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); color: var(--muted); font-size: 11.5px; }
.figure-row > span { display: inline-flex; align-items: baseline; gap: 4px; white-space: nowrap; }
.figure-row b { color: var(--teal-dark); font-family: inherit; font-size: 12px; font-weight: 700; }
.key-evidence { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.key-evidence > div { display: grid; gap: 3px; padding: 9px 11px; border: 1px solid var(--line); border-radius: 9px; background: var(--paper); }
.key-evidence span { color: var(--muted); font-size: 10px; }
.key-evidence b { font-size: 12.5px; overflow-wrap: anywhere; }
.conclusion { margin: 0; font-size: 13px; line-height: 1.7; }
.budget-note { display: grid; gap: 8px; padding: 10px 12px; border: 1px solid #e6cfa8; border-radius: 10px; background: #fffaf0; }
.budget-note p { margin: 0; color: #8a6420; font-size: 12px; line-height: 1.7; }
.reason-fold summary { cursor: pointer; color: var(--teal-dark); font-size: 11.5px; }
.reason-fold ul { display: grid; gap: 4px; margin: 8px 0 0; padding-left: 17px; color: #45524c; font-size: 12px; line-height: 1.7; }
.reason-fold p { margin: 6px 0 0; color: #55635d; font-size: 11.5px; line-height: 1.7; }
.decision-card__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.decision-more { padding-top: 1px; }

/* 换资源展开区 */
.adjust-panel { display: grid; gap: 9px; padding: 11px 12px; border: 1px dashed var(--teal); border-radius: 10px; background: #fbfdfc; }
.adjust-panel__head { display: grid; gap: 3px; }
.adjust-panel__head b { font-size: 12.5px; }
.adjust-panel__head span { font-size: 11px; }
.alt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); grid-auto-rows: 1fr; align-items: stretch; gap: 10px; }
.alt-card { display: flex; flex-direction: column; align-items: stretch; gap: 7px; height: 100%; min-height: 216px; box-sizing: border-box; padding: 12px; border: 1px solid var(--line); border-radius: 11px; background: var(--paper); }
.alt-card.resource-card--recommended { border-color: #83b9a0; background: #f3faf6; }
.alt-card.resource-card--caution { border-color: #dfc38c; background: #fffaf0; }
.alt-card.resource-card--not-recommended { border-color: #dca39d; background: #fff6f5; }
.resource-card__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.recommendation-badge { flex: 0 0 auto; padding: 3px 8px; border-radius: 999px; font-size: 10px; font-weight: 650; }
.recommendation-badge.resource-card--recommended { background: #dcefe4; color: #276347; }
.recommendation-badge.resource-card--caution { background: #f7ebcf; color: #805d1f; }
.recommendation-badge.resource-card--not-recommended { background: #f5dedb; color: #9a4239; }
.alt-card h3 { margin: 0; font-size: 13px; }
.alt-card p { margin: 0; font-size: 11px; }
.alt-card__why { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 4; color: #55635d; font-size: 11px; line-height: 1.6; }
.alt-card :deep(.el-button) { margin-top: auto; align-self: flex-start; }

/* 详情 Tab */
.detail-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.detail-tabs button { padding: 5px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 11px; cursor: pointer; }
.detail-tabs button.active { border-color: var(--teal); background: #f1f8f4; color: var(--teal-dark); }
.detail-body { display: grid; gap: 8px; margin-top: 8px; padding: 10px 12px; border-radius: 10px; background: var(--panel-soft); }
.detail-body p { margin: 0; color: #45524c; font-size: 12px; line-height: 1.8; }
.check-row, .constraint-row { display: flex; flex-wrap: wrap; gap: 6px; }
.check-row span { padding: 3px 9px; border-radius: 999px; background: #eaf4ef; color: #2f6f60; font-size: 10px; }
.constraint-row span { display: flex; gap: 6px; padding: 4px 9px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 10px; }
.constraint-row b { color: var(--ink); font-weight: 600; }

/* 候选产品卡 */
.candidate-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; }
.candidate-card { display: grid; min-width: 0; overflow: hidden; border: 1px solid var(--line); border-radius: 11px; background: var(--paper); }
.candidate-card__body { min-width: 0; display: grid; gap: 8px; padding: 12px; align-content: start; }
.candidate-card header { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.candidate-card h3 { margin: 0; font-size: 13px; line-height: 1.4; }
.candidate-card header b { color: var(--teal-dark); font-family: var(--font-mono); font-size: 14px; white-space: nowrap; }
.candidate-card__body p { margin: 0; }
.candidate-relation { justify-self: start; padding: 3px 8px; border-radius: 999px; background: #f1f8f4; color: #2f6f60; font-size: 10px; }
.candidate-card__exp { color: #45524c; font-size: 11px; line-height: 1.6; }
.candidate-card__figures { color: var(--muted); font-size: 10.5px; }
.visitor-preview-frame { display: block; width: 100%; height: 720px; min-height: 600px; overflow: hidden; border: 1px solid var(--line); border-radius: 10px; background: #fff; }
.batch-apply-fold,.copy-subsection { display: grid; gap: 8px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: #fbfdfc; }
.batch-apply-fold summary,.copy-subsection summary { cursor: pointer; color: var(--teal-dark); font-size: 11.5px; font-weight: 650; }
.batch-apply-fold p { margin: 0; font-size: 11px; }
.batch-room-select { width: min(100%, 680px); margin-right: 8px; }
.batch-result { display: grid; gap: 4px; color: #52645a; font-size: 11px; }
.batch-result p { margin: 0; }
.copy-editor { display: grid; gap: 10px; padding: 12px; border: 1px solid #bed7ca; border-radius: 10px; background: #f7fbf9; }
.copy-editor > header { display: flex; justify-content: space-between; gap: 8px; color: var(--teal-dark); font-size: 12px; }
.copy-editor > header span { color: var(--muted); font-size: 10px; }
.copy-field { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; align-items: start; padding: 8px 0; border-bottom: 1px solid #e5eeea; }
.copy-field label { grid-column: 1 / -1; color: #53645d; font-size: 10.5px; font-weight: 650; }
.copy-field :deep(.el-input) { min-width: 0; }
.copy-field :deep(.el-button) { white-space: nowrap; }
.copy-day { display: grid; gap: 6px; margin-top: 9px; }
.copy-day > b { color: var(--teal-dark); font-size: 11px; }
.copy-editor__actions { display: flex; gap: 8px; }
.date-room-picker { display: grid; grid-template-columns: minmax(145px, auto) minmax(170px, 220px) minmax(210px, 290px); gap: 10px; align-items: center; padding: 1px 0 3px; }
.date-room-picker__label { display: grid; gap: 3px; }
.date-room-picker__label b { color: var(--ink); font-size: 12px; }
.date-room-picker__label span { color: var(--muted); font-size: 10.5px; }
.badge-row { display: flex; flex-wrap: wrap; gap: 5px; }
.badge-row span { padding: 2px 7px; border-radius: 999px; background: #eaf4ef; color: #2f6f60; font-size: 9.5px; }
.candidate-card__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }

/* 执行摘要 */
.summary-list { display: grid; gap: 6px; margin: 10px 0 0; padding: 0; list-style: none; }
.summary-list li { display: flex; align-items: baseline; gap: 8px; padding: 8px 11px; border-left: 2px solid #cfe2d9; background: #f7fbf9; }
.summary-list b { color: #2f6f60; font-size: 12px; font-weight: 600; }
.summary-list span { color: #55635d; font-size: 11px; }
.local-loading { padding: 11px 12px; border: 1px dashed var(--teal); border-radius: 9px; background: #f7fbf9; color: var(--teal-dark); font-size: 12px; }
.source-plan { margin: 0; padding: 8px 11px; border-radius: 9px; background: #f7fbf9; color: #55635d; font-size: 11.5px; }
.tech-fold { margin-top: 12px; }
.tech-fold summary { cursor: pointer; color: var(--muted); font-size: 11px; }
.trace-list { display: grid; gap: 5px; margin: 8px 0 0; padding: 0; list-style: none; }
.trace-list li { display: grid; grid-template-columns: 120px minmax(0, 1fr) auto; gap: 8px; align-items: baseline; padding: 6px 10px; border-left: 2px solid #cfe2d9; background: #f7fbf9; font-size: 11px; }
.trace-list li b { color: #2f6f60; font-size: 10.5px; }
.trace-list li span { color: #55635d; }
.trace-list li em { color: #3f8a69; font-style: normal; font-size: 10px; }
.trace-list li.failed { border-left-color: #e0b473; background: #fff8ec; }
.trace-list li.failed em { color: #a4703a; }

/* 经营证据 */
.evidence-fold summary, .tech-fold summary { cursor: pointer; color: var(--teal-dark); font-size: 12px; }
.evidence-fold summary .muted { font-size: 11px; }
.evidence-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.evidence-tabs button { padding: 4px 11px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 11px; cursor: pointer; }
.evidence-tabs button.active { border-color: var(--teal); background: #f1f8f4; color: var(--teal-dark); }
.evidence-body { display: grid; gap: 8px; margin-top: 10px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 7px; }
.chip-row span { padding: 4px 9px; border-radius: 999px; background: var(--panel-soft); color: var(--ink); font-size: 11px; }
.signal-list { display: grid; gap: 4px; margin: 0; padding-left: 17px; color: #45524c; font-size: 11.5px; line-height: 1.7; }
.reply-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 11px; }
.reply-table th, .reply-table td { padding: 6px 8px; overflow-wrap: anywhere; text-align: left; }
.reply-table th { color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--line); }
.reply-table td { border-bottom: 1px solid var(--panel-soft); }

/* 其他 */
.empty-candidate { display: grid; gap: 8px; justify-items: start; padding: 8px 0; }
.empty-candidate > div { font-size: 22px; color: var(--teal); }
.empty-candidate h3 { margin: 0; font-size: 15px; }
.empty-candidate p { margin: 0; color: var(--muted); font-size: 12px; }
.option-row { display: flex; flex-wrap: wrap; gap: 7px; }
.option-row button { padding: 6px 12px; border: 1px solid var(--teal); border-radius: 999px; background: var(--paper); color: var(--teal-dark); font-size: 11px; cursor: pointer; }
.ghost-link { padding: 4px 8px; border: 0; border-radius: 7px; background: transparent; color: var(--teal-dark); font-size: 11px; text-decoration: none; cursor: pointer; }
.ghost-link:hover { text-decoration: underline; }
.ghost-link.active { background: #f1f8f4; text-decoration: none; }
.refine-row { display: grid; gap: 7px; padding: 10px 0; border-bottom: 1px dashed var(--line); }
.refine-row:last-child { border-bottom: 0; }
.refine-row p { margin: 0; font-size: 12.5px; line-height: 1.7; }
.layer-badge { margin-right: 8px; padding: 2px 8px; border-radius: 999px; background: var(--teal-dark); color: #fff; font-size: 10px; }

/* 吸底输入区 */
.composer { position: sticky; bottom: 10px; z-index: 3; display: grid; gap: 8px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 12px; background: #fff; box-shadow: 0 -8px 24px rgba(18, 20, 19, .1); }
.composer__context { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.context-chip { padding: 4px 10px; border-radius: 999px; background: var(--panel-soft); color: var(--muted); font-size: 11px; }
.context-chip.is-editing { background: #fff4ec; color: #9a6427; }
.context-chip button { margin-left: 8px; border: 0; background: transparent; color: #c9550a; font-size: 11px; cursor: pointer; }
.composer__quick { display: flex; flex-wrap: wrap; gap: 6px; }
.composer__quick button { padding: 4px 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 10.5px; cursor: pointer; }
.composer__quick button:hover { border-color: var(--teal); color: var(--teal-dark); }
.composer__main { display: flex; gap: 8px; align-items: flex-end; }
.composer__main textarea { flex: 1; min-width: 0; min-height: 44px; max-height: 140px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 11px; background: transparent; color: var(--ink); font: 13px/1.6 var(--font-sans); resize: none; outline: none; }
.composer__main textarea:focus { border-color: var(--teal); box-shadow: 0 0 0 3px rgba(35, 121, 108, .12); }
.composer__main button { flex: 0 0 auto; height: 44px; padding: 0 22px; border: 0; border-radius: 11px; background: var(--teal-dark); color: #fff; font-size: 13px; font-weight: 650; cursor: pointer; }
.composer__main button:disabled { opacity: .5; cursor: not-allowed; }

/* 操作历史 Drawer */
.log-list { display: grid; gap: 10px; }
.log-group { display: grid; gap: 6px; padding-bottom: 4px; }
.log-group__head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; color: var(--teal-dark); font-size: 11.5px; }
.log-group__head span { color: var(--muted); font-size: 10px; }
.log-item { display: grid; gap: 3px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); }
.log-time { color: var(--muted); font-size: 10.5px; }
.log-item b { font-size: 12.5px; }
.log-item small { color: var(--muted); font-size: 10px; }
.log-item p { margin: 0; color: #45524c; font-size: 11.5px; line-height: 1.7; }
.log-diffs { display: grid; gap: 3px; color: #45524c; font-size: 11px; line-height: 1.6; }
.log-diffs span { display: block; }
.log-diffs span b { margin-right: 4px; color: var(--muted); font-size: 10.5px; }
.log-diffs del { color: #9a6d6d; text-decoration: line-through; }

@media (max-width: 1000px) {
  .stage-bar ol { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .key-evidence { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .decision-card__top { grid-template-columns: 1fr; }
  .decision-card__top > img, .decision-card__ph { min-height: 168px; }
}
@media (max-width: 700px) {
  .candidate-grid { grid-template-columns: 1fr; }
  .visitor-preview-frame { height: 720px; min-height: 580px; }
  .date-room-picker { grid-template-columns: 1fr; }
  .plan-grid { grid-template-columns: 1fr; }
  .figure-row { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; padding: 9px 7px; font-size: 10px; }
  .figure-row b { font-size: 10.5px; }
  .copy-editor > header { flex-direction: column; }
  .copy-field { grid-template-columns: 1fr; }
  .stage-bar ol { grid-template-columns: 1fr; }
  .trace-list li { grid-template-columns: 1fr; }
}
</style>
