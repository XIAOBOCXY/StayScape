<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { labelCategory, labelCrowds } from '../../utils/labels'
import { errorMessage } from '../../api/client'
import DateHeatmap from '../../components/DateHeatmap.vue'
import MediaImage from '../../components/MediaImage.vue'
import ResourceImagePicker from '../../components/ResourceImagePicker.vue'
import StatusTag from '../../components/StatusTag.vue'
import type { Merchant, PartnerResource } from '../../types'
import { automaticNetworkMedia, MEDIA_LIBRARY } from '../../utils/productMedia'

const route = useRoute()
const items = ref<PartnerResource[]>([])
const loading = ref(false)
const switchingId = ref<number | null>(null)
const selected = ref<PartnerResource | null>(null)
const detailVisible = ref(false)
const selectedDate = ref('')
const viewMode = ref<'cards' | 'list'>('cards')
const savingMedia = ref(false)
const savingAddress = ref(false)
const merchants = ref<Merchant[]>([])
const createVisible = ref(false)
const creating = ref(false)
const editingResourceId = ref<number | null>(null)
const createCrowds = ref<string[]>(['ALL'])
const createForm = ref<Record<string, any>>({})
const showSessionFields = ref(false)
const visibleItems = computed(() => selectedDate.value ? items.value.filter((item) => item.available_date === selectedDate.value) : items.value)
const disablePastDates = (value: Date) => value.getTime() < new Date(new Date().setHours(0, 0, 0, 0)).getTime()

function localDate() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
function openCreate() {
  editingResourceId.value = null
  showSessionFields.value = false
  createForm.value = {
    merchant_id: merchants.value[0]?.id || 0,
    resource_name: '', category: 'CULTURE', description: '', available_date: selectedDate.value || localDate(),
    start_time: '', end_time: '', remaining_capacity: 20, settlement_price: 80, market_price: 128,
    indoor: true, weather_tags: 'RAIN,SUNNY,CLOUDY', address: '', booking_notice: '', cancellation_rule: '',
    package_enabled: true, source_type: 'PARTNER', image_url: '', image_source: '', image_attribution: '',
  }
  createCrowds.value = ['ALL']
  createVisible.value = true
}

function openEdit(row: PartnerResource) {
  editingResourceId.value = row.id
  createForm.value = {
    merchant_id: row.merchant_id,
    resource_name: row.resource_name,
    category: row.category,
    description: row.description || '',
    available_date: row.available_date,
    start_time: row.start_time || '',
    end_time: row.end_time || '',
    remaining_capacity: row.remaining_capacity,
    settlement_price: Number(row.settlement_price),
    market_price: Number(row.market_price),
    indoor: row.indoor,
    weather_tags: row.weather_tags || 'RAIN,SUNNY,CLOUDY',
    address: row.address || '',
    booking_notice: row.booking_notice || '',
    cancellation_rule: row.cancellation_rule || '',
    package_enabled: row.package_enabled,
    source_type: row.source_type,
    image_url: row.image_url || '',
    image_source: row.image_source || '',
    image_attribution: row.image_attribution || '',
  }
  createCrowds.value = String(row.suitable_crowds || 'ALL').split(',').filter(Boolean)
  showSessionFields.value = Boolean(row.start_time || row.end_time)
  detailVisible.value = false
  createVisible.value = true
}

