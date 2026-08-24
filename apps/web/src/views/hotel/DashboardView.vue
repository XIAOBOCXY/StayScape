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
const revenueChartEl = ref<HTMLElement | null>(null)
const listingChartEl = ref<HTMLElement | null>(null)
let revenueChart: echarts.ECharts | undefined
let listingChart: echarts.ECharts | undefined
let socket: WebSocket | undefined
const auth = useAuthStore()
const offSaleProductCount = computed(() => Math.max(0, Number(dashboard.value?.product_count || 0) - Number(dashboard.value?.on_sale_product_count || 0)))
const currency = (value: string | number | undefined) => `¥${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`

function renderCharts() {
  if (!dashboard.value) return
  const points = dashboard.value.sales_timeline || []
  const labels = points.map((item) => item.date.slice(5).replace('-', '/'))
  const grid = { left: 18, right: 20, top: 38, bottom: 28, containLabel: true }
  const axis = { axisLine: { lineStyle: { color: '#d9dbd7' } }, axisLabel: { color: '#777b77', fontSize: 10 }, splitLine: { lineStyle: { color: '#eceeeb' } } }
  const tooltip = { trigger: 'axis', backgroundColor: '#252725', borderWidth: 0, textStyle: { color: '#fff' } }

  if (revenueChartEl.value) {
    revenueChart?.dispose()
    revenueChart = echarts.init(revenueChartEl.value)
    revenueChart.setOption({
      color: ['#3d4d48', '#9a7135'], tooltip, legend: { top: 4, right: 4, textStyle: { color: '#6f726f', fontSize: 10 }, itemWidth: 10, itemHeight: 7 }, grid,
      xAxis: { type: 'category', data: labels, boundaryGap: true, ...axis },
      yAxis: { type: 'value', axisLabel: { color: '#777b77', fontSize: 10, formatter: (value: number) => `¥${value}` }, splitLine: axis.splitLine },
      series: [
        { name: '已确认成交额', type: 'bar', barMaxWidth: 24, data: points.map((item) => Number(item.confirmed_revenue)), itemStyle: { borderRadius: [4, 4, 0, 0] } },
        { name: '已确认毛利', type: 'line', smooth: true, symbolSize: 5, data: points.map((item) => Number(item.confirmed_gross_profit)), lineStyle: { width: 2 } },
      ],
    })
  }
  if (listingChartEl.value) {
    listingChart?.dispose()
    listingChart = echarts.init(listingChartEl.value)
    listingChart.setOption({
      color: ['#6e857c', '#4c7181'], tooltip, legend: { top: 4, right: 4, textStyle: { color: '#6f726f', fontSize: 10 }, itemWidth: 10, itemHeight: 7 }, grid,
      xAxis: { type: 'category', data: labels, boundaryGap: true, ...axis },
      yAxis: [
        { type: 'value', name: '可售套数', nameTextStyle: { color: '#777b77', fontSize: 10 }, axisLabel: { color: '#777b77', fontSize: 10 }, splitLine: axis.splitLine },
        { type: 'value', name: '货值', nameTextStyle: { color: '#777b77', fontSize: 10 }, axisLabel: { color: '#777b77', fontSize: 10, formatter: (value: number) => `¥${value}` }, splitLine: { show: false } },
      ],
      series: [
        { name: '当前可售套数', type: 'bar', barMaxWidth: 22, data: points.map((item) => item.available_packages), itemStyle: { borderRadius: [4, 4, 0, 0] } },
        { name: '当前在售货值', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 5, data: points.map((item) => Number(item.listed_value)), lineStyle: { width: 2 } },
      ],
    })
  }
}

function resizeCharts() { revenueChart?.resize(); listingChart?.resize() }
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [summary, productResponse] = await Promise.all([hotelApi.dashboard(), hotelApi.products()])
    dashboard.value = summary.data
    products.value = productResponse.data.items
    await nextTick()
    renderCharts()
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

