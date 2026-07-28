<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { Room } from '../../types'
const items = ref<Room[]>([]); const loading = ref(false); const dialog = ref(false); const saving = ref(false); const current = ref<Room | null>(null); const form = reactive({ available_count: 0, reason: '酒店调整临期客房库存' })
async function load() { loading.value = true; try { items.value = (await hotelApi.rooms()).data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
function open(row: Room) { current.value = row; form.available_count = row.available_count; form.reason = '酒店调整临期客房库存'; dialog.value = true }
async function save() { if (!current.value) return; saving.value = true; try { await hotelApi.updateRoom(current.value.id, { available_count: form.available_count, reason: form.reason }); ElMessage.success('库存已更新，受影响产品已重算'); dialog.value = false; await load() } catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false } }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">ROOM INVENTORY</div><h1>临期客房</h1><p>维护当日及次日仍未售出的房量，所有变化都会进入动态运营链路。</p></div><el-button plain @click="load">刷新</el-button></div>
  <div class="panel table-wrap"><el-table v-loading="loading" :data="items" style="width:100%"><el-table-column prop="room_type" label="房型" min-width="150" /><el-table-column prop="available_date" label="入住日期" width="125" /><el-table-column label="当前库存" width="120"><template #default="{ row }"><strong>{{ row.available_count }}</strong> 间</template></el-table-column><el-table-column prop="normal_price" label="正常价" width="110"><template #default="{ row }">¥{{ row.normal_price }}</template></el-table-column><el-table-column prop="minimum_price" label="最低价" width="110"><template #default="{ row }">¥{{ row.minimum_price }}</template></el-table-column><el-table-column prop="accounting_cost" label="核算成本" width="115"><template #default="{ row }">¥{{ row.accounting_cost }}</template></el-table-column><el-table-column label="状态" width="110"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="操作" width="100" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="open(row)">调库存</el-button></template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">暂无客房库存</div></div>
  <el-dialog v-model="dialog" title="调整临期库存" width="420px"><el-form label-width="90px"><el-form-item label="房型"><span>{{ current?.room_type }}</span></el-form-item><el-form-item label="当前数量"><span>{{ current?.available_count }} 间</span></el-form-item><el-form-item label="新库存"><el-input-number v-model="form.available_count" :min="0" :max="999" /></el-form-item><el-form-item label="调整原因"><el-input v-model="form.reason" type="textarea" :rows="3" /></el-form-item></el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">提交并重算</el-button></template></el-dialog>
</template>

