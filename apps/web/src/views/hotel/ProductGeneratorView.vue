<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import AiOperationsPanel from './AiOperationsView.vue'
import type { HotelService, PartnerResource, Room, TravelProduct } from '../../types'

type MarketingStyle = 'ARTISTIC' | 'PROMOTIONAL' | 'EMPATHETIC' | 'SEEDING'

const router = useRouter()
const loading = ref(false)
const loadingData = ref(true)
const insightLoading = ref(false)
const refining = ref(false)
const rooms = ref<Room[]>([])
const services = ref<HotelService[]>([])
const resources = ref<PartnerResource[]>([])
const products = ref<TravelProduct[]>([])
const selectedIndex = ref(0)
const showAutoResources = ref(false)
// The one-sentence generator and the parameter form are two ways to reach the
// same outcome, so they share one page instead of two menu entries.
const activeTab = ref<'form' | 'chat'>('chat')
const naturalBrief = ref('')
const batchBrief = ref('')
const interpreting = ref(false)
const parsedFields = ref<Array<{ label: string; value: unknown }>>([])
const overview = ref<Record<string, any>>({})
const batchOptions = reactive({ style: 'SEEDING' as MarketingStyle, generate_image: false })

const form = reactive({
  target_date: '',
  nights: 1,
  weather: 'CLOUDY',
  target_crowd: 'FAMILY',
  party_size: 3,
  minimum_gross_margin: '0.20',
  visitor_budget: '899',
  preferred_price: '699',
  theme: '亲子看展与城市探索',
  creative_direction: '',
  variant_count: 3,
  room_inventory_id: 0,
  breakfast_id: 0,
  late_id: 0,
  partner_ids: [] as number[],
})

const productTypes = [
  { id: 'museum', label: '博物馆看展', note: '室内文化体验', crowd: 'FAMILY', party: 3, budget: '899', theme: '亲子看展与城市探索', direction: '突出展陈里的好奇心与一段轻松的亲子时光' },
  { id: 'family', label: '亲子乐园', note: '玩乐与陪伴', crowd: 'FAMILY', party: 3, budget: '999', theme: '亲子乐园与城市玩乐', direction: '适合带孩子释放精力，安排清楚又保留惊喜' },
  { id: 'couple', label: '双人约会', note: '吃饭、看展或夜游', crowd: 'COUPLE', party: 2, budget: '1199', theme: '双人看展与城市晚餐', direction: '节奏松弛、适合记录两个人的周末' },
  { id: 'friends', label: '朋友玩乐', note: '运动、演出或聚会', crowd: 'FRIENDS', party: 4, budget: '1599', theme: '朋友城市玩乐局', direction: '让活动、聊天和拍照自然连在一起' },
  { id: 'night', label: '城市夜游', note: '本地周末小出逃', crowd: 'LOCAL_WEEKEND', party: 2, budget: '799', theme: '城市夜游与轻松住一晚', direction: '突出下班后也能立刻出发的松弛感' },
  { id: 'solo', label: '一人慢游', note: '看展、咖啡与独处', crowd: 'SOLO', party: 1, budget: '499', theme: '一个人的杭州慢游', direction: '安静、具体，不把独处写成孤单' },
]

const partyOptions = [
  { label: '一人', size: 1, crowd: 'SOLO' },
  { label: '两人', size: 2, crowd: 'COUPLE' },
  { label: '两大一小', size: 3, crowd: 'FAMILY' },
  { label: '两大两小', size: 4, crowd: 'FAMILY' },
  { label: '三大两小', size: 5, crowd: 'FAMILY' },
  { label: '三大三小', size: 6, crowd: 'FAMILY' },
  { label: '3–4 位朋友', size: 4, crowd: 'FRIENDS' },
  { label: '5–6 位朋友', size: 6, crowd: 'FRIENDS' },
]

// Length of stay is part of the product, so the operator chooses it here and
// the visitor page simply shows it.
const nightOptions = [
  { nights: 1, label: '2天1晚' },
  { nights: 2, label: '3天2晚' },
  { nights: 3, label: '4天3晚' },
]

const marketingStyles: Array<{ value: MarketingStyle; label: string }> = [
  { value: 'SEEDING', label: '轻松种草' },
  { value: 'ARTISTIC', label: '文艺叙事' },
  { value: 'EMPATHETIC', label: '情绪共鸣' },
  { value: 'PROMOTIONAL', label: '直接推荐' },
]

