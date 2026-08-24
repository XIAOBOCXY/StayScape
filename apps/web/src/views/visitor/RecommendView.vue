<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import MediaImage from '../../components/MediaImage.vue'
import type { TripPlan, TripPlanItem, TripPlanSelection, TravelProduct } from '../../types'
import { mediaForResource } from '../../utils/productMedia'

const loading = ref(false)
const route = useRoute()
const holding = ref(false)
const plans = ref<TripPlan[]>([])
const active = ref<TripPlan | null>(null)
const selectedPlanIndex = ref(0)
const dragIndex = ref<number | null>(null)
const contactVisible = ref(false)
const posterVisible = ref(false)
const note = ref('')
const productDates = ref<string[]>([])
const contact = reactive({ name: '', phone: '' })
const form = reactive({ natural_language: '', start_date: '', duration_days: 2, party_size: 2, plan_name: '我的杭州行程', source_product_id: undefined as number | undefined })

const total = computed(() => active.value?.itinerary.reduce((sum, item) => sum + Number(item.subtotal || 0), 0) || 0)
const lowStock = computed(() => active.value?.itinerary.filter((item) => item.low_stock) || [])
const alternativeItems = computed(() => {
  if (!active.value) return []
  const selected = new Set(active.value.itinerary.map((item) => `${item.resource_type}-${item.resource_id}`))
  return plans.value.flatMap((plan) => plan.itinerary).filter((item) => !selected.has(`${item.resource_type}-${item.resource_id}`)).slice(0, 6)
})

