<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { Room } from '../../types'
const items = ref<Room[]>([]); const loading = ref(false); const dialog = ref(false); const saving = ref(false); const current = ref<Room | null>(null)
const form = reactive({ room_type: '', available_date: '', available_count: 0, normal_price: '0', minimum_price: '0', accounting_cost: '0', max_guests: 2, features: '', status: 'AVAILABLE', reason: '酒店维护临期客房' })
async function load() { loading.value = true; try { items.value = (await hotelApi.rooms()).data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
function resetForm() { Object.assign(form, { room_type: '', available_date: '', available_count: 0, normal_price: '0', minimum_price: '0', accounting_cost: '0', max_guests: 2, features: '', status: 'AVAILABLE', reason: '酒店维护临期客房' }) }
function openCreate() { current.value = null; resetForm(); dialog.value = true }
function open(row: Room) { current.value = row; Object.assign(form, { room_type: row.room_type, available_date: row.available_date, available_count: row.available_count, normal_price: String(row.normal_price), minimum_price: String(row.minimum_price), accounting_cost: String(row.accounting_cost), max_guests: row.max_guests, features: row.features, status: row.status, reason: '酒店调整临期客房日期、房量或价格' }); dialog.value = true }
async function save() {
  if (!form.room_type.trim() || !form.available_date) { ElMessage.warning('请填写房型和临期日期'); return }
  if (Number(form.minimum_price) > Number(form.normal_price)) { ElMessage.warning('最低售价不能高于正常售价'); return }
  saving.value = true
  try {
    const payload = { ...form, room_type: form.room_type.trim(), available_count: Number(form.available_count), normal_price: form.normal_price, minimum_price: form.minimum_price, accounting_cost: form.accounting_cost, max_guests: Number(form.max_guests), status: form.status, reason: form.reason }
    if (current.value) { await hotelApi.updateRoom(current.value.id, payload); ElMessage.success('临期客房已更新，受影响产品已重算') }
    else { await hotelApi.createRoom(payload); ElMessage.success('临期客房已新增，可用于生成主题产品') }
    dialog.value = false; await load()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">ROOM INVENTORY</div><h1>临期客房</h1><p>维护临期日期、房型、房量、售价和核算成本；每次调整都会进入动态重算链路。</p></div><div><el-button plain @click="load">刷新</el-button><el-button type="primary" @click="openCreate">＋ 新增临期客房</el-button></div></div>
  <div class="panel table-wrap"><el-table v-loading="loading" :data="items" style="width:100%"><el-table-column prop="room_type" label="房型" min-width="150"><template #default="{row}"><strong>{{ row.room_type }}</strong><div class="muted line-clamp">{{ row.features || '未填写房型特色' }}</div></template></el-table-column><el-table-column prop="available_date" label="入住日期" width="125" /><el-table-column label="当前库存" width="120"><template #default="{ row }"><strong>{{ row.available_count }}</strong> 间</template></el-table-column><el-table-column prop="normal_price" label="正常价" width="110"><template #default="{ row }">¥{{ row.normal_price }}</template></el-table-column><el-table-column prop="minimum_price" label="最低价" width="110"><template #default="{ row }">¥{{ row.minimum_price }}</template></el-table-column><el-table-column prop="accounting_cost" label="核算成本" width="115"><template #default="{ row }">¥{{ row.accounting_cost }}</template></el-table-column><el-table-column label="状态" width="110"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="open(row)">编辑客房</el-button></template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">暂无客房库存，先新增一间临期房型。</div></div>
  <el-dialog v-model="dialog" :title="current ? '编辑临期客房' : '新增临期客房'" width="620px"><el-form label-position="top"><div class="form-grid"><el-form-item label="房型" required><el-input v-model="form.room_type" placeholder="例如：亲子房" /></el-form-item><el-form-item label="临期日期" required><el-date-picker v-model="form.available_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="可售房量"><el-input-number v-model="form.available_count" :min="0" :max="999" style="width:100%" /></el-form-item><el-form-item label="最多入住人数"><el-input-number v-model="form.max_guests" :min="1" :max="20" style="width:100%" /></el-form-item><el-form-item label="正常售价"><el-input v-model="form.normal_price"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="最低售价"><el-input v-model="form.minimum_price"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="核算成本"><el-input v-model="form.accounting_cost"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="状态"><el-select v-model="form.status" style="width:100%"><el-option label="可售" value="AVAILABLE" /><el-option label="停用" value="DISABLED" /></el-select></el-form-item><el-form-item class="full" label="房型特色"><el-input v-model="form.features" placeholder="例如：儿童用品、家庭空间、亲子主题" /></el-form-item><el-form-item class="full" label="调整原因"><el-input v-model="form.reason" type="textarea" :rows="2" /></el-form-item></div></el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存并重算</el-button></template></el-dialog>
</template>
