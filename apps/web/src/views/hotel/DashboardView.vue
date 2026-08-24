<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import MetricCard from '../../components/MetricCard.vue'
import ProductCard from '../../components/ProductCard.vue'
import StatusTag from '../../components/StatusTag.vue'
import type { Dashboard, TravelProduct } from '../../types'

const loading = ref(true)
const error = ref('')
const dashboard = ref<Dashboard | null>(null)
const products = ref<TravelProduct[]>([])
const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | undefined
let socket: WebSocket | undefined
const auth = useAuthStore()
const offSaleProductCount = computed(() => Math.max(0, Number(dashboard.value?.product_count || 0) - Number(dashboard.value?.on_sale_product_count || 0)))

function renderChart() {
  if (!chartEl.value || !dashboard.value) return
  chart?.dispose()
  chart = echarts.init(chartEl.value)
  chart.setOption({
    grid: { left: 24, right: 20, top: 20, bottom: 25, containLabel: true },
    xAxis: { type: 'category', data: ['临期房量', '在售产品', '暂未在售', '预约意向'], axisLine: { lineStyle: { color: '#dfe9e4' } }, axisLabel: { color: '#71817c' } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf2ef' } }, axisLabel: { color: '#9aa9a4' } },
    series: [{ type: 'bar', barWidth: 30, data: [dashboard.value.available_room_units, dashboard.value.on_sale_product_count, offSaleProductCount.value, dashboard.value.visitor_intent_count], itemStyle: { color: '#566d66', borderRadius: [6, 6, 0, 0] } }]
  })
}

function resizeChart() { chart?.resize() }
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [summary, productResponse] = await Promise.all([hotelApi.dashboard(), hotelApi.products()])
    dashboard.value = summary.data
    products.value = productResponse.data.items
    await nextTick()
    renderChart()
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

function connect() {
  if (!dashboard.value || !auth.token) return
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${protocol}://${location.host}/ws/hotel/${dashboard.value.hotel_id}?token=${encodeURIComponent(auth.token)}`)
  socket.onmessage = () => { ElMessage.info('资源发生变化，经营数据已刷新'); load() }
  socket.onerror = () => socket?.close()
}

onMounted(async () => { await load(); connect(); window.addEventListener('resize', resizeChart) })
onBeforeUnmount(() => { socket?.close(); chart?.dispose(); window.removeEventListener('resize', resizeChart) })
</script>

<template>
  <div class="page-head">
    <div><div class="eyebrow">HOTEL OPERATIONS</div><h1>经营总览</h1><p>把临期库存变成有主题、有毛利、可动态运营的杭州体验。</p></div>
    <div class="header-actions"><el-button plain @click="load">刷新数据</el-button><el-button type="primary" @click="$router.push('/hotel/products/generate')">✦ 生成主题产品</el-button></div>
  </div>
  <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />
  <div v-if="loading" class="panel empty-state">正在读取真实库存与产品数据…</div>
  <template v-else-if="dashboard">
    <div class="metric-grid">
      <div class="metric-link" @click="$router.push('/hotel/rooms')"><MetricCard label="临期客房" :value="dashboard.available_room_units" hint="明日待售房量 · 点击查看" accent="#0f766e" /></div>
      <div class="metric-link" @click="$router.push('/hotel/products')"><MetricCard label="在售产品" :value="dashboard.on_sale_product_count" :hint="`共 ${dashboard.product_count} 个产品 · 点击查看`" accent="#498c70" /></div>
      <div class="metric-link" @click="$router.push('/hotel/products')"><MetricCard label="暂未在售" :value="offSaleProductCount" hint="草稿、暂停或库存紧张 · 点击查看" accent="#b28350" /></div>
      <div class="metric-link" @click="$router.push('/hotel/intents')"><MetricCard label="预约意向" :value="dashboard.visitor_intent_count" hint="点击查看游客需求" accent="#7c6ab0" /></div>
    </div>

    <div class="section-title"><h2>当前产品池</h2><span>{{ dashboard.target_date }} · 点击产品查看完整内容</span></div>
    <div v-if="products.length" class="product-grid"><ProductCard v-for="product in products" :key="product.id" :product="product" /></div>
    <div v-else class="panel empty-state">还没有主题产品，先从一间临期客房开始组包。</div>

    <div class="section-title"><h2>最近动态</h2><span>资源变化会触发产品重算</span></div>
    <div class="panel table-wrap"><table class="data-table"><thead><tr><th>事件</th><th>资源</th><th>处理结果</th><th>时间</th></tr></thead><tbody><tr v-for="change in dashboard.recent_changes" :key="String(change.id)"><td>{{ change.event_type }}</td><td>{{ change.resource_type }} #{{ change.resource_id }}</td><td><StatusTag :status="change.processed ? 'AVAILABLE' : 'DRAFT'" /></td><td class="muted">{{ String(change.created_at).replace('T', ' ').slice(0, 16) }}</td></tr><tr v-if="!dashboard.recent_changes.length"><td colspan="4" class="empty-state">暂无动态调整记录</td></tr></tbody></table></div>
  </template>
  <div v-if="dashboard" class="panel signal-panel"><div class="section-title"><h2>经营信号</h2><span>来自当前数据库快照</span></div><div ref="chartEl" style="height: 250px; width: 100%" /></div>
</template>

<style scoped>
.header-actions{display:flex;align-items:center;gap:10px}.metric-link{cursor:pointer;transition:transform .2s}.metric-link:hover{transform:translateY(-3px)}.resource-snapshot-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.resource-snapshot{border:1px solid var(--line);border-radius:12px;background:#fff;padding:16px;text-align:left;color:var(--ink);cursor:pointer;box-shadow:var(--shadow);transition:.2s}.resource-snapshot:hover{border-color:#7bb8a8;box-shadow:0 15px 35px rgba(30,72,64,.12);transform:translateY(-2px)}.resource-snapshot p{margin:11px 0}.resource-snapshot__hint{display:block;margin-top:14px;color:var(--teal);font-size:10px;letter-spacing:.1em}.signal-panel{margin-top:18px}.data-table td.empty-state{height:100px;text-align:center}@media(max-width:900px){.resource-snapshot-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.header-actions{margin-top:12px}.page-head{display:block}.resource-snapshot-grid{grid-template-columns:1fr}}
</style>
