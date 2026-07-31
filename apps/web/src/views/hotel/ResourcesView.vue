<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { PartnerResource } from '../../types'
const items = ref<PartnerResource[]>([]); const loading = ref(false); const switchingId = ref<number | null>(null)
async function load() { loading.value = true; try { items.value = (await hotelApi.resources()).data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
async function toggle(row: PartnerResource, enabled: boolean) {
  const previous = row.package_enabled
  row.package_enabled = enabled
  switchingId.value = row.id
  try {
    const response = await hotelApi.toggleResourcePackage(row.id, enabled)
    row.package_enabled = response.data.package_enabled
    ElMessage.success(row.package_enabled ? '已允许酒店组包' : '已暂停酒店组包')
  } catch (e) {
    row.package_enabled = previous
    ElMessage.error(errorMessage(e))
  } finally { switchingId.value = null }
}
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">PARTNER RESOURCE POOL</div><h1>合作资源池</h1><p>酒店只能管理组包许可，商户名额、结算价格和资源状态由合作商户维护。</p></div><el-button plain @click="load">刷新</el-button></div>
  <div class="panel table-wrap"><el-table v-loading="loading" :data="items" style="width:100%"><el-table-column prop="resource_name" label="资源名称" min-width="170"><template #default="{ row }"><strong>{{ row.resource_name }}</strong><div class="muted">{{ row.merchant_name }}</div></template></el-table-column><el-table-column prop="category" label="类别" width="115" /><el-table-column prop="available_date" label="日期" width="120" /><el-table-column label="实时名额" width="110"><template #default="{ row }"><strong :class="row.remaining_capacity <= 5 ? 'warning-text' : ''">{{ row.remaining_capacity }}</strong></template></el-table-column><el-table-column label="结算价" width="100"><template #default="{ row }">¥{{ row.settlement_price }}</template></el-table-column><el-table-column label="资源状态" width="110"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="组包许可" width="145"><template #default="{ row }"><div class="switch-cell"><el-switch :model-value="row.package_enabled" :loading="switchingId === row.id" @change="toggle(row, Boolean($event))" /><span :class="row.package_enabled ? 'enabled-text' : 'muted'">{{ row.package_enabled ? '允许组包' : '未允许' }}</span></div></template></el-table-column><el-table-column label="引用产品" width="100"><template #default="{ row }">{{ row.referenced_product_count }} 个</template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">暂无合作资源</div></div>
</template>

<style scoped>
.switch-cell{display:flex;align-items:center;gap:8px}.enabled-text{color:var(--teal);font-size:12px;font-weight:600}
</style>
