<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import DateHeatmap from '../../components/DateHeatmap.vue'
import MediaImage from '../../components/MediaImage.vue'
import StatusTag from '../../components/StatusTag.vue'
import type { Room } from '../../types'
import { MEDIA_LIBRARY } from '../../utils/productMedia'

const items = ref<Room[]>([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const current = ref<Room | null>(null)
const selectedDate = ref('')
const viewMode = ref<'cards' | 'list'>('cards')
const form = reactive({ room_type: '', available_date: '', available_count: 0, normal_price: '0', minimum_price: '0', accounting_cost: '0', max_guests: 2, features: '', status: 'AVAILABLE', reason: '酒店维护临期客房' })

const visibleItems = computed(() => selectedDate.value ? items.value.filter((item) => item.available_date === selectedDate.value) : items.value)

function roomMedia(row: Room) {
  const text = `${row.room_type} ${row.features}`.toLowerCase()
  if (/亲子|儿童|家庭/.test(text)) return MEDIA_LIBRARY.familyRoom
  if (/景观|湖|窗/.test(text)) return MEDIA_LIBRARY.hotelWindow
  return MEDIA_LIBRARY.hotel
}

async function load() { loading.value = true; try { items.value = (await hotelApi.rooms()).data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
function resetForm() { Object.assign(form, { room_type: '', available_date: '', available_count: 0, normal_price: '0', minimum_price: '0', accounting_cost: '0', max_guests: 2, features: '', status: 'AVAILABLE', reason: '酒店维护临期客房' }) }
function openCreate() { current.value = null; resetForm(); dialog.value = true }
function open(row: Room) { current.value = row; Object.assign(form, { room_type: row.room_type, available_date: row.available_date, available_count: row.available_count, normal_price: String(row.normal_price), minimum_price: String(row.minimum_price), accounting_cost: String(row.accounting_cost), max_guests: row.max_guests, features: row.features, status: row.status, reason: '酒店调整临期客房日期、房量或价格' }); dialog.value = true }
async function save() {
  if (!form.room_type.trim() || !form.available_date) { ElMessage.warning('请填写房型和临期日期'); return }
  if (Number(form.minimum_price) > Number(form.normal_price)) { ElMessage.warning('最低售价不能高于正常售价'); return }
  saving.value = true
  try {
    const payload = { ...form, room_type: form.room_type.trim(), available_count: Number(form.available_count), max_guests: Number(form.max_guests) }
    if (current.value) { await hotelApi.updateRoom(current.value.id, payload); ElMessage.success('客房已更新，相关产品会自动重算') }
    else { await hotelApi.createRoom(payload); ElMessage.success('临期客房已新增，可用于生成方案') }
    dialog.value = false; await load()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">客房库存</div><h1>临期客房</h1><p>按日期查看待售房型；点击卡片可调整房量与价格。</p></div><div class="header-actions"><el-button plain @click="load">刷新</el-button><el-button type="primary" @click="openCreate">新增客房</el-button></div></div>
  <div class="inventory-toolbar panel"><DateHeatmap v-model="selectedDate" :items="items" quantity-key="available_count" label="入住日期" /><el-radio-group v-model="viewMode" size="small"><el-radio-button label="cards">卡片</el-radio-button><el-radio-button label="list">列表</el-radio-button></el-radio-group></div>
  <div v-if="viewMode === 'cards'" v-loading="loading" class="inventory-grid">
    <button v-for="row in visibleItems" :key="row.id" class="inventory-card" @click="open(row)"><MediaImage :media="roomMedia(row)" aspect="card" /><div class="inventory-card__body"><div class="row-top"><span>{{ row.available_date }}</span><StatusTag :status="row.status" /></div><h2>{{ row.room_type }}</h2><p>{{ row.features || '可在编辑中补充房型亮点' }}</p><div class="room-facts"><span><b>{{ row.available_count }}</b> 间可售</span><span>最多 {{ row.max_guests }} 人</span></div><div class="price-line"><strong>¥{{ row.minimum_price }}</strong><small>最低可售价 · 常规 ¥{{ row.normal_price }}</small></div></div></button>
  </div>
  <div v-else class="panel table-wrap"><el-table v-loading="loading" :data="visibleItems" style="width:100%" @row-click="open"><el-table-column prop="room_type" label="房型" min-width="190"><template #default="{row}"><strong>{{ row.room_type }}</strong><div class="muted line-clamp">{{ row.features || '未填写房型亮点' }}</div></template></el-table-column><el-table-column prop="available_date" label="入住日期" width="125" /><el-table-column label="可售" width="92"><template #default="{row}"><strong>{{ row.available_count }}</strong> 间</template></el-table-column><el-table-column label="最低价" width="110"><template #default="{row}">¥{{ row.minimum_price }}</template></el-table-column><el-table-column label="成本" width="105"><template #default="{row}">¥{{ row.accounting_cost }}</template></el-table-column><el-table-column label="状态" width="105"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="操作" width="90"><template #default="{row}"><el-button link type="primary" @click.stop="open(row)">调整</el-button></template></el-table-column></el-table></div>
  <div v-if="!loading && !visibleItems.length" class="panel empty-state">这一天暂时没有临期客房。</div>
  <el-dialog v-model="dialog" :title="current ? '调整临期客房' : '新增临期客房'" width="min(94vw, 620px)"><el-form label-position="top"><div class="form-grid"><el-form-item label="房型" required><el-input v-model="form.room_type" placeholder="例如：亲子房" /></el-form-item><el-form-item label="入住日期" required><el-date-picker v-model="form.available_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="可售房量"><el-input-number v-model="form.available_count" :min="0" :max="999" style="width:100%" /></el-form-item><el-form-item label="最多入住人数"><el-input-number v-model="form.max_guests" :min="1" :max="20" style="width:100%" /></el-form-item><el-form-item label="常规售价"><el-input v-model="form.normal_price"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="最低可售价"><el-input v-model="form.minimum_price"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="核算成本"><el-input v-model="form.accounting_cost"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="状态"><el-select v-model="form.status" style="width:100%"><el-option label="可售" value="AVAILABLE" /><el-option label="停用" value="DISABLED" /></el-select></el-form-item><el-form-item class="full" label="房型亮点"><el-input v-model="form.features" placeholder="例如：儿童用品、家庭空间、窗景" /></el-form-item><el-form-item class="full" label="调整说明"><el-input v-model="form.reason" type="textarea" :rows="2" /></el-form-item></div></el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
</template>

<style scoped>
.header-actions,.inventory-toolbar{display:flex;align-items:center;gap:10px}.inventory-toolbar{justify-content:space-between;margin-bottom:14px;padding:12px}.inventory-toolbar :deep(.date-heatmap){flex:1;border:0;padding:0;background:transparent}.inventory-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(235px,1fr));gap:12px}.inventory-card{overflow:hidden;padding:0;border:1px solid var(--line);border-radius:12px;background:var(--paper);color:var(--ink);text-align:left;cursor:pointer;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}.inventory-card:hover{transform:translateY(-2px);border-color:#b9c8c2;box-shadow:0 16px 32px rgba(20,25,23,.08)}.inventory-card :deep(.media-image){height:118px}.inventory-card__body{padding:12px}.row-top,.price-line{display:flex;align-items:center;justify-content:space-between;gap:8px}.row-top>span{color:var(--muted);font-family:var(--font-mono);font-size:11px}.inventory-card h2{margin:9px 0 5px;font-size:15px}.inventory-card p{display:-webkit-box;min-height:32px;overflow:hidden;margin:0;color:var(--muted);font-size:11px;line-height:1.5;-webkit-box-orient:vertical;-webkit-line-clamp:2}.room-facts{display:flex;gap:9px;margin:11px 0;color:var(--muted);font-size:11px}.room-facts b{color:var(--ink);font-family:var(--font-mono);font-size:14px}.price-line{padding-top:10px;border-top:1px solid var(--line)}.price-line strong{font-family:var(--font-mono);font-size:17px}.price-line small{color:var(--muted);font-size:10px}@media(max-width:700px){.page-head,.inventory-toolbar{align-items:stretch;flex-direction:column}.header-actions{justify-content:flex-end}.inventory-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.inventory-card :deep(.media-image){height:92px}.inventory-card__body{padding:10px}.room-facts{flex-direction:column;gap:3px}.price-line{align-items:flex-start;flex-direction:column;gap:2px}}
</style>
