<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { TravelProduct } from '../../types'

const router = useRouter(); const items = ref<TravelProduct[]>([]); const loading = ref(false); const status = ref('')
async function load() { loading.value = true; try { items.value = (await hotelApi.products(status.value || undefined)).data.items } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
async function remove(row: TravelProduct) { try { await ElMessageBox.confirm(`确定删除“${row.product_name}”吗？已有预约意向的产品会归档。`, '删除产品', { type: 'warning' }); const response = await hotelApi.deleteProduct(row.id); ElMessage.success(response.data.message); await load() } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(errorMessage(e)) } }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">PRODUCT POOL</div><h1>当前产品池</h1><p>查看、发布、暂停、编辑和删除酒店生成的主题住宿产品；点击产品进入完整成本、时间与营销素材。</p></div><div><el-button plain @click="load">刷新</el-button><el-button type="primary" @click="router.push('/hotel/products/generate')">＋ 生成新方案</el-button></div></div>
  <div class="panel filter-bar"><el-radio-group v-model="status" @change="load"><el-radio-button label="">全部</el-radio-button><el-radio-button label="DRAFT">草稿</el-radio-button><el-radio-button label="ON_SALE">在售</el-radio-button><el-radio-button label="LOW_STOCK">库存紧张</el-radio-button><el-radio-button label="PAUSED">已暂停</el-radio-button></el-radio-group></div>
  <div class="panel table-wrap"><el-table v-loading="loading" :data="items" style="width:100%"><el-table-column label="产品" min-width="250"><template #default="{row}"><strong>{{ row.product_name }}</strong><div class="muted">{{ row.theme }} · {{ row.target_crowd }} · {{ row.weather }}</div></template></el-table-column><el-table-column prop="target_date" label="入住日期" width="125" /><el-table-column label="库存" width="90"><template #default="{row}"><strong :class="row.sale_quantity <= 2 ? 'warning-text' : ''">{{ row.sale_quantity }} 套</strong></template></el-table-column><el-table-column label="售价 / 毛利" width="145"><template #default="{row}">¥{{ row.suggested_price }}<div class="muted">毛利 {{ (Number(row.gross_margin) * 100).toFixed(2) }}%</div></template></el-table-column><el-table-column label="状态" width="110"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="操作" width="190"><template #default="{row}"><el-button link type="primary" @click="router.push(`/hotel/products/${row.id}`)">查看 / 编辑</el-button><el-button link type="danger" @click="remove(row)">删除</el-button></template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">暂无符合条件的产品。</div></div>
</template>

<style scoped>
.filter-bar{margin-bottom:16px}.filter-bar :deep(.el-radio-group){display:flex;flex-wrap:wrap;gap:8px}.filter-bar :deep(.el-radio-button__inner){border-left:1px solid var(--line);border-radius:999px!important;box-shadow:none!important}
</style>
