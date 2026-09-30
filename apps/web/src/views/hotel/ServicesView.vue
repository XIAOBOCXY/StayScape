<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import DateHeatmap from '../../components/DateHeatmap.vue'
import MediaImage from '../../components/MediaImage.vue'
import ResourceImagePicker from '../../components/ResourceImagePicker.vue'
import StatusTag from '../../components/StatusTag.vue'
import type { HotelService } from '../../types'
import { automaticNetworkMedia, MEDIA_LIBRARY } from '../../utils/productMedia'

const items = ref<HotelService[]>([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const current = ref<HotelService | null>(null)
const selectedDate = ref('')
const viewMode = ref<'cards' | 'list'>('cards')
const form = reactive({ available_date: '', available_quantity: 0, unit_cost: '0', reference_price: '0', start_time: '', end_time: '', image_url: '', image_source: '', image_attribution: '', status: 'AVAILABLE', reason: '酒店服务时间与名额调整' })
const visibleItems = computed(() => selectedDate.value ? items.value.filter((item) => item.available_date === selectedDate.value) : items.value)

function serviceMedia(row: HotelService) {
  if (row.image_url) return { ...MEDIA_LIBRARY.hotelWindow, id: `service-${row.id}`, url: row.image_url, source: row.image_source || '商户图片', source_url: row.image_attribution || row.image_url }
  const text = `${row.service_name} ${row.service_type}`.toLowerCase()
  const fallback = /早餐|餐|咖啡|下午茶|美食/.test(text) ? MEDIA_LIBRARY.breakfast : /茶/.test(text) ? MEDIA_LIBRARY.teaSet : MEDIA_LIBRARY.hotelWindow
  return automaticNetworkMedia(`${row.service_name} 杭州酒店服务`, fallback.kind)
}
function session(row: HotelService) { return row.start_time && row.end_time ? `${row.start_time.slice(0, 5)} – ${row.end_time.slice(0, 5)}` : '到店后确认时间' }
async function load() { loading.value = true; try { items.value = (await hotelApi.services()).data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
function open(row: HotelService) { current.value = row; Object.assign(form, { available_date: row.available_date, available_quantity: row.available_quantity, unit_cost: String(row.unit_cost), reference_price: String(row.reference_price), start_time: row.start_time?.slice(0, 5) || '', end_time: row.end_time?.slice(0, 5) || '', image_url: row.image_url || '', image_source: row.image_source || '', image_attribution: row.image_attribution || '', status: row.status, reason: '酒店服务时间与名额调整' }); dialog.value = true }
async function save() { if (!current.value) return; if (form.start_time && form.end_time && form.start_time >= form.end_time) { ElMessage.warning('开始时间应早于结束时间'); return } saving.value = true; try { await hotelApi.updateService(current.value.id, { ...form, available_quantity: Number(form.available_quantity), unit_cost: Number(form.unit_cost), reference_price: Number(form.reference_price), start_time: form.start_time || undefined, end_time: form.end_time || undefined }); ElMessage.success('酒店服务已更新'); dialog.value = false; await load() } catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false } }
onMounted(load)
</script>

<template>
  <div v-toolbar class="header-actions"><el-radio-group v-model="viewMode" class="view-mode-switch" size="small" aria-label="服务展示方式"><el-radio-button label="cards">卡片</el-radio-button><el-radio-button label="list">列表</el-radio-button></el-radio-group><el-button plain @click="load">刷新</el-button></div>
  <div class="service-toolbar panel"><DateHeatmap v-model="selectedDate" :items="items" quantity-key="available_quantity" label="服务日期" /></div>
  <div v-if="viewMode === 'cards'" v-loading="loading" class="service-grid"><button v-for="row in visibleItems" :key="row.id" class="service-card" @click="open(row)"><MediaImage :media="serviceMedia(row)" aspect="card" /><div class="service-card__body"><div class="service-card__top"><span>{{ row.available_date }}</span><StatusTag :status="row.status" /></div><h2>{{ row.service_name }}</h2><p>{{ session(row) }}</p><div class="service-card__facts"><span><b>{{ row.available_quantity }}</b> 个可用名额</span><span>¥{{ row.unit_cost }} / 份</span></div></div></button></div>
  <div v-else class="panel table-wrap"><el-table v-loading="loading" :data="visibleItems" style="width:100%" @row-click="open"><el-table-column prop="service_name" label="服务名称" min-width="190" /><el-table-column prop="available_date" label="日期" width="120" /><el-table-column label="时间" width="150"><template #default="{row}">{{ session(row) }}</template></el-table-column><el-table-column label="剩余名额" width="110"><template #default="{row}"><strong>{{ row.available_quantity }}</strong></template></el-table-column><el-table-column label="成本" width="100"><template #default="{row}">¥{{ row.unit_cost }}</template></el-table-column><el-table-column label="状态" width="100"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="操作" width="90"><template #default="{row}"><el-button link type="primary" @click.stop="open(row)">调整</el-button></template></el-table-column></el-table></div>
  <div v-if="!loading && !visibleItems.length" class="panel empty-state">这一天暂时没有可用服务。</div>
  <el-dialog v-model="dialog" title="调整酒店服务" width="min(94vw, 680px)" class="service-dialog" top="6vh">
    <div v-if="current" class="service-dialog__head"><div><span class="eyebrow">酒店服务</span><h3>{{ current.service_name }}</h3></div><StatusTag :status="form.status" /></div>
    <el-form label-position="top" class="service-form">
      <section class="service-edit-section"><h3>使用规则</h3><div class="service-form__grid"><el-form-item label="可用日期"><el-date-picker v-model="form.available_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="状态"><el-select v-model="form.status" style="width:100%"><el-option label="可用" value="AVAILABLE" /><el-option label="暂停" value="SUSPENDED" /><el-option label="不可用" value="UNAVAILABLE" /></el-select></el-form-item><el-form-item label="开始时间"><el-time-picker v-model="form.start_time" value-format="HH:mm" format="HH:mm" placeholder="不固定时可留空" style="width:100%" /></el-form-item><el-form-item label="结束时间"><el-time-picker v-model="form.end_time" value-format="HH:mm" format="HH:mm" placeholder="不固定时可留空" style="width:100%" /></el-form-item></div></section>
      <section class="service-edit-section"><h3>供应信息</h3><div class="service-form__grid"><el-form-item label="可用名额"><el-input-number v-model="form.available_quantity" :min="0" :max="9999" style="width:100%" /></el-form-item><el-form-item label="单位成本"><el-input v-model="form.unit_cost"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="市场参考价"><el-input v-model="form.reference_price"><template #prepend>¥</template></el-input></el-form-item></div></section>
      <section class="service-edit-section"><h3>展示信息</h3><el-form-item label="服务图片"><ResourceImagePicker v-model="form.image_url" v-model:source="form.image_source" v-model:attribution="form.image_attribution" :query="`${current?.service_name || '杭州'} 酒店服务`" /></el-form-item></section>
      <el-form-item label="调整说明"><el-input v-model="form.reason" placeholder="例如：更新早餐接待名额" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存调整</el-button></template>
  </el-dialog>
</template>

<style scoped>
.header-actions,.service-toolbar{display:flex;align-items:center;gap:10px}.header-actions{justify-content:flex-end;flex-wrap:wrap}.view-mode-switch{order:-1}.service-toolbar{margin-bottom:12px;padding:10px}.service-toolbar :deep(.date-heatmap){width:100%;border:0;padding:0;background:transparent}.service-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}.service-card{display:grid;grid-template-columns:98px minmax(0,1fr);min-height:126px;overflow:hidden;padding:0;border:1px solid var(--line);border-radius:12px;background:var(--paper);color:var(--ink);text-align:left;cursor:pointer;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}.service-card:hover{transform:translateY(-2px);border-color:#b9c8c2;box-shadow:0 12px 26px rgba(20,25,23,.08)}.service-card :deep(.media-image){height:100%;min-height:126px;aspect-ratio:auto;border-radius:0}.service-card__body{min-width:0;padding:11px}.service-card__top,.service-card__facts{display:flex;align-items:center;justify-content:space-between;gap:8px}.service-card__top>span{color:var(--muted);font-family:var(--font-mono);font-size:10px}.service-card h2{margin:7px 0 4px;font-size:15px}.service-card p{margin:0;color:var(--muted);font-size:11px}.service-card__facts{margin-top:10px;padding-top:8px;border-top:1px solid var(--line);color:var(--muted);font-size:10px}.service-card__facts b{color:var(--ink);font-family:var(--font-mono);font-size:13px}.time-row{display:flex;gap:8px;width:100%}.time-row :deep(.el-date-editor){flex:1}
.service-dialog :deep(.el-dialog__body){padding-top:8px}
.service-dialog__head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.service-dialog__head h3{margin:5px 0 0;font-size:18px}
.service-dialog__stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:12px 0}
.service-dialog__stats>div{padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:var(--panel-soft)}
.service-dialog__stats small{display:block;color:var(--muted);font-size:10px}
.service-dialog__stats strong{display:block;margin-top:4px;font-family:var(--font-mono);font-size:17px}
.service-dialog__stats strong.is-target{color:var(--teal-dark)}
.service-form__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}
.service-form__grid .full{grid-column:1/-1}
.service-dialog__hint{float:left;color:var(--muted);font-size:11px;line-height:32px}
@media(max-width:620px){.service-dialog__stats{grid-template-columns:1fr 1fr}.service-form__grid{grid-template-columns:1fr}.service-dialog__hint{display:none}}@media(max-width:700px){.header-actions{justify-content:flex-start;margin-top:12px}.service-toolbar{align-items:stretch;flex-direction:column}.service-grid{grid-template-columns:1fr}.service-card{grid-template-columns:92px minmax(0,1fr);min-height:118px}.service-card :deep(.media-image){min-height:118px}.service-card__body{padding:9px}}
</style>

<style scoped>
.service-form { display:grid; gap:12px; }
.service-edit-section { padding:14px 15px 2px; border:1px solid var(--line); border-radius:12px; background:#fff; }
.service-edit-section h3 { margin:0 0 12px; color:#36574d; font-size:13px; }
.service-edit-section .service-form__grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0 14px; }
.service-form :deep(.el-form-item) { margin-bottom:12px; }
@media(max-width:620px) { .service-edit-section .service-form__grid { grid-template-columns:1fr; } }
</style>
