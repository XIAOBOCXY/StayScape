<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { merchantApi } from '../../api'
import { errorMessage } from '../../api/client'
import MetricCard from '../../components/MetricCard.vue'
import type { PartnerResource } from '../../types'

const loading = ref(true)
const data = ref<Record<string, any> | null>(null)
const resources = ref<PartnerResource[]>([])
async function load() { loading.value = true; try { const [summary, resourceResponse] = await Promise.all([merchantApi.dashboard(), merchantApi.resources()]); data.value = summary.data; resources.value = resourceResponse.data } catch (e) { errorMessage(e) } finally { loading.value = false } }
function statusLabel(status: string) { return ({ AVAILABLE: '可组包', LOW_CAPACITY: '名额紧张', SOLD_OUT: '已售罄', SUSPENDED: '已暂停', TERMINATED: '已终止' } as Record<string, string>)[status] || status }
function statusType(status: string) { return status === 'AVAILABLE' ? 'success' : status === 'LOW_CAPACITY' ? 'warning' : 'danger' }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">PARTNER WORKSPACE</div><h1>{{ data?.merchant?.name || '商户工作台' }}</h1><p>实时更新活动场次、结算价格和剩余名额；受影响的酒店产品会自动重算。</p></div><el-button type="primary" @click="$router.push('/merchant/resources')">管理我的资源</el-button></div>
  <div v-if="loading" class="panel empty-state">正在读取商户资源…</div>
  <template v-else-if="data">
    <div class="metric-grid"><MetricCard label="可用资源" :value="data.resource_count" hint="当前账号名下" /><MetricCard label="可用名额" :value="data.available_capacity" hint="实时剩余容量" accent="#c9963e" /><MetricCard label="产品引用" :value="data.package_references" hint="酒店产品引用次数" accent="#7c6ab0" /><MetricCard label="库存预警" :value="data.low_stock_resources" hint="剩余 ≤ 5 个名额" accent="#c54b45" /></div>
    <div class="section-title compact-title"><div><h2>资源概览</h2><small class="muted">紧凑卡片只展示实时运营字段，详细描述在“我的资源”查看</small></div><span>{{ resources.length }} 项</span></div>
    <div class="merchant-resource-grid"><article v-for="item in resources" :key="item.id" class="resource-compact-card"><div class="resource-card-head"><div><span class="resource-kicker">{{ item.category }}</span><h3>{{ item.resource_name }}</h3></div><el-tag :type="statusType(item.status)" effect="light">{{ statusLabel(item.status) }}</el-tag></div><div class="resource-meta"><span>{{ item.available_date }}</span><span>{{ item.start_time?.slice(0,5) || '--' }}–{{ item.end_time?.slice(0,5) || '--' }}</span></div><div class="resource-numbers"><div><strong>{{ item.remaining_capacity }}</strong><small>remaining seats</small></div><div><strong>¥{{ item.settlement_price }}</strong><small>结算价 / 套</small></div></div><div class="resource-card-foot"><span>被 {{ item.referenced_product_count }} 款产品引用</span><span v-if="!item.package_enabled" class="warning-text">组包已关闭</span></div></article></div>
    <div v-if="!resources.length" class="panel empty-state">当前还没有可管理的合作资源。</div>
  </template>
</template>

<style scoped>
.compact-title{margin-top:28px}.merchant-resource-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;align-items:stretch}.resource-compact-card{min-height:205px;padding:18px;border:1px solid var(--line);border-radius:14px;background:linear-gradient(145deg,#fff,#f7fbf8);display:flex;flex-direction:column;gap:13px;transition:transform .2s,box-shadow .2s,border-color .2s}.resource-compact-card:hover{transform:translateY(-2px);border-color:#9ac8b8;box-shadow:0 12px 28px rgba(24,73,62,.09)}.resource-card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:9px}.resource-kicker{font-size:10px;color:var(--teal);letter-spacing:.12em}.resource-card-head h3{font-size:15px;line-height:1.35;margin:5px 0 0}.resource-meta{display:flex;justify-content:space-between;gap:7px;color:var(--muted);font-size:11px;padding-bottom:10px;border-bottom:1px solid var(--line)}.resource-numbers{display:grid;grid-template-columns:1fr 1fr;gap:10px}.resource-numbers strong{display:block;color:var(--teal-dark);font:22px Georgia,serif}.resource-numbers small{display:block;color:var(--muted);font-size:10px;margin-top:3px}.resource-card-foot{display:flex;justify-content:space-between;gap:8px;margin-top:auto;color:var(--muted);font-size:11px}.warning-text{color:#a8732c}@media(min-width:1500px){.merchant-resource-grid{grid-template-columns:repeat(5,minmax(230px,1fr))}}@media(max-width:700px){.merchant-resource-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:480px){.merchant-resource-grid{grid-template-columns:1fr}}
</style>