function resourceMedia(row: PartnerResource) {
  if (row.image_url) return { ...MEDIA_LIBRARY.city, id: `resource-${row.id}`, url: row.image_url, source: row.image_source || '商户图片', source_url: row.image_attribution || row.image_url }
  const text = `${row.resource_name} ${row.category} ${row.description}`.toLowerCase()
  const fallback = /博物馆|良渚|丝绸|美术|展览/.test(text) ? MEDIA_LIBRARY.liangzhuMuseum
    : /西湖|湖滨/.test(text) ? MEDIA_LIBRARY.westLake
      : /运河|拱宸/.test(text) ? MEDIA_LIBRARY.gongchen
        : /西溪|湿地|自然/.test(text) ? MEDIA_LIBRARY.xixi
          : /茶|龙井/.test(text) ? MEDIA_LIBRARY.longjing
            : /灵隐/.test(text) ? MEDIA_LIBRARY.lingyin
              : /乐园|宋城|游乐/.test(text) ? MEDIA_LIBRARY.songcheng
                : /动漫|动画/.test(text) ? MEDIA_LIBRARY.animationMuseum
                  : /攀岩|运动|卡丁车/.test(text) ? MEDIA_LIBRARY.climbing
                    : /演出|音乐|剧场/.test(text) ? MEDIA_LIBRARY.performance
                      : /美食|餐|咖啡/.test(text) ? MEDIA_LIBRARY.warmFood
                        : MEDIA_LIBRARY.city
  return automaticNetworkMedia(`${row.resource_name} ${row.address || '杭州'} ${row.category || ''}`, fallback.kind)
}
function session(row: PartnerResource) { return row.start_time && row.end_time ? `${row.start_time.slice(0, 5)} – ${row.end_time.slice(0, 5)}` : '预约后确认时间' }
function addressNeedsDetail(value: unknown) {
  const text = String(value || '').trim()
  return text.length < 10 || !(/\d+\s*(?:号|弄|幢|栋|座|室)|(?:路|街|巷)\s*\d+/.test(text))
}
function openDetails(row: PartnerResource) { selected.value = row; detailVisible.value = true }
async function load() { loading.value = true; try { const [resourceResponse, merchantResponse] = await Promise.all([hotelApi.resources(), hotelApi.merchants()]); items.value = resourceResponse.data; merchants.value = merchantResponse.data; const focus = items.value.find((item) => item.id === Number(route.query.focus)); if (focus) openDetails(focus) } catch (error) { ElMessage.error(errorMessage(error)) } finally { loading.value = false } }
async function createResource() {
  const form = createForm.value
  if (!form.merchant_id || !String(form.resource_name || '').trim() || !form.available_date) { ElMessage.warning('请填写合作商户、资源名称和可用日期'); return }
  if (addressNeedsDetail(form.address)) { ElMessage.warning('请填写包含区县、道路门牌或明确场馆入口的详细地址'); return }
  if (Number(form.remaining_capacity) < 0 || Number(form.settlement_price) < 0 || Number(form.market_price) < 0) { ElMessage.warning('名额和价格不能为负数'); return }
  if (form.start_time && form.end_time && form.start_time >= form.end_time) { ElMessage.warning('结束时间应晚于开始时间'); return }
  creating.value = true
  try {
    const payload = { ...form, resource_name: String(form.resource_name).trim(), address: String(form.address).trim(), suitable_crowds: createCrowds.value.includes('ALL') ? 'ALL' : createCrowds.value.join(','), start_time: form.start_time || null, end_time: form.end_time || null }
    const response = editingResourceId.value
      ? await hotelApi.updateResource(editingResourceId.value, payload)
      : await hotelApi.createResource(payload)
    if (editingResourceId.value) {
      const index = items.value.findIndex((item) => item.id === response.data.id)
      if (index >= 0) items.value[index] = response.data
    } else items.value = [response.data, ...items.value]
    selectedDate.value = response.data.available_date
    createVisible.value = false
    ElMessage.success(editingResourceId.value ? '合作资源已更新' : '合作资源已添加')
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { creating.value = false }
}
async function toggle(row: PartnerResource, enabled: boolean) { const previous = row.package_enabled; row.package_enabled = enabled; switchingId.value = row.id; try { const response = await hotelApi.toggleResourcePackage(row.id, enabled); row.package_enabled = response.data.package_enabled; ElMessage.success(row.package_enabled ? '已加入可组包资源' : '已暂停组包') } catch (error) { row.package_enabled = previous; ElMessage.error(errorMessage(error)) } finally { switchingId.value = null } }
async function saveMedia() { if (!selected.value) return; savingMedia.value = true; try { const response = await hotelApi.updateResourceMedia(selected.value.id, { image_url: selected.value.image_url || '', image_source: selected.value.image_source || '', image_attribution: selected.value.image_attribution || '' }); selected.value = response.data; const index = items.value.findIndex((item) => item.id === response.data.id); if (index >= 0) items.value[index] = response.data; ElMessage.success('资源图片已更新') } catch (error) { ElMessage.error(errorMessage(error)) } finally { savingMedia.value = false } }
async function saveAddress() {
  if (!selected.value) return
  const address = String(selected.value.address || '').trim()
  if (addressNeedsDetail(address)) { ElMessage.warning('请填写包含区县、道路门牌或明确场馆入口的详细地址'); return }
  savingAddress.value = true
  try {
    const response = await hotelApi.updateResourceAddress(selected.value.id, address)
    selected.value = response.data
    const index = items.value.findIndex((item) => item.id === response.data.id)
    if (index >= 0) items.value[index] = response.data
    ElMessage.success('详细地址已更新，后续路线推荐会按新地址重新判断')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { savingAddress.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page-head"><div><h1>合作资源池</h1><p>按日期查看合作体验；点击资源可在中央窗口查看完整内容。</p></div><div class="header-actions"><el-radio-group v-model="viewMode" class="view-mode-switch" size="small" aria-label="资源展示方式"><el-radio-button label="cards">卡片</el-radio-button><el-radio-button label="list">列表</el-radio-button></el-radio-group><el-button plain @click="load">刷新</el-button><el-button type="primary" @click="openCreate">添加合作资源</el-button></div></div>
  <div class="resource-toolbar panel"><DateHeatmap v-model="selectedDate" :items="items" quantity-key="remaining_capacity" label="体验日期" /></div>
  <div v-if="viewMode === 'cards'" v-loading="loading" class="resource-grid"><article v-for="row in visibleItems" :key="row.id" class="resource-card" @click="openDetails(row)"><MediaImage :media="resourceMedia(row)" aspect="card" /><div class="resource-card__body"><div class="resource-card__top"><span>{{ labelCategory(row.category) }}</span><strong :class="row.remaining_capacity <= 5 ? 'warning-text' : ''">余 {{ row.remaining_capacity }}</strong></div><h2>{{ row.resource_name }}</h2><p>{{ row.merchant_name || '合作商户' }} · {{ row.available_date }} · {{ session(row) }}</p><div class="resource-tags"><span v-if="row.indoor">室内</span><span v-if="row.suitable_crowds">适合 {{ labelCrowds(row.suitable_crowds) }}</span><span v-if="addressNeedsDetail(row.address)" class="address-warning">待补详细地址</span></div><div class="resource-card__bottom"><span>¥{{ row.settlement_price }} 结算</span><label @click.stop><el-switch :model-value="row.package_enabled" size="small" :loading="switchingId === row.id" @change="toggle(row, Boolean($event))" /><b>{{ row.package_enabled ? '可组包' : '未组包' }}</b></label></div></div></article></div>
  <div v-else class="panel table-wrap"><el-table v-loading="loading" :data="visibleItems" style="width:100%" @row-click="openDetails"><el-table-column prop="resource_name" label="资源名称" min-width="220"><template #default="{row}"><strong>{{ row.resource_name }}</strong><div class="muted">{{ row.merchant_name || '合作商户' }}</div></template></el-table-column><el-table-column prop="available_date" label="日期" width="120" /><el-table-column label="场次" width="145"><template #default="{row}">{{ session(row) }}</template></el-table-column><el-table-column label="余量" width="90"><template #default="{row}"><strong :class="row.remaining_capacity <= 5 ? 'warning-text' : ''">{{ row.remaining_capacity }}</strong></template></el-table-column><el-table-column label="结算价" width="100"><template #default="{row}">¥{{ row.settlement_price }}</template></el-table-column><el-table-column label="状态" width="100"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="组包" width="132"><template #default="{row}"><div class="switch-cell" @click.stop><el-switch :model-value="row.package_enabled" :loading="switchingId === row.id" @change="toggle(row, Boolean($event))" /><span>{{ row.package_enabled ? '可组包' : '未组包' }}</span></div></template></el-table-column><el-table-column label="详情" width="80"><template #default="{row}"><el-button link type="primary" @click.stop="openDetails(row)">查看</el-button></template></el-table-column></el-table></div>
  <div v-if="!loading && !visibleItems.length" class="panel empty-state">这一天暂时没有合作资源。</div>
  <el-dialog v-model="createVisible" :title="editingResourceId ? '编辑合作资源' : '添加合作资源'" width="min(94vw, 760px)" top="6vh" destroy-on-close>
    <el-form label-position="top" class="create-resource-form">
      <section class="resource-form-section">
        <h3>基础信息</h3>
        <div class="form-grid">
          <el-form-item label="合作商户" required><el-select v-model="createForm.merchant_id" placeholder="选择合作商户" style="width:100%"><el-option v-for="merchant in merchants" :key="merchant.id" :label="merchant.merchant_name" :value="merchant.id" /></el-select></el-form-item>
          <el-form-item label="资源名称" required><el-input v-model="createForm.resource_name" maxlength="160" placeholder="例如：良渚文化体验课" /></el-form-item>
          <el-form-item label="资源类型"><el-select v-model="createForm.category" style="width:100%"><el-option label="文化体验" value="CULTURE"/><el-option label="演出剧场" value="PERFORMANCE"/><el-option label="夜游" value="NIGHTLIFE"/><el-option label="美食体验" value="FOOD"/><el-option label="运动体验" value="SPORT"/><el-option label="娱乐体验" value="ENTERTAINMENT"/><el-option label="旅拍" value="PHOTO"/></el-select></el-form-item>
        </div>
      </section>
      <section class="resource-form-section">
        <h3>使用规则</h3>
        <div class="form-grid">
          <el-form-item label="可用日期" required><el-date-picker v-model="createForm.available_date" type="date" value-format="YYYY-MM-DD" format="YYYY-MM-DD" :disabled-date="disablePastDates" style="width:100%" /></el-form-item>
          <el-form-item label="适合人群"><el-select v-model="createCrowds" multiple collapse-tags placeholder="不限人群" style="width:100%"><el-option label="不限人群" value="ALL"/><el-option label="双人同行" value="COUPLE"/><el-option label="亲子家庭" value="FAMILY"/><el-option label="朋友同行" value="FRIENDS"/><el-option label="独自出行" value="SOLO"/></el-select></el-form-item>
          <div class="session-control"><el-button size="small" plain @click="showSessionFields = !showSessionFields">{{ showSessionFields ? '收起体验场次' : '+ 添加体验场次' }}</el-button></div>
          <template v-if="showSessionFields"><el-form-item label="开始时间"><el-time-picker v-model="createForm.start_time" value-format="HH:mm:ss" format="HH:mm" placeholder="选择开始时间" style="width:100%" /></el-form-item><el-form-item label="结束时间"><el-time-picker v-model="createForm.end_time" value-format="HH:mm:ss" format="HH:mm" placeholder="选择结束时间" style="width:100%" /></el-form-item></template>
          <el-form-item label="预约要求" class="form-grid__wide"><el-input v-model="createForm.booking_notice" placeholder="例如：提前一天预约" /></el-form-item>
        </div>
      </section>
      <section class="resource-form-section">
        <h3>供应信息</h3>
        <div class="form-grid"><el-form-item label="库存 / 名额" required><el-input-number v-model="createForm.remaining_capacity" :min="0" :max="100000" style="width:100%" /></el-form-item><el-form-item label="合作结算价 / 人" required><el-input-number v-model="createForm.settlement_price" :min="0" :precision="2" :step="10" style="width:100%" /></el-form-item><el-form-item label="市场参考价 / 人" required><el-input-number v-model="createForm.market_price" :min="0" :precision="2" :step="10" style="width:100%" /></el-form-item></div>
      </section>
      <section class="resource-form-section">
        <h3>资源描述</h3>
        <el-form-item label="介绍"><el-input v-model="createForm.description" type="textarea" :rows="3" maxlength="1200" placeholder="写清体验内容和时长" /></el-form-item>
        <el-form-item label="详细地址" required><el-input v-model="createForm.address" maxlength="255" placeholder="填写区县、道路门牌或场馆具体入口" /></el-form-item>
      </section>
      <section class="resource-form-section resource-form-section--last"><h3>AI 推荐设置</h3><el-checkbox v-model="createForm.package_enabled">允许加入酒店套餐推荐</el-checkbox></section>
      <span v-if="!merchants.length" class="form-warning">请先添加合作商户，再录入合作资源。</span>
    </el-form>
    <template #footer><el-button @click="createVisible=false">取消</el-button><el-button type="primary" :loading="creating" :disabled="!merchants.length" @click="createResource">{{ editingResourceId ? '保存修改' : '添加资源' }}</el-button></template>
  </el-dialog>
  <el-dialog v-model="detailVisible" :title="selected?.resource_name || '资源详情'" width="min(94vw, 880px)" top="7vh" destroy-on-close><div v-if="selected" class="resource-detail"><MediaImage :media="resourceMedia(selected)" aspect="hero" /><div class="resource-detail__content"><div class="detail-kicker">{{ labelCategory(selected.category) }} · {{ selected.merchant_name || '合作商户' }}</div><div class="detail-title"><div><h2>{{ selected.resource_name }}</h2><p>{{ selected.description || '在地体验内容' }}</p></div><strong :class="selected.remaining_capacity <= 5 ? 'warning-text' : ''">余 {{ selected.remaining_capacity }}</strong></div><div class="detail-stat-grid"><div><span>日期</span><b>{{ selected.available_date }}</b></div><div><span>时间</span><b>{{ session(selected) }}</b></div><div><span>结算价</span><b>¥{{ selected.settlement_price }}</b></div><div><span>已被引用</span><b>{{ selected.referenced_product_count }} 款产品</b></div></div><div class="detail-rows"><div><span>地点</span><strong>{{ selected.address || '—' }}</strong></div><div><span>适合人群</span><strong>{{ selected.suitable_crowds ? labelCrowds(selected.suitable_crowds) : '不限人群' }}</strong></div><div><span>预约要求</span><strong>{{ selected.booking_notice || '无需预约' }}</strong></div></div><div class="resource-media-edit"><span>展示图片</span><ResourceImagePicker v-model="selected.image_url" v-model:source="selected.image_source" v-model:attribution="selected.image_attribution" :query="`${selected.resource_name} ${selected.address || '杭州'}`" /><el-button size="small" type="primary" :loading="savingMedia" @click="saveMedia">保存图片</el-button></div></div></div><template #footer><el-button @click="detailVisible=false">关闭</el-button><el-button v-if="selected" plain @click="openEdit(selected)">编辑资源</el-button><el-button v-if="selected" type="primary" plain @click="toggle(selected, !selected.package_enabled)">{{ selected.package_enabled ? '暂停组包' : '允许组包' }}</el-button></template></el-dialog>
</template>

<style scoped>
.header-actions,.resource-toolbar{display:flex;align-items:center;gap:10px}.header-actions{justify-content:flex-end;flex-wrap:wrap}.view-mode-switch{order:-1}.resource-toolbar{margin-bottom:12px;padding:10px}.resource-toolbar :deep(.date-heatmap){width:100%;border:0;padding:0;background:transparent}.resource-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:10px}.resource-card{display:grid;grid-template-columns:104px minmax(0,1fr);min-height:146px;overflow:hidden;border:1px solid var(--line);border-radius:12px;background:var(--paper);cursor:pointer;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}.resource-card:hover{transform:translateY(-2px);border-color:#b9c8c2;box-shadow:0 12px 26px rgba(20,25,23,.08)}.resource-card :deep(.media-image){height:100%;min-height:146px;aspect-ratio:auto;border-radius:0}.resource-card__body{min-width:0;padding:11px}.resource-card__top,.resource-card__bottom,.detail-title{display:flex;align-items:center;justify-content:space-between;gap:10px}.resource-card__top>span,.detail-kicker{color:var(--muted);font-size:10px}.resource-card__top>strong{font-family:var(--font-mono);font-size:14px}.resource-card h2{overflow:hidden;margin:7px 0 4px;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.resource-card p{overflow:hidden;margin:0;color:var(--muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.resource-tags{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}.resource-tags span{padding:3px 6px;border:1px solid var(--line);border-radius:999px;color:var(--muted);font-size:9px}.resource-card__bottom{padding-top:8px;border-top:1px solid var(--line);color:var(--ink);font-family:var(--font-mono);font-size:11px}.resource-card__bottom label,.switch-cell{display:flex;align-items:center;gap:6px;font-family:inherit}.resource-card__bottom b,.switch-cell span{color:var(--muted);font-size:10px;font-weight:500}.resource-detail{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:18px}.resource-detail>:first-child{min-height:400px;border-radius:10px}.resource-detail__content{min-width:0}.detail-kicker{margin-top:4px;letter-spacing:.08em}.detail-title{align-items:flex-start;margin:9px 0 15px}.detail-title h2{margin:0 0 7px;font-size:22px;letter-spacing:-.3px}.detail-title p{margin:0;color:var(--muted);font-size:13px;line-height:1.65}.detail-title>strong{flex:0 0 auto;font-family:var(--font-mono);font-size:16px}.detail-stat-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.detail-stat-grid div{padding:10px;border:1px solid var(--line);border-radius:9px;background:var(--panel-soft)}.detail-stat-grid span{display:block;color:var(--muted);font-size:10px}.detail-stat-grid b{display:block;margin-top:5px;font-family:var(--font-mono);font-size:12px}.detail-rows{margin-top:10px;border-top:1px solid var(--line)}.detail-rows div{display:grid;grid-template-columns:78px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)}.detail-rows span{color:var(--muted);font-size:11px}.detail-rows strong{font-size:12px;font-weight:550;line-height:1.55}.address-warning{border-color:#e9b8a9!important;color:#9a5142!important;background:#fff8f5}.resource-address-edit{display:grid;gap:7px;margin-top:12px;padding-top:10px;border-top:1px solid var(--line)}.resource-address-edit>label{color:var(--muted);font-size:11px}.resource-address-edit>.el-button{justify-self:start}.form-help{display:block;color:var(--muted);font-size:11px;line-height:1.5}.resource-media-edit{margin-top:12px;padding-top:10px;border-top:1px solid var(--line)}.resource-media-edit>span{display:block;margin-bottom:7px;color:var(--muted);font-size:11px}.resource-media-edit>.el-button{margin-top:8px}.create-hint{margin:0 0 16px;line-height:1.6}.create-resource-form .form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 14px}.create-resource-form .form-grid .el-form-item{margin-bottom:12px}.create-switches{display:flex;gap:18px;flex-wrap:wrap}.form-warning{display:block;margin-top:5px;color:#a85a4c;font-size:12px}@media(max-width:760px){.header-actions{justify-content:flex-start;margin-top:12px}.resource-toolbar{align-items:stretch;flex-direction:column}.resource-grid{grid-template-columns:1fr}.resource-card{grid-template-columns:96px minmax(0,1fr);min-height:128px}.resource-card :deep(.media-image){min-height:128px}.resource-card__body{padding:9px}.resource-detail{grid-template-columns:1fr}.resource-detail>:first-child{min-height:190px;height:190px}.detail-title h2{font-size:19px}.create-resource-form .form-grid{grid-template-columns:1fr}}
</style>

<style scoped>
.resource-form-section { margin:0 0 18px; padding:15px 16px 4px; border:1px solid var(--line); border-radius:12px; background:#fff; }
.resource-form-section h3 { margin:0 0 14px; color:#36574d; font-size:13px; font-weight:700; }
.resource-form-section--last { margin-bottom:0; padding-bottom:14px; }
.resource-form-section .form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0 16px; }
.resource-form-section .form-grid__wide { grid-column:1/-1; }
.session-control { display:flex; align-items:flex-start; margin:2px 0 12px; }
.create-resource-form :deep(.el-form-item) { margin-bottom:12px; }
@media(max-width:760px) { .resource-form-section .form-grid { grid-template-columns:1fr; } .resource-form-section .form-grid__wide { grid-column:auto; } }
</style>