function supportsCrowd(value: string | undefined, crowd: string) {
  return !value || value === 'ALL' || value.split(/[,，]/).map(item => item.trim()).includes(crowd)
}
function supportsWeather(value: string | undefined, weather: string) {
  return !value || value.split(/[,，]/).map(item => item.trim().toUpperCase()).some(item => item === 'ALL' || item === weather)
}

const eligibleRooms = computed(() => rooms.value.filter(item => item.available_date === form.target_date && item.available_count > 0 && item.max_guests >= form.party_size))
const eligibleServices = computed(() => services.value.filter(item => item.available_date === form.target_date && item.available_quantity >= (item.service_type === 'BREAKFAST' ? form.party_size : 1) && supportsCrowd(item.suitable_crowds, form.target_crowd)))
function resourcesFor(weather: string) {
  return resources.value.filter(item =>
    item.source_type !== 'PUBLIC_REFERENCE' &&
    item.package_enabled &&
    item.status === 'AVAILABLE' &&
    item.available_date === form.target_date &&
    item.remaining_capacity >= form.party_size &&
    supportsCrowd(item.suitable_crowds, form.target_crowd) &&
    supportsWeather(item.weather_tags, weather),
  )
}
const candidateResources = computed(() => resourcesFor(form.weather))
const selectedRoom = computed(() => rooms.value.find(item => item.id === form.room_inventory_id))
const selectedPartners = computed(() => resources.value.filter(item => form.partner_ids.includes(item.id)))
const inventorySummary = computed(() => ({ rooms: eligibleRooms.value.length, services: eligibleServices.value.length, experiences: candidateResources.value.length }))
const product = computed(() => products.value[selectedIndex.value] || null)
const signals = computed<Array<{ signal: string; message: string }>>(() => {
  const value = overview.value.operations_insights?.recommendation_signals
  return Array.isArray(value) ? value : []
})
const forecast = computed(() => (overview.value.weather || {}) as { scenario?: string; usable?: boolean; advisory?: string })
const forecastLabel = computed(() => ({ RAIN: '有雨安排', SUNNY: '晴日安排', CLOUDY: '多云安排' }[String(forecast.value.scenario || form.weather)] || '天气待确认'))

function chooseWeather() {
  const verified = String(forecast.value.scenario || '')
  if (forecast.value.usable && ['RAIN', 'SUNNY', 'CLOUDY'].includes(verified)) return verified
  const choices = ['CLOUDY', 'SUNNY', 'RAIN']
  return choices.map(weather => ({ weather, count: resourcesFor(weather).length })).sort((left, right) => right.count - left.count || choices.indexOf(left.weather) - choices.indexOf(right.weather))[0]?.weather || 'CLOUDY'
}

function syncSmartInventory() {
  if (!form.target_date) return
  form.weather = chooseWeather()
  const room = [...eligibleRooms.value].sort((left, right) => right.available_count - left.available_count)[0]
  form.room_inventory_id = room?.id || 0
  const breakfast = eligibleServices.value.filter(item => item.service_type === 'BREAKFAST').sort((left, right) => right.available_quantity - left.available_quantity)[0]
  const late = eligibleServices.value.filter(item => item.service_type === 'LATE_CHECKOUT').sort((left, right) => right.available_quantity - left.available_quantity)[0]
  form.breakfast_id = breakfast?.id || 0
  form.late_id = late?.id || 0
  form.partner_ids = [...candidateResources.value].sort((left, right) => right.remaining_capacity - left.remaining_capacity).slice(0, 4).map(item => item.id)
}

async function refreshOverview() {
  if (!form.target_date) return
  insightLoading.value = true
  try {
    const response = await hotelApi.aiOverview(form.target_date)
    overview.value = response.data
    const weather = (response.data.weather || {}) as { scenario?: string; usable?: boolean }
    const scenario = String(weather.scenario || '')
    if (weather.usable && ['RAIN', 'SUNNY', 'CLOUDY'].includes(scenario)) form.weather = scenario
    syncSmartInventory()
  } catch {
    // The form still works from real hotel inventory. The server reports an
    // explicit verification note when it cannot confirm a forecast.
    overview.value = {}
  } finally {
    insightLoading.value = false
  }
}

