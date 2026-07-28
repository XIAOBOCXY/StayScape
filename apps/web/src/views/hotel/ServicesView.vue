<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { HotelService } from '../../types'
const items = ref<HotelService[]>([]); const loading = ref(false); const dialog = ref(false); const saving = ref(false); const current = ref<HotelService | null>(null); const form = reactive({ available_quantity: 0, reason: '酒店服务名额调整' })
async function load() { loading.value = true; try { items.value = (await hotelApi.services()).data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
function open(row: HotelService) { current.value = row; form.available_quantity = row.available_quantity; form.reason = '酒店服务名额调整'; dialog.value = true }
async function save() { if (!current.value) return; saving.value = true; try { await hotelApi.updateService(current.value.id, { available_quantity: form.available_quantity, reason: form.reason }); ElMessage.success('服务名额已更新，受影响产品已重算'); dialog.value = false; await load() } catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false } }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">HOTEL SERVICES</div><h1>酒店服务</h1><p>早餐、延迟退房、寄存和停车等服务是产品成本与容量的一部分。</p></div><el-button plain @click="load">刷新</el-button></div>
  <div class="panel table-wrap"><el-table v-loading="loading" :data="items" style="width:100%"><el-table-column prop="service_name" label="服务名称" min-width="150" /><el-table-column prop="service_type" label="类型" width="130" /><el-table-column prop="available_date" label="日期" width="120" /><el-table-column label="剩余数量" width="110"><template #default="{ row }"><strong>{{ row.available_quantity }}</strong></template></el-table-column><el-table-column label="单位成本" width="110"><template #default="{ row }">¥{{ row.unit_cost }}</template></el-table-column><el-table-column label="时间" width="150"><template #default="{ row }">{{ row.start_time || '--' }} - {{ row.end_time || '--' }}</template></el-table-column><el-table-column label="状态" width="110"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="操作" width="100"><template #default="{ row }"><el-button link type="primary" @click="open(row)">调名额</el-button></template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">暂无酒店服务</div></div>
  <el-dialog v-model="dialog" title="调整服务名额" width="420px"><el-form label-width="90px"><el-form-item label="服务"><span>{{ current?.service_name }}</span></el-form-item><el-form-item label="新名额"><el-input-number v-model="form.available_quantity" :min="0" :max="9999" /></el-form-item><el-form-item label="调整原因"><el-input v-model="form.reason" type="textarea" :rows="3" /></el-form-item></el-form><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">提交并重算</el-button></template></el-dialog>
</template>

