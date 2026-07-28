<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { merchantApi } from '../../api'
import { errorMessage } from '../../api/client'
import MetricCard from '../../components/MetricCard.vue'
import type { PartnerResource } from '../../types'
const loading = ref(true); const data = ref<Record<string, any> | null>(null); const resources = ref<PartnerResource[]>([])
async function load() { loading.value = true; try { const [summary, resourceResponse] = await Promise.all([merchantApi.dashboard(), merchantApi.resources()]); data.value = summary.data; resources.value = resourceResponse.data } catch (e) { errorMessage(e) } finally { loading.value = false } }
onMounted(load)
</script>
<template><div class="page-head"><div><div class="eyebrow">PARTNER WORKSPACE</div><h1>{{ data?.merchant?.name || '商户工作台' }}</h1><p>实时更新活动场次、结算价格和剩余名额，受影响的酒店产品会自动重算。</p></div><el-button type="primary" @click="$router.push('/merchant/resources')">管理我的资源</el-button></div><div v-if="loading" class="panel empty-state">正在读取商户资源…</div><template v-else-if="data"><div class="metric-grid"><MetricCard label="可用资源" :value="data.resource_count" hint="当前账号名下" /><MetricCard label="可用名额" :value="data.available_capacity" hint="实时剩余容量" accent="#c9963e" /><MetricCard label="产品引用" :value="data.package_references" hint="酒店产品引用次数" accent="#7c6ab0" /><MetricCard label="库存预警" :value="data.low_stock_resources" hint="剩余 ≤ 5 个名额" accent="#c54b45" /></div><div class="section-title"><h2>资源概览</h2><span>点击“我的资源”进行名额调整</span></div><div class="product-grid"><div v-for="item in resources" :key="item.id" class="panel"><div class="product-card__top"><strong>{{ item.resource_name }}</strong><el-tag :type="item.remaining_capacity <= 5 ? 'warning' : 'success'" effect="light">余 {{ item.remaining_capacity }}</el-tag></div><p class="muted">{{ item.available_date }} · {{ item.start_time || '--' }} - {{ item.end_time || '--' }}</p><div class="product-card__resources"><span>结算 ¥{{ item.settlement_price }}</span><span>{{ item.referenced_product_count }} 个产品引用</span></div></div></div></template></template>