async function loadData() {
  loadingData.value = true
  try {
    const [roomResponse, serviceResponse, resourceResponse] = await Promise.all([hotelApi.rooms(), hotelApi.services(), hotelApi.resources()])
    rooms.value = roomResponse.data
    services.value = serviceResponse.data
    resources.value = resourceResponse.data
    const preferredRoom = [...rooms.value].sort((left, right) => right.available_count - left.available_count)[0]
    form.target_date = preferredRoom?.available_date || ''
    syncSmartInventory()
    await refreshOverview()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loadingData.value = false
  }
}

async function interpretBrief() {
  if (!naturalBrief.value.trim()) { ElMessage.warning('先写下想做的产品，例如“周末两大一小看博物馆，预算 900，想要室内一些”'); return }
  interpreting.value = true
  try {
    const response = await hotelApi.interpretProductDraft(naturalBrief.value.trim())
    const interpreted = response.data.interpreted || {}
    const editableFields = ['target_date', 'weather', 'target_crowd', 'party_size', 'theme', 'visitor_budget', 'preferred_price', 'variant_count', 'creative_direction']
    editableFields.forEach((field) => { if (interpreted[field] !== undefined) (form as Record<string, unknown>)[field] = interpreted[field] })
    parsedFields.value = (response.data.parsed_fields || []).map((item) => ({ label: String(item.label), value: item.value }))
    products.value = []
    await refreshOverview()
    ElMessage.success('已整理为可编辑的产品参数')
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { interpreting.value = false }
}

function applyProductType(preset: typeof productTypes[number]) {
  form.target_crowd = preset.crowd
  form.party_size = preset.party
  form.theme = preset.theme
  form.visitor_budget = preset.budget
  form.preferred_price = preset.budget
  form.creative_direction = preset.direction
  products.value = []
  syncSmartInventory()
}

function chooseParty(option: typeof partyOptions[number]) {
  form.party_size = option.size
  form.target_crowd = option.crowd
  products.value = []
  syncSmartInventory()
}

async function generate() {
  syncSmartInventory()
  if (!form.room_inventory_id || !candidateResources.value.length) {
    ElMessage.warning('当前日期与人数下没有可组合的房间或体验，请换一个日期、人数或产品方向。')
    return
  }
  loading.value = true
  products.value = []
  selectedIndex.value = 0
  try {
    const response = await hotelApi.generateProduct({
      target_date: form.target_date,
      weather: form.weather,
      target_crowd: form.target_crowd,
      party_size: form.party_size,
      nights: form.nights,
      minimum_gross_margin: form.minimum_gross_margin,
      visitor_budget: form.visitor_budget,
      preferred_price: form.preferred_price,
      theme: form.theme,
      creative_direction: form.creative_direction,
      variant_count: form.variant_count,
      room_inventory_id: form.room_inventory_id,
      // Candidate cards are alternatives, not ingredients to stack together.
      resource_selections: [],
    })
    products.value = response.data.products?.length ? response.data.products : [response.data.product]
    ElMessage.success(`已生成 ${products.value.length} 套 ${form.party_size} 人产品候选`)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

async function refineAll() {
  if (!products.value.length) return
  if (!batchBrief.value.trim()) { ElMessage.warning('写下希望怎样调整这些候选，例如“统一改得更适合带 6 岁孩子，语气活泼一些”'); return }
  refining.value = true
  try {
    const response = await hotelApi.refineProductMarketing({
      product_ids: products.value.map(item => item.id),
      natural_language: batchBrief.value.trim(),
      style: batchOptions.style,
      generate_image: batchOptions.generate_image,
    })
    const updated = new Map(response.data.map(item => [item.id, item]))
    products.value = products.value.map(item => updated.get(item.id) || item)
    batchBrief.value = ''
    ElMessage.success(batchOptions.generate_image ? '候选文案、SVG 海报与产品主图已更新' : '候选文案与 SVG 海报已更新')
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { refining.value = false }
}

async function publish() {
  if (!product.value) return
  try {
    products.value[selectedIndex.value] = (await hotelApi.productStatus(product.value.id, 'ON_SALE')).data
    ElMessage.success('已发布当前方案')
  } catch (error) { ElMessage.error(errorMessage(error)) }
}

function openDetail(item = product.value) { if (item) router.push(`/hotel/products/${item.id}`) }
// 候选卡片也带真实主图（优先房型实拍，其次任一体验图），避免出现「没有图片」的卡片。
function productThumb(item: TravelProduct) {
  const resources = (item.resources || []) as Array<Record<string, any>>
  const room = resources.find((row) => row.resource_type === 'ROOM' && row.image_url)
  const anyImage = resources.find((row) => row.image_url)
  return String(room?.image_url || anyImage?.image_url || '')
}

watch([() => form.target_date, () => form.target_crowd, () => form.party_size], () => {
  products.value = []
  syncSmartInventory()
  void refreshOverview()
})

onMounted(loadData)
</script>

<template>
  <div class="generator-page" :class="{ 'generator-page--chat': activeTab === 'chat' }">
  <div class="generator-bar">
    <h1>生成产品</h1>
    <div class="generator-tabs">
      <button type="button" :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">用一句话生成</button>
      <button type="button" :class="{ active: activeTab === 'form' }" @click="activeTab = 'form'">按参数生成</button>
    </div>
    <span class="generator-bar__spacer"></span>
    <el-button plain :loading="loadingData" @click="loadData">刷新可用资源</el-button>
  </div>

  <template v-if="activeTab === 'form'">
  <div v-if="loadingData" class="panel empty-state">正在读取当前可用房间、服务与合作体验…</div>
  <template v-else>
    <section class="recommend-panel panel" v-loading="insightLoading">
      <div class="recommend-panel__lead"><div class="eyebrow">智能推荐</div><strong>从真实经营与天气信息开始</strong><small>{{ forecastLabel }} · {{ forecast.advisory || '天气信息将在生成时再次核验。' }}</small></div>
      <div class="recommend-signals">
        <span v-for="item in signals" :key="item.signal"><i />{{ item.message }}</span>
        <span v-if="!signals.length"><i />当前经营样本有限，优先从实时可用库存生成候选。</span>
      </div>
    </section>

    <section class="builder panel">
      <div class="builder-heading"><div><div class="eyebrow">先选方向</div><h2>少量选择，剩下由系统组合</h2></div><span>自动避开不可用资源</span></div>
      <div class="selector-block">
        <label>产品类型</label>
        <div class="choice-grid product-type-grid">
          <button v-for="preset in productTypes" :key="preset.id" type="button" :class="{ active: form.theme === preset.theme }" @click="applyProductType(preset)"><strong>{{ preset.label }}</strong><small>{{ preset.note }}</small></button>
        </div>
      </div>
      <div class="selector-block">
        <label>人数套餐</label>
        <div class="choice-grid party-grid">
          <button v-for="option in partyOptions" :key="option.label" type="button" :class="{ active: form.party_size === option.size && form.target_crowd === option.crowd }" @click="chooseParty(option)">{{ option.label }}</button>
        </div>
      </div>
      <div class="selector-block">
        <label>出行天数</label>
        <div class="choice-grid party-grid">
          <button v-for="option in nightOptions" :key="option.nights" type="button" :class="{ active: form.nights === option.nights }" @click="form.nights = option.nights">{{ option.label }}</button>
        </div>
        <small class="selector-note">天数与房型绑定在商品上；多住一晚会在行程里补上一整天的体验内容。</small>
      </div>

      <el-form label-position="top" class="builder-form">
        <div class="form-grid compact-form">
          <el-form-item label="入住日期"><el-date-picker v-model="form.target_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
          <el-form-item label="参考售价"><el-input v-model="form.preferred_price"><template #prepend>¥</template></el-input></el-form-item>
          <el-form-item label="目标客群"><el-select v-model="form.target_crowd" style="width:100%"><el-option label="亲子家庭" value="FAMILY" /><el-option label="两人约会" value="COUPLE" /><el-option label="朋友相聚" value="FRIENDS" /><el-option label="一个人慢游" value="SOLO" /><el-option label="本地周末" value="LOCAL_WEEKEND" /></el-select></el-form-item>
          <el-form-item label="候选数量"><el-select v-model="form.variant_count" style="width:100%"><el-option :value="2" label="2 套" /><el-option :value="3" label="3 套" /><el-option :value="4" label="4 套" /></el-select></el-form-item>
          <el-form-item class="full" label="产品主题"><el-input v-model="form.theme" placeholder="如：带孩子看展以后吃一顿好饭、双人夜游、朋友运动放松" /></el-form-item>
          <el-form-item class="full" label="补充偏好（可选）"><el-input v-model="form.creative_direction" placeholder="如：更适合 6 岁孩子、不要太赶、突出拍照和晚餐体验" /></el-form-item>
        </div>
      </el-form>

      <div class="inventory-strip">
        <div><small>可用房型</small><strong>{{ inventorySummary.rooms }}</strong></div>
        <div><small>可用服务</small><strong>{{ inventorySummary.services }}</strong></div>
        <div><small>可用体验</small><strong>{{ inventorySummary.experiences }}</strong></div>
        <div class="inventory-strip__text"><span>当前按 {{ form.party_size }} 人套餐筛选</span><button type="button" @click="showAutoResources = !showAutoResources">{{ showAutoResources ? '收起内容' : '查看候选内容' }}</button></div>
      </div>
      <div v-if="showAutoResources" class="inventory-detail"><span v-if="selectedRoom">住宿：{{ selectedRoom.room_type }}（余 {{ selectedRoom.available_count }} 间）</span><span v-for="item in selectedPartners" :key="item.id">体验：{{ item.resource_name }}（余 {{ item.remaining_capacity }}）</span></div>
      <el-button type="primary" size="large" class="generate-button" :loading="loading" @click="generate">生成 {{ form.party_size }} 人产品候选</el-button>
    </section>

    <section v-if="products.length" class="candidate-panel panel">
      <div class="candidate-panel__head"><div><div class="eyebrow">候选方案</div><h2>先挑方向，再细调单品</h2></div><span>{{ products.length }} 套 · {{ form.party_size }} 人套餐</span></div>
      <div class="candidate-grid">
        <button v-for="(item, index) in products" :key="item.id" type="button" :class="{ active: selectedIndex === index }" @click="selectedIndex = index">
          <img v-if="productThumb(item)" class="candidate-thumb" :src="productThumb(item)" :alt="item.product_name" loading="lazy" />
          <div><small>候选 {{ index + 1 }}</small><StatusTag :status="item.status" /></div>
          <strong>{{ item.product_name }}</strong>
          <span>{{ item.theme }}</span>
          <footer><b>¥{{ item.suggested_price }}</b><em>{{ item.party_size }} 人 · {{ item.sale_quantity }} 套可售</em></footer>
        </button>
      </div>
      <article v-if="product" class="candidate-detail">
        <div class="candidate-detail__top"><div><span>{{ product.theme }} · {{ product.party_size }} 人套餐</span><h2>{{ product.product_name }}</h2></div><StatusTag :status="product.status" /></div>
        <p>{{ product.recommendation_reason }}</p>
        <div class="candidate-chips"><span v-for="item in product.resources" :key="item.id">{{ item.resource_name }}</span></div>
        <div class="candidate-facts"><div><small>参考售价</small><strong>¥{{ product.suggested_price }}</strong></div><div><small>可售数量</small><strong>{{ product.sale_quantity }} 套</strong></div><div><small>套餐人数</small><strong>{{ product.party_size }} 人</strong></div></div>
        <el-alert v-if="product.risk_message" :title="product.risk_message" type="info" :closable="false" show-icon />
        <div class="form-actions"><el-button @click="openDetail(product)">细调产品详情</el-button><el-button type="primary" :disabled="product.status !== 'DRAFT'" @click="publish">发布当前方案</el-button></div>
      </article>

      <div class="batch-refine">
        <div><div class="eyebrow">批量自然语言调整</div><strong>统一改写这 {{ products.length }} 套候选</strong><small>只调整游客可见的标题、文案、SVG 海报与可选主图，不改库存、价格或发布状态。</small></div>
        <el-input v-model="batchBrief" type="textarea" :rows="2" placeholder="例如：统一改得更适合带 6 岁孩子，文案更轻松，强调博物馆里的互动感" />
        <div class="batch-refine__controls"><el-select v-model="batchOptions.style" style="width:130px"><el-option v-for="style in marketingStyles" :key="style.value" :label="style.label" :value="style.value" /></el-select><el-switch v-model="batchOptions.generate_image" active-text="重做主图" inactive-text="不重做主图" /><el-button type="primary" :loading="refining" @click="refineAll">应用到全部候选</el-button></div>
      </div>
    </section>

    <section v-else class="empty-candidate panel"><div>✦</div><h2>选择一个产品方向，生成可编辑的候选</h2><p>系统会先用真实房间、服务和体验做组合校验，再调用 AI 写出不同的产品表达。</p></section>
  </template>
  </template>
  <AiOperationsPanel v-else />
  </div>
</template>

<style scoped>
.generator-bar { display: flex; align-items: center; gap: 14px; margin: 0 0 12px; }
.generator-page { display: flex; flex-direction: column; height: calc(100dvh - 58px - 62px); min-height: 440px; overflow: hidden; }
/* 对话模式（AiOperationsView）是分阶段长页面，不再用固定高度内滚，改为随文档滚动。 */
.generator-page--chat { height: auto; min-height: 0; overflow: visible; }
.generator-bar h1 { margin: 0; font-size: 22px; letter-spacing: -.5px; }
.generator-bar__spacer { flex: 1 1 auto; }
.generator-tabs { display: flex; gap: 6px; padding: 4px; width: max-content; border: 1px solid var(--line); border-radius: 10px; background: var(--panel-soft); }
.candidate-thumb { display: block; width: 100%; height: 96px; object-fit: cover; border-radius: 8px; margin-bottom: 8px; }
.generator-tabs button { padding: 7px 16px; border: 0; border-radius: 7px; background: transparent; color: var(--muted); font-size: 12px; cursor: pointer; }
.generator-tabs button.active { background: var(--paper); color: var(--ink); font-weight: 650; box-shadow: 0 1px 3px rgba(24, 40, 34, .08); }
/* 窄屏时标题会被挤压成竖排，这里让工具条换行并让页签占满一行。 */
@media (max-width: 760px) {
  .generator-bar { flex-wrap: wrap; row-gap: 8px; }
  .generator-bar h1 { font-size: 20px; white-space: nowrap; }
  .generator-tabs { width: 100%; }
  .generator-tabs button { flex: 1 1 0; text-align: center; }
}
.selector-note { display: block; margin-top: 8px; color: var(--muted); font-size: 11px; }
.generator-head{align-items:flex-end}.generator-head h1{margin-bottom:7px}.generator-head p{max-width:680px}.brief-panel{display:grid;grid-template-columns:minmax(210px,.9fr) minmax(320px,1.6fr) auto;align-items:center;gap:12px;margin-bottom:14px}.brief-panel strong,.brief-panel small{display:block}.brief-panel strong{margin-top:4px;font-size:14px}.brief-panel small,.recommend-panel small,.batch-refine small{margin-top:4px;color:var(--muted);font-size:11px;line-height:1.55}.brief-chips{grid-column:1/-1;display:flex;gap:6px;flex-wrap:wrap}.brief-chips span{border:1px solid var(--line);border-radius:6px;background:var(--panel-soft);padding:4px 7px;color:var(--muted);font-size:11px}.recommend-panel{display:grid;grid-template-columns:minmax(220px,.72fr) 1.28fr;gap:20px;align-items:center;margin-bottom:14px;padding:16px 18px}.recommend-panel__lead strong{display:block;margin-top:4px;font-size:14px}.recommend-signals{display:grid;gap:7px}.recommend-signals span{color:var(--muted);font-size:12px;line-height:1.55}.recommend-signals i{display:inline-block;width:6px;height:6px;margin:0 7px 1px 0;border-radius:50%;background:#6b857a}.builder{padding:20px}.builder-heading,.candidate-panel__head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px}.builder-heading h2,.candidate-panel__head h2,.empty-candidate h2{margin:5px 0 0;font-size:21px;letter-spacing:-.2px}.builder-heading>span,.candidate-panel__head>span{color:var(--muted);font-size:12px}.selector-block{margin-top:18px}.selector-block>label{display:block;margin-bottom:8px;color:var(--muted);font-size:12px;font-weight:650}.choice-grid{display:flex;gap:7px;flex-wrap:wrap}.choice-grid button{border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink);cursor:pointer;transition:background .18s,border-color .18s,transform .18s}.choice-grid button:hover{border-color:#a5b1ab;transform:translateY(-1px)}.choice-grid button.active{border-color:#64746d;background:#eff3f1;box-shadow:inset 0 0 0 1px #64746d}.product-type-grid button{display:flex;flex-direction:column;min-width:130px;padding:10px 11px;text-align:left}.product-type-grid strong{font-size:12px}.product-type-grid small{margin-top:3px;color:var(--muted);font-size:10px}.party-grid button{padding:8px 12px;font-size:12px}.builder-form{margin-top:20px}.compact-form{gap:11px}.builder-form :deep(.el-form-item){margin-bottom:10px}.builder-form :deep(.el-form-item__label){padding-bottom:4px;font-size:12px;font-weight:650}.inventory-strip{display:grid;grid-template-columns:repeat(3,minmax(0,110px)) 1fr;gap:0;margin-top:6px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.inventory-strip>div{display:flex;flex-direction:column;justify-content:center;min-height:64px;padding:8px 13px;border-right:1px solid var(--line)}.inventory-strip>div:last-child{border-right:0}.inventory-strip small{color:var(--muted);font-size:10px}.inventory-strip strong{margin-top:2px;font:600 18px/1.2 var(--font-mono)}.inventory-strip__text{align-items:flex-start!important;gap:3px;color:var(--muted);font-size:11px}.inventory-strip__text button{border:0;background:transparent;padding:0;color:var(--teal);font-size:11px;cursor:pointer}.inventory-detail{display:flex;gap:7px;flex-wrap:wrap;padding-top:11px}.inventory-detail span,.candidate-chips span{padding:5px 7px;border:1px solid var(--line);border-radius:6px;background:var(--panel-soft);color:var(--muted);font-size:11px}.generate-button{width:100%;height:42px;margin-top:18px}.candidate-panel{margin-top:14px;padding:20px}.candidate-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;margin:17px 0}.candidate-grid>button{min-height:138px;border:1px solid var(--line);border-radius:9px;background:var(--paper);padding:12px;text-align:left;color:var(--ink);cursor:pointer;transition:border-color .18s,background .18s}.candidate-grid>button:hover,.candidate-grid>button.active{border-color:#687872;background:var(--panel-soft)}.candidate-grid>button>div{display:flex;justify-content:space-between;align-items:center}.candidate-grid small,.candidate-grid span{display:block;color:var(--muted);font-size:10px}.candidate-grid strong{display:block;min-height:37px;margin:8px 0 3px;font-size:13px;line-height:1.4}.candidate-grid footer{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px}.candidate-grid b{font-family:var(--font-mono);font-size:14px}.candidate-grid em{color:var(--muted);font-size:10px;font-style:normal}.candidate-detail{padding:18px 0;border-top:1px solid var(--line)}.candidate-detail__top{display:flex;justify-content:space-between;gap:12px}.candidate-detail__top span{color:var(--muted);font-size:11px}.candidate-detail__top h2{margin:6px 0 0;font-size:23px;line-height:1.35}.candidate-detail>p{margin:13px 0 0;color:var(--muted);font-size:13px;line-height:1.75}.candidate-chips{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0}.candidate-facts{display:flex;gap:32px;margin:16px 0;padding:12px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.candidate-facts small{display:block;color:var(--muted);font-size:10px}.candidate-facts strong{display:block;margin-top:3px;font-family:var(--font-mono);font-size:16px}.form-actions{margin-top:14px}.batch-refine{display:grid;grid-template-columns:230px minmax(260px,1fr);gap:14px;align-items:center;margin-top:20px;padding-top:18px;border-top:1px solid var(--line)}.batch-refine strong{display:block;margin-top:4px;font-size:13px}.batch-refine small{display:block}.batch-refine__controls{grid-column:2;display:flex;align-items:center;justify-content:flex-end;gap:10px}.empty-candidate{display:grid;place-items:center;align-content:center;min-height:260px;margin-top:14px;text-align:center}.empty-candidate>div{display:grid;place-items:center;width:42px;height:42px;border:1px solid var(--line);border-radius:50%;color:var(--teal);font-size:21px}.empty-candidate h2{margin-top:14px}.empty-candidate p{max-width:480px;margin:8px 0 0;color:var(--muted);font-size:13px;line-height:1.7}@media(max-width:900px){.brief-panel{grid-template-columns:1fr}.recommend-panel{grid-template-columns:1fr}.batch-refine{grid-template-columns:1fr}.batch-refine__controls{grid-column:auto;justify-content:flex-start}.inventory-strip{grid-template-columns:repeat(3,1fr)}.inventory-strip__text{grid-column:1/-1;border-top:1px solid var(--line);border-right:0!important}}@media(max-width:620px){.generator-head{align-items:flex-start}.choice-grid{gap:6px}.product-type-grid button{min-width:calc(50% - 4px)}.inventory-strip{grid-template-columns:repeat(3,1fr)}.candidate-facts{gap:15px}.candidate-facts strong{font-size:14px}.candidate-detail__top{align-items:flex-start;flex-direction:column}.batch-refine__controls{align-items:flex-start;flex-direction:column}.batch-refine__controls .el-button{width:100%}}
</style>
