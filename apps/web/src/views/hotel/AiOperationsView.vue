<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
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
// 只允许一个「经营证据」分类展开，避免页面被多块原始数据同时撑长。
const panel = ref<'' | 'inventory' | 'resources' | 'orders' | 'weather' | 'knowledge'>('')
const evidenceFold = ref<HTMLDetailsElement | null>(null)
const evidenceLoaded = ref<string[]>([])
const evidenceLoading = ref('')
const evidenceError = ref('')
const evidenceRequests = new Map<string, Promise<void>>()
// 本次会话真正生成出来的候选：生成后直接进入「预览与发布」，不再单独占用一个确认步骤。
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
  if (overview.value.weather?.usable === false) return '天气待核验'
  if (!overview.value.weather) return '按需查看'
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
const roomEvidenceTypeCount = computed(() => new Set(roomEvidenceRows.value.map((room) => room.room_type)).size)
const resourceEvidenceRows = computed<AnyRecord[]>(() => (insights.value.resource_evidence || []) as AnyRecord[])
const serviceEvidenceRows = computed<AnyRecord[]>(() => (insights.value.service_evidence || []) as AnyRecord[])
const weatherEvidenceRows = computed<AnyRecord[]>(() => (overview.value.weather_forecasts || []) as AnyRecord[])
const recentOrderSummary = computed<AnyRecord>(() => (orders.value.recent || {}) as AnyRecord)
const primarySpec = computed<AnyRecord | null>(() => (advisor.value?.primary as AnyRecord) || null)
const judgement = computed<AnyRecord>(() => (advisor.value?.judgement as AnyRecord) || {})
const primaryExperience = computed<AnyRecord | null>(() => ((primarySpec.value?.experiences as AnyRecord[]) || [])[0] || null)
// 顶部只显示主推与备选；完整的当前选择只在下方展开，避免同一结论重复出现。
const rawPlans = computed<AnyRecord[]>(() => ((judgement.value.plans as AnyRecord[]) || []).slice(0, 4))
function planKey(item: AnyRecord) {
  return [item.target_date, item.room_type, item.resource_name].map((value) => String(value || '')).join('|')
}
const selectedPlanKey = computed(() => {
  const primary = primarySpec.value
  return primary ? planKey({ target_date: primary.target_date, room_type: primary.room_type, resource_name: primary.experiences?.[0]?.name }) : ''
})
function concisePlanReason(item: AnyRecord) {
  const text = String(item.fit_reason || planReason(item) || '').trim()
  const first = text.split(/[；。]/).map((part) => part.trim()).find(Boolean) || ''
  const compact = first.replace(/^(?:推荐理由|适配点|主推理由|备选特点)\s*(?:[：:]\s*|\s+)/, '')
  return compact.length > 42 ? compact.slice(0, 42) + '…' : compact
}
const plans = computed<AnyRecord[]>(() => {
  const list: AnyRecord[] = rawPlans.value.map((item) => ({
    ...item,
    is_current: selectedPlanKey.value ? planKey(item) === selectedPlanKey.value : Boolean(item.is_current),
    is_ai_primary: Boolean(item.is_ai_primary) || item.label === 'AI主推',
  }))
  return list.filter((item) => !item.is_current || item.is_ai_primary)
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

const stages = [
  { id: 1, label: '经营分析', hint: '查看并询问经营数据' },
  { id: 2, label: '产品方案', hint: '比较方向 · 调整当前方案' },
  { id: 3, label: '预览与发布', hint: '确认候选 · 检查游客端成品' },
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
    // 进入产品方案前补齐四类经营证据：AI 执行摘要据此给出真实数字，而不是占位结论。
    await Promise.allSettled([
      ensureEvidence('inventory'),
      ensureEvidence('orders'),
      ensureEvidence('resources'),
      ensureEvidence('weather'),
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
    evidenceLoading.value = section
    evidenceError.value = ''
    try {
      if (section === 'inventory') {
        const rooms = await hotelApi.rooms({ from_date: localDateKey(new Date()), days: 17 })
        inventoryRooms.value = rooms.data as AnyRecord[]
      } else if (section === 'resources') {
        const response = await hotelApi.aiOverview({ section: 'resources' })
        overview.value = { ...overview.value, ...response.data }
      } else if (section === 'orders') {
        orders.value = (await hotelApi.ordersOverview()).data
      } else if (section === 'weather') {
        const response = await hotelApi.aiOverview({ section: 'weather' })
        overview.value = { ...overview.value, ...response.data }
      } else if (section === 'knowledge') {
        const response = await hotelApi.aiOverview({ section: 'knowledge' })
        overview.value = { ...overview.value, ...response.data }
      }
      evidenceLoaded.value = [...new Set([...evidenceLoaded.value, section])]
    } catch (error) {
      evidenceError.value = errorMessage(error)
    } finally {
      evidenceLoading.value = ''
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
function localDateKey(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}
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

async function toggleEvidence(section: typeof panel.value) {
  panel.value = panel.value === section ? '' : section
  if (panel.value && evidenceFold.value) {
    evidenceFold.value.open = true
    await ensureEvidence(panel.value)
  }
}

async function selectEvidence(section: typeof panel.value) {
  panel.value = section
  if (evidenceFold.value) evidenceFold.value.open = true
  if (section) await ensureEvidence(section)
}

async function openEvidence(section: typeof panel.value) {
  selectedStage.value = 1
  panel.value = section
  await nextTick()
  if (evidenceFold.value) evidenceFold.value.open = true
  if (section) await ensureEvidence(section)
}
function askOperatingQuestion(question: string) {
  brief.value = question
  void submit()
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

function weatherScenarioLabel(row: AnyRecord) {
  if (!row.usable) return '待核验'
  const labels: Record<string, string> = { RAIN: '有雨', SUNNY: '晴', CLOUDY: '多云' }
  return labels[String(row.scenario || '')] || '待核验'
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
      text: `房型「${room.resource_name}」${product.target_date}${remaining === '—' || remaining === null || remaining === undefined ? '' : ` 余量 ${remaining} 间`}，可住 ${product.party_size} 人；据房量与体验席位核定本产品最多可售 ${product.sale_quantity ?? '—'} 套。`,
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

// 「AI 执行摘要」只出现一次：这一轮读了什么、校验了什么，每行一条结论并附可核查依据。
const execSummary = computed<AnyRecord[]>(() => {
  const roomCount = roomEvidenceRows.value.length
  const orders = recentOrderSummary.value as AnyRecord
  const confirmed = Number(orders.confirmed_count ?? recentConfirmedRows.value.length ?? 0)
  const topCrowd = ((orders.top_crowds || []) as AnyRecord[])[0]
  const partnerCount = resourceEvidenceRows.value.length
  const serviceCount = serviceEvidenceRows.value.length
  const usableWeather = weatherEvidenceRows.value.filter((row) => row.usable).length
  const primary = primarySpec.value
  const rows: AnyRecord[] = [
    {
      key: 'inventory',
      label: '房态已读取',
      done: dataReady.value,
      headline: roomCount
        ? `未来 ${pressure.value.window_days ?? 17} 天 · ${roomEvidenceDateCount.value} 个日期 × ${roomEvidenceTypeCount.value} 种房型 · 共 ${roomEvidenceTotal.value} 间夜`
        : `未来 ${pressure.value.window_days ?? 17} 天 · 待消化 ${pressure.value.unsold_room_nights ?? 0} 间夜 · ${pressure.value.room_type_count ?? 0} 种房型`,
      basis: focusRoom.value
        ? `余量最高：${focusRoom.value.room_type} ${focusRoom.value.remaining} 间（${focusRoom.value.target_date}） · 数据来源：客房库存`
        : '数据来源：客房库存接口，按所选日期与房型核定可售套数',
    },
    {
      key: 'orders',
      label: '客群需求已分析',
      done: evidenceLoaded.value.includes('orders'),
      headline: !evidenceLoaded.value.includes('orders')
        ? '待读取订单明细：展开后可给出近 15 天成交额与最集中客群'
        : confirmed
          ? `近 15 天已确认 ${confirmed} 单 · 成交 ¥${orders.confirmed_revenue ?? recentConfirmedRevenue.value} · 最集中：${crowdLabel(topCrowd?.target_crowd)}（${topCrowd?.confirmed_orders ?? 0} 单）`
          : '近 15 天暂无确认成交，按房态与资源适配推断客群',
      basis: !evidenceLoaded.value.includes('orders')
        ? '数据来源：展开「经营数据明细 → 订单数据」后按确认订单统计'
        : confirmed
          ? '数据来源：确认订单（含提交时价格快照）；客群取自产品目标客群'
          : '数据来源：订单接口已读取，样本不足时不推断主力客群',
    },
    {
      key: 'resources',
      label: '合作资源已匹配',
      done: evidenceLoaded.value.includes('resources'),
      headline: !evidenceLoaded.value.includes('resources')
        ? `待读取合作资源明细：重点日期可组包 ${pressure.value.available_resource_count ?? '—'} 个`
        : partnerCount || serviceCount
          ? `${partnerCount} 项可组包体验 · ${serviceCount} 项酒店权益 · 重点日期可组包 ${pressure.value.available_resource_count ?? '—'} 个`
          : `已读取合作资源与酒店权益（可组包 ${pressure.value.available_resource_count ?? '—'} 个）`,
      basis: evidenceLoaded.value.includes('resources')
        ? '数据来源：合作资源余量、结算价、场次、室内外标签与是否允许组包'
        : '数据来源：展开「经营数据明细 → 合作资源」后按余量、结算价与场次核对',
    },
    {
      key: 'weather',
      label: '天气与路线已核对',
      done: evidenceLoaded.value.includes('weather'),
      headline: !evidenceLoaded.value.includes('weather')
        ? '待读取天气明细：展开后按日给出降雨概率与温度'
        : usableWeather
          ? `杭州未来 ${weatherEvidenceRows.value.length} 天逐日预报，其中 ${usableWeather} 天可用 · 当前：${weatherLabel.value}`
          : `当前：${weatherLabel.value} · 天气未知时只提示核验，不阻断生成`,
      basis: evidenceLoaded.value.includes('weather')
        ? '数据来源：天气服务；降雨日优先室内资源，并保留可替换路线'
        : '数据来源：展开「经营数据明细 → 天气预测」后按日核对；未知天气不阻断生成',
    },
    {
      key: 'plan',
      label: primary ? '当前方案可生成候选' : '当前条件暂无推荐组合',
      done: Boolean(primary),
      headline: primary
        ? `${primary.product_name || '当前方案'} · 建议售价 ¥${primary.price} · 可售 ${primary.max_sellable} 套 · 毛利率 ${primary.margin}%`
        : (judgement.value.text || '可以先调整日期、客群、体验或价格目标后重新计算'),
      basis: primary
        ? '已校验：库存 → 资源名额 → 成本 → 最低合法价 → 毛利率，全部通过后才允许生成候选产品'
        : '调整条件后重新计算，任何一步校验失败都会说明原因并保留上一版方案',
    },
  ]
  return rows
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

// 当前方案的默认视图：只保留四条能直接支撑决策的事实，长行程与推荐逻辑默认折叠。
const primaryEvidence = computed<AnyRecord[]>(() => {
  const primary = primarySpec.value
  if (!primary) return []
  const orders = recentOrderSummary.value as AnyRecord
  const topCrowd = ((orders.top_crowds || []) as AnyRecord[])[0]
  const confirmed = Number(orders.confirmed_count ?? 0)
  return [
    { label: '库存压力', text: focusRoom.value ? `${focusRoom.value.room_type} 余 ${focusRoom.value.remaining} 间（${focusRoom.value.target_date}）` : `待消化 ${pressure.value.unsold_room_nights ?? 0} 间夜` },
    { label: '客群依据', text: confirmed && topCrowd ? `近 15 天${crowdLabel(topCrowd.target_crowd)}成交最集中（${topCrowd.confirmed_orders} 单）` : `${crowdLabel(primary.crowd)} · 按房型可住人数与资源适配` },
    { label: '资源容量', text: primary.bottleneck ? `瓶颈：${primary.bottleneck}` : `可售 ${primary.max_sellable} 套（体验名额充足）` },
    { label: '天气', text: weatherLabel.value },
  ]
})

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

const AUTO_BRIEF = '结合已读取的房态、近15天订单和合作资源，按经营分析阶段记录的关注方向给出产品推荐；如果没有可用组合，请说明具体原因和需要补充的数据'

async function autoStart() {
  submitting.value = true
  processingMessage.value = '正在结合房态、近15日成交、合作资源与经营分析关注点生成方案方向…'
  try {
    const conversationId = await ensureConversation()
    const response = await hotelApi.advisor(Number(conversationId), AUTO_BRIEF, true)
    const data = response.data
    mergeConversation(data.conversation as AnyRecord)
    advisor.value = data.advisor as AnyRecord
    const nextPrimary = (advisor.value?.primary as AnyRecord) || null
    previousPrimary.value = nextPrimary
    if (nextPrimary && !targetInventoryKey.value) targetInventoryKey.value = `${nextPrimary.target_date}|${nextPrimary.room_type}`
    selectedStage.value = 2
    advisorAnalysisSignature.value = analysisSignature()
    advisorLoadedThisVisit.value = true
  } catch (error) { showToast(errorMessage(error)) }
  finally { submitting.value = false }
}

onMounted(async () => { selectedStage.value = 1; await load() })
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
            <div><b>{{ s.label }}</b><small>{{ s.hint }}</small></div>
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

    <!-- ② 经营状态 -->
    <section class="fact-strip">
      <button type="button" class="fact-card" :class="{ active: panel === 'inventory' }" @click="openEvidence('inventory')">
        <span>待消化房量</span>
        <strong>{{ dataReady ? `${pressure.unsold_room_nights ?? 0} 间` : (loadError ? '读取失败' : '读取中') }}</strong>
        <small>{{ dataReady ? `未来 ${pressure.window_days ?? 17} 天 · ${pressure.room_type_count ?? 0} 种房型` : (loadError ? '请重试' : '正在读取客房库存') }}</small>
      </button>
      <button type="button" class="fact-card" :class="{ active: panel === 'inventory' }" @click="openEvidence('inventory')">
        <span>重点库存</span>
        <strong>{{ dataReady ? (focusRoom ? `${focusRoom.room_type} ${focusRoom.remaining} 间` : '暂无可售房量') : (loadError ? '读取失败' : '读取中') }}</strong>
        <small>{{ dataReady ? (focusRoom?.target_date || '未来日期暂无可售客房') : (loadError ? '请重试' : '正在读取库存分布') }}</small>
      </button>
      <button type="button" class="fact-card" :class="{ active: panel === 'resources' }" @click="openEvidence('resources')">
        <span>可用合作资源</span>
        <strong>{{ dataReady ? `${pressure.available_resource_count ?? 0} 个` : (loadError ? '读取失败' : '读取中') }}</strong>
        <small>{{ dataReady ? '重点日期可组包' : (loadError ? '请重试' : '正在读取合作资源') }}</small>
      </button>
      <div class="fact-actions">
        <span class="weather-chip">杭州 · {{ weatherLabel }}</span>
        <span v-if="overview.weather && overview.weather.usable === false" class="fact-warn">天气未核验，方案仍可生成并附天气提示</span>
      </div>
    </section>

    <div v-if="loadError" class="panel empty-state">经营数据暂时无法读取：{{ loadError }} <el-button type="primary" @click="load">重新加载</el-button></div>

    <!-- ③ 经营分析：数据、判断与产品影响留在各自证据页签中 -->
    <section v-if="stageIndex === 1" class="panel stage-panel">
      <div class="stage-panel__head"><h2>经营数据分析</h2><span class="muted">查看经营依据，也可以直接询问数据</span></div>
      <div v-if="analysisMessages.length" class="analysis-chat" aria-live="polite">
        <article v-for="(message, index) in analysisMessages" :key="`${message.created_at}-${index}`" class="analysis-message" :class="`analysis-message--${message.role}`">
          <b>{{ message.role === 'user' ? '你的问题' : '经营分析' }}</b>
          <p>{{ message.content }}</p>
        </article>
      </div>
      <details ref="evidenceFold" class="evidence-fold">
        <summary>经营数据明细</summary>
        <div class="evidence-tabs">
          <button type="button" :class="{ active: panel === 'inventory' }" @click="selectEvidence('inventory')">房态数据</button>
          <button type="button" :class="{ active: panel === 'resources' }" @click="selectEvidence('resources')">合作资源</button>
          <button type="button" :class="{ active: panel === 'orders' }" @click="selectEvidence('orders')">订单数据</button>
          <button type="button" :class="{ active: panel === 'weather' }" @click="selectEvidence('weather')">天气预测</button>
          <button type="button" :class="{ active: panel === 'knowledge' }" @click="selectEvidence('knowledge')">知识库</button>
        </div>
        <div v-if="panel && evidenceLoading === panel" class="evidence-loading">正在读取此分类的数据…</div>
        <div v-else-if="panel && evidenceError" class="evidence-loading evidence-loading--error">
          {{ evidenceError }} <el-button link type="primary" @click="retryEvidence">重试</el-button>
        </div>

        <div v-if="panel === 'inventory' && evidenceLoaded.includes('inventory')" class="evidence-body">
          <div class="chip-row">
            <span>未来 {{ pressure.window_days ?? 17 }} 天当前可售 {{ roomEvidenceTotal }} 间夜</span>
            <span>{{ roomEvidenceDateCount }} 个日期 · {{ roomEvidenceTypeCount }} 种房型</span>
            <span v-if="focusRoom">待售货值最高 {{ focusRoom.room_type }} {{ focusRoom.remaining }} 间（{{ focusRoom.target_date }}）</span>
          </div>
          <table v-if="roomEvidenceRows.length" class="reply-table">
            <thead><tr><th>日期</th><th>房型</th><th>当前余量</th><th>参考价</th><th>适合人数</th><th>状态</th></tr></thead>
            <tbody><tr v-for="row in roomEvidenceRows.slice(0, 45)" :key="row.id"><td>{{ row.available_date }}</td><td>{{ row.room_type }}</td><td>{{ row.available_count }} 间</td><td>¥{{ row.normal_price }}</td><td>{{ row.max_guests }} 人</td><td>{{ row.status === 'AVAILABLE' ? '可售' : statusLabel(row.status) }}</td></tr></tbody>
          </table>
          <div class="evidence-analysis"><b>分析与产品影响</b><p>当前库存接口提供逐日可售间数、房型、参考价与入住人数上限；产品生成据所选日期和房型核定可售套数。系统尚无总房量及历史每日库存快照，因此这里不把可售间数包装成预测入住率。</p><small>数据来源：客房库存 · {{ insights.as_of || '当前' }}读取</small></div>
        </div>

        <div v-if="panel === 'resources' && evidenceLoaded.includes('resources')" class="evidence-body">
          <div class="chip-row"><span>未来日期内 {{ resourceEvidenceRows.length }} 项合作体验可组包</span><span>酒店权益 {{ serviceEvidenceRows.length }} 项</span><span>含历史产品关联次数与近15日确认订单</span></div>
          <table v-if="resourceEvidenceRows.length" class="reply-table">
            <thead><tr><th>日期</th><th>合作资源</th><th>库存 / 结算价</th><th>适配客群</th><th>关联产品</th><th>近15日成交</th></tr></thead>
            <tbody><tr v-for="row in resourceEvidenceRows.slice(0, 35)" :key="row.id"><td>{{ row.available_date }}</td><td><b>{{ row.name }}</b><small class="table-subline">{{ row.merchant_name || row.category }} · {{ row.indoor ? '室内' : '户外' }} · {{ row.address || '地址待补充' }}</small></td><td>{{ row.remaining_capacity }} 份 · ¥{{ row.settlement_price }}</td><td>{{ crowdListLabel(row.suitable_crowds) }}</td><td>{{ row.product_count }} 个</td><td>{{ row.recent_confirmed_orders }} 单</td></tr></tbody>
          </table>
          <table v-if="serviceEvidenceRows.length" class="reply-table"><thead><tr><th>日期</th><th>酒店服务</th><th>余量</th><th>适用客群</th></tr></thead><tbody><tr v-for="row in serviceEvidenceRows.slice(0, 20)" :key="row.id"><td>{{ row.available_date }}</td><td>{{ row.name }}</td><td>{{ row.available_quantity }} 份</td><td>{{ crowdListLabel(row.suitable_crowds) }}</td></tr></tbody></table>
          <p v-if="!resourceEvidenceRows.length && !serviceEvidenceRows.length" class="muted">当前日期范围内没有可用合作资源或酒店权益。</p>
          <div class="evidence-analysis"><b>分析与产品影响</b><p>名额决定体验可组合的日期与产品上限；关联产品数反映资源曾进入多少个产品，近15日成交数按确认订单回溯。可用名额为零或未开放组包的资源不会进入推荐。</p><small>数据来源：合作资源、酒店服务、产品组成及确认订单记录</small></div>
        </div>

        <div v-if="panel === 'orders' && evidenceLoaded.includes('orders')" class="evidence-body">
          <div class="chip-row">
            <span>近 15 天已确认 {{ recentOrderSummary.confirmed_count ?? recentConfirmedRows.length }} 单</span>
            <span>成交 ¥{{ recentConfirmedRevenue }}</span>
            <span>订单最多客群 {{ crowdLabel(recentOrderSummary.top_crowds?.[0]?.target_crowd) || '暂无' }}</span>
            <span>平均订单 ¥{{ recentOrderSummary.average_order_value ?? '—' }}</span>
          </div>
          <div class="evidence-split">
            <div><b>近期成交产品</b><table class="reply-table"><thead><tr><th>产品</th><th>确认单</th><th>成交金额</th></tr></thead><tbody><tr v-for="row in (recentOrderSummary.top_products || [])" :key="row.product_id"><td>{{ row.product_name }}</td><td>{{ row.confirmed_orders }}</td><td>¥{{ row.revenue }}</td></tr><tr v-if="!recentOrderSummary.top_products?.length"><td colspan="3" class="muted">近15日暂无成交产品</td></tr></tbody></table></div>
            <div><b>近期客群结构</b><table class="reply-table"><thead><tr><th>客群</th><th>确认单</th><th>占比</th></tr></thead><tbody><tr v-for="row in (recentOrderSummary.top_crowds || [])" :key="row.target_crowd"><td>{{ crowdLabel(row.target_crowd) }}</td><td>{{ row.confirmed_orders }}</td><td>{{ row.share }}%</td></tr><tr v-if="!recentOrderSummary.top_crowds?.length"><td colspan="3" class="muted">暂无足够成交样本判断客群</td></tr></tbody></table></div>
          </div>
          <table v-if="recentOrderRows.length" class="reply-table">
            <thead><tr><th>产品</th><th>类别</th><th>金额</th><th>日期</th><th>状态</th></tr></thead>
            <tbody><tr v-for="row in recentOrderRows" :key="row.id"><td>{{ row.product_name }}</td><td>{{ categoryLabel(row.category) }}</td><td>¥{{ row.amount }}</td><td>{{ String(row.confirmed_at || row.created_at || '').slice(0, 10) }}</td><td>{{ statusLabel(row.status) }}</td></tr></tbody>
          </table>
          <div v-if="!recentOrderRows.length" class="muted">近15天没有新订单记录。</div>
          <div class="evidence-analysis"><b>分析与产品影响</b><p v-if="recentOrderSummary.confirmed_count">成交分布按订单确认时间统计，客群来自已成交产品的目标客群。{{ recentOrderSummary.top_crowds?.length ? `当前成交较集中的客群是${crowdLabel(recentOrderSummary.top_crowds[0].target_crowd)}；` : '' }}生成产品时可将此作为方向参考，不会覆盖用户选择。</p><p v-else>近15日没有确认成交，系统不会从零样本推断主力客群；推荐仍可基于当前房态、可用资源和天气生成。</p><small>金额优先读取提交时的价格快照；旧记录缺少快照时按当前产品价估算（{{ recentOrderSummary.estimated_amount_count ?? 0 }} 笔）。</small></div>
        </div>

        <div v-if="panel === 'weather' && evidenceLoaded.includes('weather')" class="evidence-body">
          <div class="chip-row"><span>杭州未来 {{ weatherEvidenceRows.length }} 天逐日预报</span><span>来源：{{ weatherEvidenceRows.find((row) => row.usable)?.source_name || '天气服务' }}</span><span>天气用于体验适配，不作为生成硬性限制</span></div>
          <table class="reply-table"><thead><tr><th>日期</th><th>天气</th><th>温度</th><th>降雨概率</th><th>路线建议</th></tr></thead><tbody><tr v-for="row in weatherEvidenceRows" :key="row.target_date"><td>{{ row.target_date }}</td><td>{{ weatherScenarioLabel(row) }}</td><td>{{ row.temperature_min ?? '—' }}–{{ row.temperature_max ?? '—' }}℃</td><td>{{ row.precipitation_probability == null ? '—' : `${row.precipitation_probability}%` }}</td><td>{{ !row.usable ? '待核验；不阻断生成' : row.scenario === 'RAIN' ? '优先室内，户外保留替代安排' : row.scenario === 'SUNNY' ? '可安排户外，注意防晒补水' : '室内外均可，结合路线距离安排' }}</td></tr><tr v-if="!weatherEvidenceRows.length"><td colspan="5" class="muted">当前没有逐日天气记录。</td></tr></tbody></table>
          <div class="evidence-analysis"><b>分析与产品影响</b><p>降雨概率较高时，推荐排序会提高室内资源与有替代安排的路线；晴好天气可增加户外路线权重。天气未知或超出预报范围时只提示核验，不因此阻止产品生成。</p><small>每日预报来自天气服务；未核验日期不会显示为确定天气。</small></div>
        </div>

        <div v-if="panel === 'knowledge' && evidenceLoaded.includes('knowledge')" class="evidence-body">
          <div class="chip-row"><span>地点知识 {{ knowledgeTotal }} 条</span><span>仅作非售卖路线参考</span><span>关联成交统计：暂无结构化地点关联</span></div>
          <table class="reply-table">
            <thead><tr><th>地点</th><th>适用信息</th><th>开放 / 预约</th><th>核验与来源</th></tr></thead>
            <tbody><tr v-for="row in (overview.knowledge || []).slice(0, 12)" :key="row.name"><td><b>{{ row.name }}</b><small class="table-subline">{{ row.address || row.area }}</small></td><td>{{ row.category_label || row.category }} · {{ crowdListLabel(row.suitable_crowds) }} · {{ row.weather_adaptations_label || row.weather_adaptations || '天气未标注' }}</td><td>{{ row.opening_hours || '开放时间未登记' }}<small class="table-subline">{{ row.reservation_notice || '无预约说明' }}</small></td><td>{{ row.verification_status === 'ACTIVE' ? '已核验' : row.verification_status === 'STALE' ? '信息待更新' : '需复核' }}<small class="table-subline">{{ row.source_name || '来源未登记' }} · {{ row.verified_at || row.source_updated_at || '无核验日期' }}</small></td></tr></tbody>
          </table>
          <div class="evidence-analysis"><b>分析与产品影响</b><p>知识库补充地点地址、开放时间、适配客群与天气信息，用于丰富非售卖路线和说明行程衔接；正式包含的权益仍必须来自有库存和结算价的合作资源或酒店服务。</p><small>当前知识地点没有与产品路线、订单建立结构化外键，因此不展示伪造的历史成交排名。</small></div>
        </div>
      </details>

      <!-- 无方案不等于卡住：分析完成后直接给出原因与可执行的下一步。 -->
      <div v-if="analysisDone && !primarySpec" class="next-step-note">
        <b>经营分析已完成，当前条件没有推荐组合</b>
        <p>{{ judgement.text || '系统已读取房态、订单与合作资源，但按当前日期、客群、体验或价格目标没有满足条件的组合。' }}</p>
        <ul>
          <li v-if="focusRoom">可优先把日期换到 {{ focusRoom.target_date }} 的 {{ focusRoom.room_type }}（余 {{ focusRoom.remaining }} 间）。</li>
          <li v-if="!evidenceLoaded.includes('resources')">合作资源还未读取，刷新资源后再算一次可以排除名额不足。</li>
          <li v-else>若名额不足，可在合作资源池补充资源或允许更多资源组包。</li>
          <li>也可以放宽价格目标或换一个客群，让约束条件更容易满足。</li>
        </ul>
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
    </section>

    <!-- ③ Step 2：产品方案。方向比较 + 当前方案调整，满意后生成候选。 -->
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
          <p class="plan-fit-note" :class="{ caution: String(item.fit_label || '').startsWith('需核对'), negative: item.fit_label === '不建议优先' }"><b>{{ item.is_ai_primary ? '主推理由' : '备选特点' }}</b>{{ concisePlanReason(item) }}</p>
          <el-button v-if="!item.is_current" size="small" plain :disabled="submitting" @click="ask(item.message)">切换为当前方案</el-button>
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

          <div class="key-evidence primary-facts">
            <div v-for="item in primaryEvidence" :key="item.label"><span>{{ item.label }}</span><b>{{ item.text }}</b></div>
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

          <details v-if="primarySpec.itinerary_days?.length" class="advanced-fold itinerary-fold">
            <summary>查看完整行程与转场（{{ primarySpec.itinerary_days.length }} 天）</summary>
            <div class="itinerary-days">
            <article v-for="day in primarySpec.itinerary_days" :key="day.day_index" class="itinerary-day">
              <header><b>{{ day.label }} · {{ day.title }}</b><span>{{ day.date }}</span></header>
              <p class="itinerary-day__summary">{{ day.summary }}</p>
              <div v-for="(item, index) in day.items" :key="String(day.day_index) + '-' + String(index)" class="itinerary-entry">
                <time>{{ item.time || '时间待确认' }}</time>
                <div>
                  <strong>{{ item.title }}</strong>
                  <span v-if="item.route_only" class="route-only-badge">路线建议 · 非套餐权益</span>
                  <p>{{ item.description }}</p>
                  <!-- 不再逐条折叠「路线详情」：地点、时长、区域直接一行显示，核验提示单独一行。 -->
                  <p v-if="item.address || item.duration_text || item.area" class="itinerary-entry__meta">
                    <span v-if="item.address">{{ item.address }}</span>
                    <span v-if="item.duration_text">{{ item.duration_text }}</span>
                    <span v-if="item.area">{{ item.area }}</span>
                  </p>
                  <p v-if="item.notes" class="itinerary-entry__verify">出行前核验：{{ item.notes }}</p>
                </div>
              </div>
              <details v-if="routeForDay(day.day_index)?.legs?.length" class="route-transfer-fold">
                <summary>查看转场与核验</summary>
                <div class="route-transfer-list">
                  <p v-for="leg in (routeForDay(day.day_index)?.legs || [])" :key="leg.from_stop + leg.to_stop">
                    {{ leg.from_stop }} → {{ leg.to_stop }} · {{ leg.distance_label || '交通机动' }}<template v-if="leg.minutes"> · 预留约 {{ leg.minutes }} 分钟</template><template v-else> · 具体地点待定，暂不估算耗时</template>
                    <small>{{ leg.note }}</small>
                  </p>
                </div>
              </details>
            </article>
            </div>
          </details>

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

          <div v-if="activeAdjust === 'resources'" class="adjust-panel">
            <div class="adjust-panel__head"><b>替换当前合作资源</b><span class="muted">保持日期、房型和客群，只替换核心体验；绿色为优先推荐，黄色需要核对，换完会重新跑容量与利润校验。</span></div>
            <div v-if="resourceSwaps.length" class="alt-grid">
              <article v-for="item in resourceSwaps" :key="`swap-${item.name}`" class="alt-card" :class="recommendationClass(item)">
                <div class="resource-card__head">
                  <span class="section-kicker">{{ item.window || '按场次' }}<template v-if="item.fit_label"> · {{ item.fit_label }}</template></span>
                  <span class="recommendation-badge" :class="recommendationClass(item)">{{ recommendationLabel(item) }}</span>
                </div>
                <h3>{{ item.name }}</h3>
                <p class="muted">换后预估价 ¥{{ item.estimated_price }}<template v-if="item.price_delta && Number(item.price_delta) !== 0">（{{ Number(item.price_delta) > 0 ? '涨' : '降' }} ¥{{ Math.abs(Number(item.price_delta)).toFixed(2) }}）</template> · 可售 {{ item.sets }} 套 · 单人成本 ¥{{ item.settlement_price }}</p>
                <p v-if="item.address" class="resource-fit-note">地点：{{ item.address }}</p>
                <p v-if="item.fit_reason" class="resource-fit-note">{{ item.fit_reason }}</p>
                <el-button size="small" plain @click="ask(`${primarySpec.target_date} 的 ${primarySpec.room_type} 换成 ${item.name}`)">换成这个体验</el-button>
              </article>
            </div>
            <p v-else class="muted">当前日期与房型下没有其它可用合作资源：可以到合作资源池为该日期补充资源并允许组包，或换一个日期再看。</p>
          </div>

          <div v-if="activeAdjust === 'route'" class="adjust-panel"><div class="adjust-panel__head"><b>选择路线调整方式</b><span class="muted">先选安排，再由 AI 按场次和天气重新校验。</span></div><div class="option-row"><button type="button" @click="ask('路线留出更多自由时间，晚上体验结束后直接回酒店')">留出自由时间</button><button type="button" @click="ask('优先室内路线，减少户外移动')">优先室内路线</button><button type="button" @click="ask('保持当前体验，只调整先后顺序')">只调先后顺序</button></div></div>

          <div v-if="activeAdjust === 'service'" class="adjust-panel"><div class="adjust-panel__head"><b>选择要增加的体验或酒店权益</b><span class="muted">按客群、场次、天气、余量和路线匹配度排序；绿色优先推荐，红色表示不建议优先。</span></div><div v-if="availableAddResources.length" class="alt-grid"><article v-for="item in availableAddResources" :key="`${item.kind}-${item.id || item.name}`" class="alt-card" :class="recommendationClass(item)"><div class="resource-card__head"><span class="section-kicker">{{ item.kind }}<template v-if="item.fit_label"> · {{ item.fit_label }}</template></span><span class="recommendation-badge" :class="recommendationClass(item)">{{ recommendationLabel(item) }}</span></div><h3>{{ item.name }}</h3><p class="muted">可售 {{ item.sets ?? item.available_quantity ?? '—' }} 套<template v-if="item.window"> · {{ item.window }}</template> · 单人成本 ¥{{ item.settlement_price ?? item.unit_cost ?? '—' }}</p><p v-if="item.address" class="resource-fit-note">地点：{{ item.address }}</p><p v-if="item.fit_reason" class="resource-fit-note">{{ item.fit_reason }}</p><el-button size="small" plain :disabled="item.addable === false" @click="ask(item.kind === '体验' ? `增加体验：${item.name}` : `增加酒店服务：${item.name}`)">{{ item.is_selected ? '已加入' : item.addable === false ? '暂不可加入' : `增加这项${item.kind}` }}</el-button></article></div><p v-else class="muted">当前日期没有已启用组包的合作体验或酒店权益。请在合作资源池添加资源并允许组包，再刷新方案。</p></div>

          <details class="reason-fold"><summary>展开推荐依据与风险</summary><div class="detail-tabs"><button type="button" :class="{ active: detailTab === 'basis' }" @click="detailTab = 'basis'">经营价值</button><button type="button" :class="{ active: detailTab === 'value' }" @click="detailTab = 'value'">收益与容量</button><button type="button" :class="{ active: detailTab === 'risk' }" @click="detailTab = 'risk'">风险与限制</button><button type="button" :class="{ active: detailTab === 'compare' }" @click="detailTab = 'compare'">方案比较</button></div><div class="detail-body"><template v-if="detailTab === 'basis'"><p v-for="item in (primarySpec.reason_sections || [])" :key="item.label"><b>{{ item.label }}：</b>{{ item.text }}</p><p v-if="!primarySpec.reason_sections?.length">{{ logicByTitle['推荐逻辑'] || '按当前房态、近 14 天成交与合作资源容量综合判断。' }}</p></template><template v-else-if="detailTab === 'value'"><p>{{ logicByTitle['酒店经营价值'] || '按建议售价与最大可售量计算收益。' }}</p></template><template v-else-if="detailTab === 'risk'"><p>{{ logicByTitle['风险与约束'] || '容量、场次与天气变化会触发自动复检。' }}</p></template><template v-else><p>{{ primarySpec.not_chosen || '本轮没有其它更高优先级的组合。' }}</p></template></div></details>
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
            <span class="candidate-relation">{{ card.relation }}</span>
            <p class="muted">{{ card.date }} · {{ card.crowd_label }} · {{ card.party }} 人<template v-if="card.quantity !== ''"> · 可售 {{ card.quantity }} 套</template></p>
            <p v-if="card.experiences.length" class="candidate-card__exp">正式体验：{{ card.experiences.join('、') }}</p>
            <p v-if="card.services.length" class="candidate-card__exp">酒店权益：{{ card.services.join('、') }}</p>
            <p class="candidate-card__figures">成本 ¥{{ card.cost }} · 最低合法价 ¥{{ card.floor_price }}<template v-if="card.margin_label"> · 毛利率 {{ card.margin_label }}</template></p>
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

    <!-- AI 执行摘要：整个工作台只出现一次，一行一条结论并附可核查的依据。 -->
    <details class="exec-summary">
      <summary>AI 执行摘要 · 这一轮读了什么、校验了什么（{{ execSummary.length }} 项）</summary>
      <ul>
        <li v-for="row in execSummary" :key="row.key" :class="{ 'is-pending': !row.done }">
          <span class="exec-summary__mark">{{ row.done ? '✓' : '·' }}</span>
          <b>{{ row.label }}</b>
          <span class="exec-summary__detail">{{ row.headline }}</span>
          <small>{{ row.basis }}</small>
        </li>
      </ul>
    </details>

    <!-- ⑤ 无论有没有方案，输入区都固定可用：有方案是调整，没有方案就是规划。 -->
    <form class="composer" @submit.prevent="submit()">
      <div class="composer__context">
        <span v-if="stageIndex === 1 && !primarySpec" class="context-chip">经营数据查询助手 · 问题与关注方向会带入产品方案</span>
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
        <textarea v-model="brief" rows="1" :placeholder="stageIndex === 1 && !primarySpec ? '输入经营问题，例如：近15天哪款产品成交最多？未来哪些房型余量较高？' : '例如：价格控制在 700 以内；换成更适合两人的体验；把下午路线改轻松一些'" @input="growInput" @keydown.enter.exact.prevent="submit()" />
        <button type="submit" :disabled="!brief.trim() || submitting">{{ stageIndex === 1 && !primarySpec ? '查询经营数据' : primarySpec ? '调整方案' : '规划方案' }}</button>
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
/* 所有状态共用同一容器宽度：展开推荐逻辑、候选与表格都不会把页面撑宽。 */
.ai-ops > nav, .ai-ops > section, .ai-ops > div, .ai-ops > details, .ai-ops > form { min-width: 0; max-width: 100%; }
.ai-ops :deep(.reply-table), .reason-list li, .exec-summary li, .candidate-card, .decision-card { overflow-wrap: anywhere; }

/* AI 执行摘要：一行一条结论，并给出可核查的依据；默认折叠。 */
.exec-summary { display: grid; gap: 8px; padding: 11px 13px; border: 1px solid var(--line); border-radius: 11px; background: var(--paper); }
.exec-summary > summary { cursor: pointer; color: var(--teal-dark); font-size: 12px; font-weight: 650; }
.exec-summary ul { display: grid; gap: 6px; margin: 10px 0 0; padding: 0; list-style: none; }
.exec-summary li { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px; min-width: 0; padding: 7px 9px; border-top: 1px solid #eef3f0; font-size: 12.5px; line-height: 1.7; }
.exec-summary li:first-child { border-top: 0; }
.exec-summary__mark { color: #2f6f60; font-weight: 700; }
.exec-summary li b { color: var(--ink); }
.exec-summary__detail { color: #45524c; }
.exec-summary li small { color: var(--muted); font-size: 11.5px; }
.exec-summary li.is-pending .exec-summary__mark { color: var(--muted); }
.exec-summary li.is-pending b, .exec-summary li.is-pending .exec-summary__detail { color: #6b7a74; }
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
.stage-bar b { display: block; font-size: 13px; }
.stage-bar small { display: block; margin-top: 2px; color: var(--muted); font-size: 11.5px; }
.stage-bar li.active { border-color: var(--teal); background: #f1f8f4; }
.stage-bar li.active i { background: var(--teal-dark); color: #fff; }
.stage-bar li.done i { background: #dcece4; color: var(--teal-dark); }

/* 经营指标 */
.fact-strip { display: flex; align-items: stretch; gap: 8px; flex-wrap: wrap; }
.fact-card { flex: 1 1 168px; min-width: 0; display: grid; gap: 2px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); color: var(--ink); text-align: left; cursor: pointer; transition: border-color .18s, background .18s; }
.fact-card:hover { border-color: var(--teal); }
.fact-card.active { border-color: var(--teal); background: #f1f8f4; }
.fact-card span { color: var(--muted); font-size: 11.5px; }
.fact-card strong { font-family: var(--font-mono); font-size: 16px; overflow-wrap: anywhere; }
.fact-card small { color: var(--muted); font-size: 11.5px; }
.fact-actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.weather-chip { padding: 5px 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 12px; white-space: nowrap; }
.fact-warn { padding: 4px 9px; border-radius: 999px; background: #fff6e5; color: #9a6b2a; font-size: 10px; white-space: nowrap; }

/* 分区容器 */
.stage-panel { display: grid; gap: 12px; }
.stage-panel__head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.stage-panel__head h2 { margin: 0; font-size: 15px; }
.analysis-chat { display: grid; gap: 8px; }
.analysis-message { display: grid; gap: 3px; max-width: 92%; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); }
.analysis-message--user { justify-self: end; border-color: #d7e8e1; background: #f2f8f5; }
.analysis-message--assistant { justify-self: start; }
.analysis-message b { color: var(--teal-dark); font-size: 10.5px; }
.analysis-message p { margin: 0; color: var(--ink); font-size: 12px; line-height: 1.7; }
.stage-next { align-items: center; }
/* 处理中：内联提示条，不覆盖步骤条、经营数据与输入区。 */
.work-status { display: flex; align-items: flex-start; gap: 10px; padding: 11px 13px; border: 1px solid #d9e8e1; border-radius: 10px; background: #f5faf7; color: #245e51; }
.work-status b { display: block; font-size: 12px; line-height: 1.6; }
.work-status small { display: block; margin-top: 3px; color: #5d7a70; font-size: 10.5px; line-height: 1.6; }
.next-step-note { display: grid; gap: 8px; padding: 12px 14px; border: 1px dashed var(--teal); border-radius: 11px; background: #f7fbf9; }
.next-step-note > b { color: var(--teal-dark); font-size: 12.5px; }
.next-step-note p { margin: 0; color: #4d5f58; font-size: 12px; line-height: 1.7; }
.next-step-note ul { display: grid; gap: 4px; margin: 0; padding-left: 18px; color: #55635d; font-size: 11.5px; line-height: 1.7; }
.advanced-fold { display: grid; gap: 10px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: #fbfdfc; }
.advanced-fold > summary { cursor: pointer; color: var(--teal-dark); font-size: 11.5px; font-weight: 650; }
.advanced-fold[open] > summary { margin-bottom: 8px; }
.reason-list { display: grid; gap: 5px; margin: 8px 0 0; padding-left: 0; list-style: none; color: #45524c; font-size: 11.5px; line-height: 1.7; }
.reason-list li { display: block; overflow-wrap: anywhere; }
.reason-list b { color: #2f6053; }
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
.plan-fit-note,.resource-fit-note { margin: 0; color: #486158; font-size: 12.5px; line-height: 1.65; }
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
.itinerary-day > header { display: flex; justify-content: space-between; gap: 9px; color: var(--teal-dark); font-size:  14px; }
.itinerary-day > header span { color: var(--muted); font-family: var(--font-mono); }
.itinerary-day__summary { margin: 0; color: var(--muted); font-size:  14px; line-height: 1.65; }
.itinerary-entry { display: grid; grid-template-columns:  92px minmax(0, 1fr); gap: 10px; padding: 10px 0; border-top: 1px solid #e8eeea; }
.itinerary-entry > time { color: var(--teal-dark); font-family: var(--font-mono); font-size:  13px; font-weight: 700; }
.itinerary-entry strong { color: var(--ink); font-size:  15px; line-height: 1.45; }
.itinerary-entry p { margin:  4px 0; color: #55635d; font-size: 14px; line-height: 1.65; }
.itinerary-entry small { display: block; margin-top: 3px; color: var(--muted); font-size: 12px; line-height: 1.55; }
.itinerary-entry__note { color: #8a642c !important; }
.route-only-badge { display: inline-block; margin-left: 6px; padding: 2px 6px; border-radius: 999px; background: #eaf2ed; color: #426452; font-size: 9px; }
.route-transfer-fold { padding-top: 5px; border-top: 1px dashed var(--line); }
.route-transfer-list { display: grid; gap: 5px; padding-top: 7px; }
.route-transfer-list p { margin: 0; color: #50615a; font-size:  12px; line-height: 1.65; }
.route-transfer-list small { display: block; color: var(--muted); font-size: 12px; }
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
.reason-fold p { margin: 6px 0 0; color: #55635d; font-size: 12.5px; line-height: 1.7; }
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
.alt-card p { margin: 0; font-size: 12.5px; line-height: 1.65; }
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
.candidate-card__figures { color: var(--muted); font-size: 12px; }
.visitor-preview-frame { display: block; width: 100%; height: 680px; min-height: 480px; max-height: 720px; overflow: auto; border: 1px solid var(--line); border-radius: 10px; background: #fff; }
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
.badge-row span { padding: 3px 8px; border-radius: 999px; background: #eaf4ef; color: #2f6f60; font-size: 11px; }
.candidate-card__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }

.local-loading { padding: 11px 12px; border: 1px dashed var(--teal); border-radius: 9px; background: #f7fbf9; color: var(--teal-dark); font-size: 12px; }
.source-plan { margin: 0; padding: 8px 11px; border-radius: 9px; background: #f7fbf9; color: #55635d; font-size: 11.5px; }

/* 经营证据 */
.evidence-fold summary { cursor: pointer; color: var(--teal-dark); font-size: 12px; }
.evidence-fold summary .muted { font-size: 11px; }
.evidence-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.evidence-tabs button { padding: 4px 11px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper); color: var(--muted); font-size: 11px; cursor: pointer; }
.evidence-tabs button.active { border-color: var(--teal); background: #f1f8f4; color: var(--teal-dark); }
.evidence-body { display: grid; gap: 8px; margin-top: 10px; }
.evidence-analysis { display: grid; gap: 4px; padding: 11px 13px; border: 1px solid #e2ebe6; border-radius: 9px; background: #f7faf8; }
.evidence-analysis b, .evidence-split > div > b { color: #33463f; font-size: 11.5px; }
.evidence-analysis p { margin: 0; color: #53625b; font-size: 11.5px; line-height: 1.7; }
.evidence-analysis small, .table-subline { display: block; color: var(--muted); font-size: 10px; line-height: 1.55; margin-top: 3px; }
.evidence-split { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.evidence-split > div { min-width: 0; }
.chip-row { display: flex; flex-wrap: wrap; gap: 7px; }
.chip-row span { padding: 4px 9px; border-radius: 999px; background: var(--panel-soft); color: var(--ink); font-size: 11px; }
.signal-list { display: grid; gap: 4px; margin: 0; padding-left: 17px; color: #45524c; font-size: 11.5px; line-height: 1.7; }
.reply-table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
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
.refine-row__head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.refine-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.refine-meta em { padding: 2px 8px; border-radius: 999px; background: var(--panel-soft); color: var(--muted); font-size: 11.5px; font-style: normal; }
.refine-row__instruction { font-size: 12.5px; line-height: 1.6; }
.refine-row .reply-table { margin-top: 2px; }
.refine-row > p { margin: 0; font-size: 12px; }

/* 吸底输入区 */
.composer { position: sticky; bottom: 10px; z-index: 12; display: grid; gap: 8px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 12px; background: #fff; box-shadow: 0 -8px 24px rgba(18, 20, 19, .1); }
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
.log-item small { color: var(--muted); font-size: 11.5px; }
.log-item p { margin: 0; color: #45524c; font-size: 11.5px; line-height: 1.7; }
.log-diffs { display: grid; gap: 3px; color: #45524c; font-size: 11px; line-height: 1.6; }
.log-diffs span { display: block; }
.log-diffs span b { margin-right: 4px; color: var(--muted); font-size: 11.5px; }
.log-diffs del { color: #9a6d6d; text-decoration: line-through; }

@media (max-width: 1000px) {
  .stage-bar ol { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .key-evidence { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .decision-card__top { grid-template-columns: 1fr; }
  .decision-card__top > img, .decision-card__ph { min-height: 168px; }
}
@media (max-width: 700px) {
  .evidence-split { grid-template-columns: 1fr; }
  .candidate-grid { grid-template-columns: 1fr; }
  .visitor-preview-frame { height: 520px; min-height: 420px; }
  .date-room-picker { grid-template-columns: 1fr; }
  .plan-grid { grid-template-columns: 1fr; }
  .figure-row { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; padding: 9px 7px; font-size: 10px; }
  .figure-row b { font-size: 10.5px; }
  .copy-editor > header { flex-direction: column; }
  .copy-field { grid-template-columns: 1fr; }
  .stage-bar ol { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stage-bar li button { padding: 8px; gap: 6px; }
  .stage-bar b { font-size: 12.5px; }
  .stage-bar small { font-size: 11px; }
  .figure-row { font-size: 12px; }
  .figure-row b { font-size: 12.5px; }
}
/* 行程条目：地点 / 时长 / 区域一行显示，核验提示单独一行，不再逐条折叠。 */
.itinerary-entry__meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0 0; color: #4d6159; font-size: 12.5px; line-height: 1.6; }
.itinerary-entry__meta span { overflow-wrap: anywhere; }
.itinerary-entry__meta span + span::before { content: '·'; margin-right: 6px; color: var(--muted); }
.itinerary-entry__verify { margin: 4px 0 0; color: #8a642c; font-size: 12.5px; line-height: 1.6; }

</style>