onMounted(async () => { await load(); connect(); window.addEventListener('resize', resizeCharts) })
onBeforeUnmount(() => { socket?.close(); revenueChart?.dispose(); listingChart?.dispose(); window.removeEventListener('resize', resizeCharts) })
</script>

<template>
  <div class="page-head">
    <div><div class="eyebrow">经营总览</div><h1>经营总览</h1><p>查看临期客房、在售产品、预约意向与最近变动。</p></div>
    <div class="header-actions"><el-button plain @click="load">刷新数据</el-button><el-button type="primary" @click="$router.push('/hotel/products/generate')">✦ 生成主题产品</el-button></div>
  </div>
  <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />
  <div v-if="loading" class="panel empty-state">正在读取真实库存与产品数据…</div>
  <template v-else-if="dashboard">
    <div class="metric-grid metric-grid--sales">
      <div class="metric-link" @click="$router.push('/hotel/intents')"><MetricCard label="已确认成交额" :value="currency(dashboard.confirmed_revenue)" :hint="`${dashboard.confirmed_order_count} 单，未把暂留计入收入`" accent="#3d4d48" /></div>
      <div class="metric-link" @click="$router.push('/hotel/intents')"><MetricCard label="已确认毛利" :value="currency(dashboard.confirmed_gross_profit)" hint="只按酒店已确认的预约计算" accent="#9a7135" /></div>
      <div class="metric-link" @click="$router.push('/hotel/intents')"><MetricCard label="待确认金额" :value="currency(dashboard.held_revenue)" :hint="`${dashboard.held_order_count} 笔暂留，尚未计入成交`" accent="#7d7f89" /></div>
      <div class="metric-link" @click="$router.push('/hotel/products')"><MetricCard label="当前在售货值" :value="currency(dashboard.listed_value)" :hint="`${dashboard.available_package_count} 套仍可预约`" accent="#4c7181" /></div>
    </div>

    <section class="dashboard-charts">
      <article class="panel chart-panel"><header><div><span>已确认成交</span><h2>成交额与毛利趋势</h2></div><small>确认后才进入收入</small></header><div ref="revenueChartEl" class="dashboard-chart" /></article>
      <article class="panel chart-panel"><header><div><span>当前可售</span><h2>日期库存与在售货值</h2></div><small>按出发日期汇总</small></header><div ref="listingChartEl" class="dashboard-chart" /></article>
    </section>

    <div class="metric-grid metric-grid--operations">
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
</template>

<style scoped>
.header-actions{display:flex;align-items:center;gap:10px}.metric-link{cursor:pointer;transition:transform .2s}.metric-link:hover{transform:translateY(-3px)}.metric-grid--sales{margin-bottom:12px}.metric-grid--operations{margin-top:12px}.dashboard-charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:18px 0}.chart-panel{padding:14px 15px}.chart-panel header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.chart-panel header span{display:block;color:var(--muted);font-size:10px;letter-spacing:.08em}.chart-panel h2{margin:5px 0 0;font-size:15px}.chart-panel header small{margin-top:4px;color:var(--muted);font-size:10px;text-align:right}.dashboard-chart{width:100%;height:248px;margin-top:4px}.resource-snapshot-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.resource-snapshot{border:1px solid var(--line);border-radius:12px;background:#fff;padding:16px;text-align:left;color:var(--ink);cursor:pointer;box-shadow:var(--shadow);transition:.2s}.resource-snapshot:hover{border-color:#7bb8a8;box-shadow:0 15px 35px rgba(30,72,64,.12);transform:translateY(-2px)}.resource-snapshot p{margin:11px 0}.resource-snapshot__hint{display:block;margin-top:14px;color:var(--teal);font-size:10px;letter-spacing:.1em}.data-table td.empty-state{height:100px;text-align:center}@media(max-width:900px){.dashboard-charts,.resource-snapshot-grid{grid-template-columns:1fr}}@media(max-width:600px){.header-actions{margin-top:12px}.page-head{display:block}.dashboard-chart{height:220px}.resource-snapshot-grid{grid-template-columns:1fr}}
</style>
