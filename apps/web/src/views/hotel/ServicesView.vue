<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import DateHeatmap from '../../components/DateHeatmap.vue'
import MediaImage from '../../components/MediaImage.vue'
import StatusTag from '../../components/StatusTag.vue'
import type { HotelService } from '../../types'
import { MEDIA_LIBRARY } from '../../utils/productMedia'

const items = ref<HotelService[]>([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const current = ref<HotelService | null>(null)
const selectedDate = ref('')
const viewMode = ref<'cards' | 'list'>('cards')
const form = reactive({ available_date: '', available_quantity: 0, start_time: '', end_time: '', status: 'AVAILABLE', reason: '酒店服务时间与名额调整' })
const visibleItems = computed(() => selectedDate.value ? items.value.filter((item) => item.available_date === selectedDate.value) : items.value)

function serviceMedia(row: HotelService) {
  const text = `${row.service_name} ${row.service_type}`.toLowerCase()
  if (/早餐|餐|咖啡|下午茶|美食/.test(text)) return MEDIA_LIBRARY.breakfast
  if (/茶/.test(text)) return MEDIA_LIBRARY.teaSet
  return MEDIA_LIBRARY.hotelWindow
}
function session(row: HotelService) { return row.start_time && row.end_time ? `${row.start_time.slice(0, 5)} – ${row.end_time.slice(0, 5)}` : '到店后确认时间' }
async function load() { loading.value = true; try { items.value = (await hotelApi.services()).data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
function open(row: HotelService) { current.value = row; Object.assign(form, { available_date: row.available_date, available_quantity: row.available_quantity, start_time: row.start_time?.slice(0, 5) || '', end_time: row.end_time?.slice(0, 5) || '', status: row.status, reason: '酒店服务时间与名额调整' }); dialog.value = true }
async function save() { if (!current.value) return; if (form.start_time && form.end_time && form.start_time >= form.end_time) { ElMessage.warning('开始时间应早于结束时间'); return } saving.value = true; try { await hotelApi.updateService(current.value.id, { ...form, start_time: form.start_time || undefined, end_time: form.end_time || undefined }); ElMessage.success('服务名额已更新，相关产品会自动重算'); dialog.value = false; await load() } catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false } }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">酒店服务</div><h1>酒店服务</h1><p>早餐、延迟退房、寄存和停车等服务，可按日期和名额快速查看。</p></div><el-button plain @click="load">刷新</el-button></div>
  <div class="service-toolbar panel"><DateHeatmap v-model="selectedDate" :items="items" quantity-key="available_quantity" label="服务日期" /><el-radio-group v-model="viewMode" size="small"><el-radio-button label="cards">卡片</el-radio-button><el-radio-button label="list">列表</el-radio-button></el-radio-group></div>
  <div v-if="viewMode === 'cards'" v-loading="loading" class="service-grid"><button v-for="row in visibleItems" :key="row.id" class="service-card" @click="open(row)"><MediaImage :media="serviceMedia(row)" aspect="card" /><div class="service-card__body"><div class="service-card__top"><span>{{ row.available_date }}</span><StatusTag :status="row.status" /></div><h2>{{ row.service_name }}</h2><p>{{ session(row) }}</p><div class="service-card__facts"><span><b>{{ row.available_quantity }}</b> 个可用名额</span><span>¥{{ row.unit_cost }} / 份</span></div></div></button></div>
  <div v-else class="panel table-wrap"><el-table v-loading="loading" :data="visibleItems" style="width:100%" @row-click="open"><el-table-column prop="service_name" label="服务名称" min-width="190" /><el-table-column prop="available_date" label="日期" width="120" /><el-table-column label="时间" width="150"><template #default="{row}">{{ session(row) }}</template></el-table-column><el-table-column label="剩余名额" width="110"><template #default="{row}"><strong>{{ row.available_quantity }}</strong></template></el-table-column><el-table-column label="成本" width="100"><template #default="{row}">¥{{ row.unit_cost }}</template></el-table-column><el-table-column label="状态" width="100"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="操作" width="90"><template #default="{row}"><el-button link type="primary" @click.stop="open(row)">调整</el-button></template></el-table-column></el-table></div>
  <div v-if="!loading && !visibleItems.length" class="panel empty-state">这一天暂时没有可用服务。</div>
  <el-dialog v-model="dialog" title="调整服务名额与时间" width="min(94vw, 520px)"><el-form label-position="top"><el-form-item label="服务"><strong>{{ current?.service_name }}</strong></el-form-item><el-form-item label="服务日期"><el-date-picker v-model="form.available_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="服务时间"><div class="time-row"><el-time-picker v-model="form.start_time" value-format="HH:mm" format="HH:mm" placeholder="开始" /><el-time-picker v-model="form.end_time" value-format="HH:mm" format="HH:mm" placeholder="结束" /></div></el-form-item><el-form-item label="可用名额"><el-input-number v-model="form.available_quantity" :min="0" :max="9999" style="width:100%" /></el-form-item><el-form-item label="状态"><el-select v-model="form.status" style="width:100%"><el-option label="可用" value="AVAILABLE" /><el-option label="暂停" value="SUSPENDED" /><el-option label="不可用" value="UNAVAILABLE" /></el-select></el-form-item><el-form-item label="调整说明"><el-input v-model="form.reason" type="textarea" :rows="2" /></el-form-item></el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
</template>

<style scoped>
.service-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px;padding:12px}.service-toolbar :deep(.date-heatmap){flex:1;border:0;padding:0;background:transparent}.service-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}.service-card{overflow:hidden;padding:0;border:1px solid var(--line);border-radius:12px;background:var(--paper);color:var(--ink);text-align:left;cursor:pointer;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}.service-card:hover{transform:translateY(-2px);border-color:#b9c8c2;box-shadow:0 16px 32px rgba(20,25,23,.08)}.service-card :deep(.media-image){height:108px}.service-card__body{padding:12px}.service-card__top,.service-card__facts{display:flex;align-items:center;justify-content:space-between;gap:8px}.service-card__top>span{color:var(--muted);font-family:var(--font-mono);font-size:11px}.service-card h2{margin:9px 0 4px;font-size:15px}.service-card p{margin:0;color:var(--muted);font-size:11px}.service-card__facts{margin-top:13px;padding-top:10px;border-top:1px solid var(--line);color:var(--muted);font-size:10px}.service-card__facts b{color:var(--ink);font-family:var(--font-mono);font-size:14px}.time-row{display:flex;gap:8px;width:100%}.time-row :deep(.el-date-editor){flex:1}@media(max-width:700px){.service-toolbar{align-items:stretch;flex-direction:column}.service-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.service-card :deep(.media-image){height:88px}.service-card__body{padding:10px}.service-card__facts{align-items:flex-start;flex-direction:column;gap:3px}}
</style>