function clonePlan(plan: TripPlan): TripPlan {
  return JSON.parse(JSON.stringify(plan)) as TripPlan
}
function toSelection(items: TripPlanItem[]): TripPlanSelection[] {
  return items.map((item, index) => ({ resource_type: item.resource_type, resource_id: item.resource_id, quantity: item.quantity, sort_order: index * 10 }))
}
function resetSort() {
  if (!active.value) return
  active.value.itinerary.forEach((item, index) => { item.sort_order = index * 10 })
  active.value.items = toSelection(active.value.itinerary)
  active.value.total_price = total.value.toFixed(2)
}
function itineraryMedia(item: TripPlanItem, index: number) {
  return mediaForResource(null, {
    id: item.resource_id,
    resource_type: item.resource_type,
    resource_id: item.resource_id,
    resource_name: item.resource_name,
    quantity_per_package: item.quantity,
    unit_cost: item.unit_price,
    replaceable: item.resource_type !== 'ROOM',
    required: true,
    available_date: item.date,
    start_time: item.start_time || undefined,
    end_time: item.end_time || undefined,
    address: item.address,
    description: item.description,
    image_url: item.image_url,
    image_source: item.image_source,
    image_attribution: item.image_attribution,
  }, index)
}
function timeLabel(item: TripPlanItem) {
  if (item.resource_type === 'ROOM') return '15:00 后办理入住'
  return item.start_time && item.end_time ? `${item.start_time} – ${item.end_time}` : '时间以确认信息为准'
}
function typeLabel(item: TripPlanItem) {
  return ({ ROOM: '住宿', HOTEL_SERVICE: '酒店服务', PARTNER_RESOURCE: '体验' } as Record<string, string>)[item.resource_type] || '行程内容'
}
function move(index: number, delta: number) {
  if (!active.value) return
  const next = index + delta
  if (next < 0 || next >= active.value.itinerary.length) return
  const [item] = active.value.itinerary.splice(index, 1)
  active.value.itinerary.splice(next, 0, item)
  resetSort()
}
function startDrag(index: number) { dragIndex.value = index }
function drop(index: number) {
  if (dragIndex.value === null || !active.value || dragIndex.value === index) return
  const [item] = active.value.itinerary.splice(dragIndex.value, 1)
  active.value.itinerary.splice(index, 0, item)
  dragIndex.value = null
  resetSort()
}
function removeItem(index: number) {
  if (!active.value) return
  const item = active.value.itinerary[index]
  if (item.resource_type === 'ROOM') { showToast('住宿会随行程保留；可重新生成来换房型。'); return }
  active.value.itinerary.splice(index, 1)
  resetSort()
}
function addItem(item: TripPlanItem) {
  if (!active.value) return
  active.value.itinerary.push({ ...item, sort_order: active.value.itinerary.length * 10 })
  resetSort()
}
function selectPlan(plan: TripPlan, index = 0) {
  active.value = clonePlan(plan)
  selectedPlanIndex.value = index
  note.value = ''
}
function payload() {
  return {
    natural_language: form.natural_language,
    start_date: form.start_date,
    duration_days: Number(form.duration_days),
    party_size: Number(form.party_size),
    plan_name: form.plan_name,
    weather: 'CLOUDY',
    target_crowd: active.value?.target_crowd || 'FRIENDS',
    include_breakfast: true,
    source_product_id: form.source_product_id,
  }
}
async function propose() {
  if (!form.start_date) { showToast('先选择出发日期'); return }
  loading.value = true
  try {
    const response = await visitorApi.proposeTripPlans(payload())
    plans.value = response.data.plans
    note.value = response.data.inventory_note || ''
    if (plans.value.length) {
      // A concrete date or day count written in the sentence is reflected back
      // into the visible controls, so the next edit/hold uses what the visitor
      // sees instead of a hidden parsed value.
      form.start_date = plans.value[0].start_date
      form.duration_days = plans.value[0].duration_days
      selectPlan(plans.value[0], 0)
    }
    else active.value = null
  } catch (error) { showToast(errorMessage(error)) }
  finally { loading.value = false }
}
async function openHold() {
  if (!active.value) { await propose(); return }
  contactVisible.value = true
}
async function holdOrUpdate() {
  if (!active.value || !contact.name.trim() || !contact.phone.trim()) { showToast('请填写联系人和手机号'); return }
  holding.value = true
  const request = { ...payload(), items: toSelection(active.value.itinerary), contact_name: contact.name.trim(), contact_phone: contact.phone.trim() }
  try {
    const response = active.value.id
      ? await visitorApi.updateTripPlan(Number(active.value.id), request)
      : await visitorApi.holdTripPlan(request)
    active.value = response.data
    note.value = response.data.message
    contactVisible.value = false
    showToast(active.value.status === 'HELD' ? '行程已暂留，继续调整会同步刷新库存' : '行程已更新')
  } catch (error) { showToast(errorMessage(error)) }
  finally { holding.value = false }
}
async function syncHeld() {
  if (!active.value?.id) { contactVisible.value = true; return }
  holding.value = true
  try {
    const response = await visitorApi.updateTripPlan(Number(active.value.id), { ...payload(), items: toSelection(active.value.itinerary), contact_name: contact.name, contact_phone: contact.phone })
    active.value = response.data
    note.value = response.data.message
    showToast('行程与暂留库存已更新')
  } catch (error) { showToast(errorMessage(error)) }
  finally { holding.value = false }
}
async function loadDates() {
  try {
    const products: TravelProduct[] = (await visitorApi.products()).data
    productDates.value = [...new Set(products.map((item) => item.target_date))].sort()
    form.start_date = productDates.value[0] || new Date().toISOString().slice(0, 10)
  } catch { form.start_date = new Date().toISOString().slice(0, 10) }
}
function disabledDate(value: Date) {
  const local = `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
  return productDates.value.length ? !productDates.value.includes(local) : false
}

onMounted(async () => {
  form.natural_language = typeof route.query.q === 'string' ? route.query.q : ''
  const sourceProductId = Number(route.query.product || 0)
  form.source_product_id = Number.isFinite(sourceProductId) && sourceProductId > 0 ? sourceProductId : undefined
  await loadDates()
  await propose()
})
</script>

<template>
  <main class="trip-builder">
    <section class="trip-builder__head">
      <router-link to="/visitor/products" class="back-link">← 返回产品</router-link>
      <div><span>自定义行程</span><h1>说说想怎么玩</h1></div>
      <p>可以直接写第一天、第二天想去哪里；系统只会给出当前还有名额的安排。</p>
    </section>

    <section class="trip-prompt">
      <textarea v-model="form.natural_language" placeholder="例如：两个人周六到杭州，第一天看展吃饭，第二天去博物馆和西湖；想住两晚，不想太赶。" @keyup.ctrl.enter="propose" />
      <div class="trip-prompt__controls">
        <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" :disabled-date="disabledDate" />
        <el-select v-model="form.duration_days" aria-label="行程天数"><el-option v-for="day in [1, 2, 3, 4, 5]" :key="day" :label="`${day} 天`" :value="day" /></el-select>
        <el-input-number v-model="form.party_size" :min="1" :max="8" controls-position="right" aria-label="同行人数" /><span class="party-label">人同行</span>
        <el-button type="primary" :loading="loading" @click="propose">生成行程</el-button>
      </div>
    </section>

    <div v-if="plans.length" class="plan-switcher"><button v-for="(plan, index) in plans" :key="`${plan.start_date}-${index}`" :class="{ active: selectedPlanIndex === index }" @click="selectPlan(plan, index)"><small>方案 {{ index + 1 }}</small><strong>¥{{ plan.total_price }}</strong><span>{{ plan.itinerary.filter(item => item.resource_type === 'PARTNER_RESOURCE').map(item => item.resource_name).slice(0, 2).join(' · ') }}</span></button></div>

    <section v-if="active" class="trip-workspace">
      <header class="trip-workspace__summary"><div><span>{{ active.start_date }} · {{ active.duration_days }} 天 · {{ active.party_size }} 人</span><h2>{{ form.plan_name }}</h2></div><div class="trip-summary-actions"><button type="button" @click="posterVisible = true">分享海报</button><div><small>当前合计</small><strong>¥{{ total.toFixed(2) }}</strong></div></div></header>
      <p v-if="note" class="trip-note">{{ note }}</p>
      <div v-if="lowStock.length" class="low-stock-line">{{ lowStock.map(item => `「${item.resource_name}」名额不多`).join('，') }}</div>

      <div class="itinerary-editor">
        <article v-for="(item, index) in active.itinerary" :key="`${item.resource_type}-${item.resource_id}-${index}`" class="editable-item" draggable="true" @dragstart="startDrag(index)" @dragover.prevent @drop="drop(index)">
          <div class="item-order"><span>第 {{ item.day }} 天</span><b>{{ String(index + 1).padStart(2, '0') }}</b></div>
          <MediaImage :media="itineraryMedia(item, index)" aspect="card" />
          <div class="editable-item__body"><div><span>{{ typeLabel(item) }}</span><time>{{ timeLabel(item) }}</time></div><h3>{{ item.resource_name }}</h3><p>{{ item.description || item.address || '按当天安排体验' }}</p><small>{{ item.address || '杭州' }} · ¥{{ item.subtotal }}</small></div>
          <div class="item-actions"><button type="button" title="上移" @click="move(index, -1)">↑</button><button type="button" title="下移" @click="move(index, 1)">↓</button><button type="button" :disabled="item.resource_type === 'ROOM'" title="移除" @click="removeItem(index)">×</button></div>
        </article>
      </div>

      <div v-if="alternativeItems.length" class="add-ons"><span>也可以换成</span><button v-for="item in alternativeItems" :key="`${item.resource_type}-${item.resource_id}`" @click="addItem(item)">＋ {{ item.resource_name }}</button></div>
      <div class="workspace-actions"><el-button v-if="active.id" plain :loading="holding" @click="syncHeld">同步这次修改</el-button><el-button type="primary" :loading="holding" @click="openHold">{{ active.id ? '继续暂留' : '暂留并继续编辑' }}</el-button></div>
    </section>

    <section v-else-if="!loading" class="trip-empty"><h2>换一个日期或说得再具体一点</h2><p>例如写“第二天去博物馆”，或把行程天数调短一些。</p></section>

    <el-dialog v-model="contactVisible" title="暂留这份行程" width="min(92vw, 440px)"><p class="contact-note">暂留会占用当前选择的房型和体验名额；你仍可以在保留时间内调整顺序或内容。</p><el-form label-position="top"><el-form-item label="联系人"><el-input v-model="contact.name" placeholder="怎么称呼你" /></el-form-item><el-form-item label="手机号码"><el-input v-model="contact.phone" inputmode="tel" placeholder="用于行程确认" /></el-form-item></el-form><template #footer><el-button @click="contactVisible=false">取消</el-button><el-button type="primary" :loading="holding" @click="holdOrUpdate">确认暂留</el-button></template></el-dialog>

    <el-dialog v-model="posterVisible" title="行程分享海报" width="min(92vw, 520px)" top="5vh"><section v-if="active" class="trip-share-poster"><header><span>杭州周末 · {{ active.start_date }}</span><h2>{{ form.plan_name }}</h2><p>{{ active.duration_days }} 天 {{ active.party_size }} 人 · ¥{{ total.toFixed(2) }}</p></header><article v-for="(item, index) in active.itinerary" :key="`poster-${item.resource_type}-${item.resource_id}-${index}`"><div class="trip-share-poster__time"><b>第 {{ item.day }} 天</b><span>{{ timeLabel(item) }}</span></div><MediaImage :media="itineraryMedia(item, index)" aspect="card" /><div><small>{{ typeLabel(item) }} · {{ item.address || '杭州' }}</small><strong>{{ item.resource_name }}</strong><p>{{ item.description || '按当天安排体验' }}</p></div></article><footer><span>杭州旅居</span><small>按当前选择生成的路线与时间表</small></footer></section><template #footer><el-button type="primary" @click="posterVisible = false">完成</el-button></template></el-dialog>

    <div v-if="active" class="trip-sticky"><div><small>{{ active.id ? '已暂留，修改后请同步' : '还未占用名额' }}</small><strong>¥{{ total.toFixed(2) }}</strong></div><button :disabled="holding" @click="active.id ? syncHeld() : openHold()">{{ active.id ? '同步修改' : '暂留行程' }}</button></div>
  </main>
</template>

<style scoped>
.trip-builder{max-width:980px;margin:0 auto;padding:8px 0 94px}.trip-builder__head{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;align-items:end;margin:8px 0 18px}.back-link{grid-column:1/-1;color:var(--muted);font-size:12px;text-decoration:none}.trip-builder__head span{color:var(--muted);font-size:11px;letter-spacing:.09em}.trip-builder h1{margin:4px 0 0;font-size:26px;letter-spacing:-.6px}.trip-builder__head p{max-width:380px;margin:0;color:var(--muted);font-size:12px;line-height:1.65}.trip-prompt{padding:12px;border:1px solid var(--line);border-radius:14px;background:var(--paper);box-shadow:0 10px 28px rgba(26,33,30,.05)}.trip-prompt textarea{display:block;width:100%;min-height:86px;padding:5px;border:0;outline:0;resize:vertical;background:transparent;color:var(--ink);font:14px/1.75 var(--font-sans)}.trip-prompt textarea::placeholder{color:#9aa5a1}.trip-prompt__controls{display:flex;align-items:center;gap:8px;padding-top:10px;border-top:1px solid var(--line)}.trip-prompt__controls :deep(.el-date-editor){width:140px}.trip-prompt__controls :deep(.el-select){width:88px}.trip-prompt__controls :deep(.el-input-number){width:104px}.party-label{margin-left:-5px;color:var(--muted);font-size:12px}.plan-switcher{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}.plan-switcher button{display:grid;gap:3px;padding:11px;border:1px solid var(--line);border-radius:11px;background:var(--paper);color:var(--ink);text-align:left;cursor:pointer;transition:.16s}.plan-switcher button:hover,.plan-switcher button.active{border-color:#65736e;background:#f3f6f4}.plan-switcher small,.plan-switcher span{overflow:hidden;color:var(--muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.plan-switcher strong{font-family:var(--font-mono);font-size:15px}.trip-workspace{border:1px solid var(--line);border-radius:14px;background:var(--paper);overflow:hidden}.trip-workspace__summary{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;padding:16px 17px;border-bottom:1px solid var(--line)}.trip-workspace__summary span,.trip-workspace__summary small{display:block;color:var(--muted);font-size:11px}.trip-workspace__summary h2{margin:5px 0 0;font-size:18px}.trip-workspace__summary>div:last-child{text-align:right}.trip-workspace__summary strong{display:block;margin-top:4px;font-family:var(--font-mono);font-size:21px}.trip-note,.low-stock-line{margin:10px 14px 0;padding:9px 10px;border-radius:8px;background:#f5f7f6;color:#5b6863;font-size:11px;line-height:1.55}.low-stock-line{background:#fff1ed;color:#98463b}.itinerary-editor{display:grid;gap:1px;padding:12px}.editable-item{display:grid;grid-template-columns:48px 92px minmax(0,1fr) 66px;gap:11px;align-items:stretch;min-height:102px;padding:10px 0;border-bottom:1px solid var(--line);background:var(--paper);cursor:grab}.editable-item:last-child{border-bottom:0}.item-order{display:grid;align-content:start;gap:5px;color:var(--muted);font-size:9px}.item-order b{font-family:var(--font-mono);font-size:17px;color:var(--ink)}.editable-item :deep(.media-image){width:92px;height:82px;min-height:0;align-self:center;aspect-ratio:auto;border-radius:8px}.editable-item__body{min-width:0}.editable-item__body>div{display:flex;justify-content:space-between;gap:8px}.editable-item__body span,.editable-item__body time,.editable-item__body small{color:var(--muted);font-size:10px}.editable-item__body h3{overflow:hidden;margin:4px 0;color:var(--ink);font-size:14px;text-overflow:ellipsis;white-space:nowrap}.editable-item__body p{display:-webkit-box;overflow:hidden;margin:0;color:var(--muted);font-size:11px;line-height:1.45;-webkit-line-clamp:2;-webkit-box-orient:vertical}.editable-item__body small{display:block;margin-top:5px;font-family:var(--font-mono)}.item-actions{display:flex;align-items:center;justify-content:flex-end;gap:3px}.item-actions button{width:19px;height:21px;border:1px solid var(--line);border-radius:5px;background:var(--panel-soft);color:var(--muted);cursor:pointer}.item-actions button:disabled{opacity:.3;cursor:default}.add-ons{display:flex;align-items:center;flex-wrap:wrap;gap:6px;padding:0 14px 14px}.add-ons>span{margin-right:3px;color:var(--muted);font-size:11px}.add-ons button{max-width:230px;overflow:hidden;padding:6px 8px;border:1px solid var(--line);border-radius:999px;background:#fff;color:#52655f;font-size:10px;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.workspace-actions{display:flex;justify-content:flex-end;gap:8px;padding:11px 14px;border-top:1px solid var(--line)}.trip-empty{padding:40px 20px;text-align:center;color:var(--muted)}.trip-empty h2{margin:0;color:var(--ink);font-size:18px}.trip-empty p{font-size:12px}.contact-note{margin:0 0 16px;color:var(--muted);font-size:12px;line-height:1.65}.trip-sticky{position:fixed;z-index:12;right:max(16px,calc((100vw - 980px)/2));bottom:14px;display:flex;align-items:center;justify-content:space-between;width:min(400px,calc(100vw - 32px));padding:9px 10px 9px 14px;border:1px solid rgba(20,27,24,.16);border-radius:12px;background:rgba(255,255,255,.94);box-shadow:0 14px 35px rgba(26,31,28,.18);backdrop-filter:blur(12px)}.trip-sticky small,.trip-sticky strong{display:block}.trip-sticky small{color:var(--muted);font-size:10px}.trip-sticky strong{margin-top:2px;font-family:var(--font-mono);font-size:17px}.trip-sticky button{border:0;border-radius:8px;background:#1d2925;color:#fff;padding:10px 15px;font-weight:650;cursor:pointer}.trip-sticky button:disabled{opacity:.5}@media(max-width:700px){.trip-builder{padding-top:0}.trip-builder__head{display:block;margin:5px 0 14px}.trip-builder__head p{margin-top:8px}.trip-prompt__controls{flex-wrap:wrap}.trip-prompt__controls .el-button{margin-left:auto}.plan-switcher{overflow:auto;display:flex;padding-bottom:2px}.plan-switcher button{min-width:156px}.editable-item{grid-template-columns:36px 78px minmax(0,1fr) 24px;gap:8px}.item-order span{display:none}.editable-item :deep(.media-image){width:78px;height:76px;min-height:0}.item-actions{flex-direction:column}.item-actions button{width:20px;height:19px}.trip-workspace__summary{padding:13px}.trip-workspace__summary h2{font-size:16px}.trip-sticky{right:16px;bottom:10px}}
.trip-summary-actions{display:flex;align-items:flex-end;gap:10px}.trip-summary-actions>div{text-align:right}.trip-summary-actions>button{border:1px solid var(--line);border-radius:7px;background:var(--panel-soft);color:var(--ink);padding:6px 8px;font-size:10px;cursor:pointer}.trip-share-poster{overflow:hidden;border:1px solid var(--line);border-radius:12px;background:#f8f9f7}.trip-share-poster header{padding:22px 20px 16px;background:#26322e;color:#fff}.trip-share-poster header span{color:#c4d2cc;font-size:10px}.trip-share-poster h2{margin:8px 0 4px;font-size:24px}.trip-share-poster header p{margin:0;color:#d7e2dc;font-family:var(--font-mono);font-size:12px}.trip-share-poster article{display:grid;grid-template-columns:54px 88px minmax(0,1fr);gap:9px;align-items:center;padding:10px;border-bottom:1px solid var(--line);background:#fff}.trip-share-poster__time{font-size:9px;color:var(--muted)}.trip-share-poster__time b,.trip-share-poster__time span{display:block}.trip-share-poster__time span{margin-top:4px;font-family:var(--font-mono);font-size:8px}.trip-share-poster article :deep(.media-image){min-height:74px;border-radius:7px}.trip-share-poster article>div:last-child{min-width:0}.trip-share-poster article small{display:block;overflow:hidden;color:var(--muted);font-size:9px;text-overflow:ellipsis;white-space:nowrap}.trip-share-poster article strong{display:block;overflow:hidden;margin:4px 0 2px;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.trip-share-poster article p{display:-webkit-box;overflow:hidden;margin:0;color:var(--muted);font-size:10px;line-height:1.35;-webkit-line-clamp:2;-webkit-box-orient:vertical}.trip-share-poster footer{display:flex;justify-content:space-between;gap:8px;padding:11px 14px;background:#f3f5f2;color:#5b6863;font-size:10px}.trip-share-poster footer span{font-weight:700}.trip-share-poster footer small{font-size:9px}@media(max-width:700px){.trip-summary-actions{gap:6px}.trip-share-poster article{grid-template-columns:44px 72px minmax(0,1fr)}.trip-share-poster article :deep(.media-image){min-height:66px}}
</style>
