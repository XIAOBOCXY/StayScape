<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import MetricCard from '../../components/MetricCard.vue'
import DashboardProductCard from '../../components/DashboardProductCard.vue'
import type { Dashboard, TravelProduct } from '../../types'

const loading = ref(true)
const refreshing = ref(false)
const showingCached = ref(false)
const error = ref('')
const productLoading = ref(false)
const productError = ref('')
const dashboard = ref<Dashboard | null>(null)
const products = ref<TravelProduct[]>([])
function productPriority(product: TravelProduct) {
  const status = String(product.status || '').toUpperCase()
  const quantity = Number(product.sale_quantity || 0)
  if (quantity > 0 && (status === 'LOW_STOCK' || (status === 'ON_SALE' && quantity <= 2))) return 0
  if (quantity > 0 && ['ON_SALE', 'AVAILABLE'].includes(status)) return 1
  if (['PAUSED', 'SUSPENDED'].includes(status)) return 2
  return 3
}
const prioritizedProducts = computed(() => [...products.value].sort((a, b) => productPriority(a) - productPriority(b)))
const productLoaded = ref(false)
const productPoolEl = ref<HTMLElement | null>(null)
let productLoadSequence = 0
let productObserver: IntersectionObserver | undefined
let loadSequence = 0
const revenueChartEl = ref<HTMLElement | null>(null)
const listingChartEl = ref<HTMLElement | null>(null)
let revenueChart: echarts.ECharts | undefined
let listingChart: echarts.ECharts | undefined
let socket: WebSocket | undefined
const auth = useAuthStore()
const cacheKey = () => `stayscape-dashboard-${auth.user?.id || 'unknown'}`
function restoreCachedDashboard() {
  try {
    const raw = sessionStorage.getItem(cacheKey())
    if (!raw) return
    const cached = JSON.parse(raw) as { savedAt?: number; data?: Dashboard }
    if (!cached.data || !cached.savedAt || Date.now() - cached.savedAt > 10 * 60 * 1000) return
    dashboard.value = cached.data
    loading.value = false
    showingCached.value = true
  } catch { /* Ignore an invalid or unavailable tab cache. */ }
}
const offSaleProductCount = computed(() => Math.max(0, Number(dashboard.value?.product_count || 0) - Number(dashboard.value?.on_sale_product_count || 0)))
const currency = (value: string | number | undefined) => `¥${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`
async function renderCharts(requestId: number) {
  if (!dashboard.value) return
  const echarts = await import('echarts')
  if (requestId !== loadSequence || !dashboard.value) return
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
function scheduleCharts(requestId: number) {
  // Let the new metrics paint before parsing the large chart module.
  requestAnimationFrame(() => setTimeout(() => { void renderCharts(requestId).catch(() => undefined) }, 0))
}
async function loadProducts() {
  const requestId = ++productLoadSequence
  productLoading.value = true
  productError.value = ''
  try {
    const { data } = await hotelApi.products(undefined, 8, false)
    if (requestId === productLoadSequence) {
      products.value = Array.isArray(data.items) ? data.items : []
      productLoaded.value = true
    }
  } catch (e) {
    if (requestId === productLoadSequence) productError.value = errorMessage(e)
  } finally {
    if (requestId === productLoadSequence) productLoading.value = false
  }
}

async function load() {
  const requestId = ++loadSequence
  loading.value = !dashboard.value
  refreshing.value = true
  error.value = ''
  try {
    if (productLoaded.value) void loadProducts()
    const summary = await hotelApi.dashboard()
    // A previous successful request can still provide the first screen while
    // a newer refresh is pending. Never keep the skeleton for that race.
    if (requestId !== loadSequence && dashboard.value) return
    dashboard.value = summary.data
    error.value = ''
    showingCached.value = false
    loading.value = false
    try { sessionStorage.setItem(cacheKey(), JSON.stringify({ savedAt: Date.now(), data: summary.data })) } catch { /* Storage can be disabled. */ }
    await nextTick()
    scheduleCharts(loadSequence)
  } catch (e) {
    if (requestId === loadSequence) error.value = errorMessage(e)
  } finally {
    if (requestId === loadSequence) {
      loading.value = false
      refreshing.value = false
    }
  }
}
async function connect() {
  if (!dashboard.value || !auth.token) return
  let ticket = ''
  try {
    ticket = (await hotelApi.wsTicket()).data.ticket
  } catch {
    return
  }
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${protocol}://${location.host}/ws/hotel/${dashboard.value.hotel_id}?ticket=${encodeURIComponent(ticket)}`)
  socket.onmessage = () => { ElMessage.info('资源发生变化，经营数据已刷新'); load() }
  socket.onerror = () => socket?.close()
}

onMounted(async () => {
  restoreCachedDashboard()
  const initialLoad = load()
  if (dashboard.value) {
    await nextTick()
    scheduleCharts(loadSequence)
  }
  await initialLoad
  connect()
  window.addEventListener('resize', resizeCharts)
  await nextTick()
  if (productPoolEl.value && 'IntersectionObserver' in window) {
    productObserver = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadProducts()
    }, { rootMargin: '0px' })
    productObserver.observe(productPoolEl.value)
  }
})
onBeforeUnmount(() => { productObserver?.disconnect(); socket?.close(); revenueChart?.dispose(); listingChart?.dispose(); window.removeEventListener('resize', resizeCharts) })
</script>

<template>
  <div v-toolbar class="header-actions"><el-button plain @click="load">刷新数据</el-button><el-button type="primary" @click="$router.push('/hotel/products/generate')">✦ 生成主题产品</el-button></div>
  <el-alert v-if="showingCached && refreshing" title="正在更新经营数据，当前显示上次读取的结果" type="info" show-icon :closable="false" />
  <el-alert v-if="error && dashboard" :title="`${error}；当前显示上次读取的结果`" type="error" show-icon closable @close="error = ''" />
  <template v-if="dashboard">
    <div class="metric-grid metric-grid--sales">
      <div class="metric-link" @click="$router.push('/hotel/intents')"><MetricCard label="已确认成交额" :value="currency(dashboard.confirmed_revenue)" :hint="`${dashboard.confirmed_order_count} 单，未把暂留计入收入`" accent="#3d4d48" /></div>
      <div class="metric-link" @click="$router.push('/hotel/intents')"><MetricCard label="已确认毛利" :value="currency(dashboard.confirmed_gross_profit)" hint="只按酒店已确认的购买计算" accent="#9a7135" /></div>
      <div class="metric-link" @click="$router.push('/hotel/intents')"><MetricCard label="待确认金额" :value="currency(dashboard.held_revenue)" :hint="`${dashboard.held_order_count} 笔暂留，尚未计入成交`" accent="#7d7f89" /></div>
      <div class="metric-link" @click="$router.push('/hotel/products')"><MetricCard label="当前在售货值" :value="currency(dashboard.listed_value)" :hint="`${dashboard.available_package_count} 套仍可购买`" accent="#4c7181" /></div>
    </div>

    <section class="dashboard-charts">
      <article class="panel chart-panel"><header><div><span>已确认成交</span><h2>成交额与毛利趋势</h2></div><small>确认后才进入收入</small></header><div ref="revenueChartEl" class="dashboard-chart" /></article>
      <article class="panel chart-panel"><header><div><span>当前可售</span><h2>日期库存与在售货值</h2></div><small>按出发日期汇总</small></header><div ref="listingChartEl" class="dashboard-chart" /></article>
    </section>

    <div class="metric-grid metric-grid--operations">
      <div class="metric-link" @click="$router.push('/hotel/rooms')"><MetricCard label="临期客房" :value="dashboard.available_room_units" hint="明日待售房量 · 点击查看" accent="#0f766e" /></div>
      <div class="metric-link" @click="$router.push('/hotel/products')"><MetricCard label="在售产品" :value="dashboard.on_sale_product_count" :hint="`共 ${dashboard.product_count} 个产品 · 点击查看`" accent="#498c70" /></div>
      <div class="metric-link" @click="$router.push('/hotel/products')"><MetricCard label="暂未在售" :value="offSaleProductCount" hint="草稿、暂停或库存紧张 · 点击查看" accent="#b28350" /></div>
      <div class="metric-link" @click="$router.push('/hotel/intents')"><MetricCard label="订单" :value="dashboard.visitor_intent_count" hint="点击查看游客需求" accent="#7c6ab0" /></div>
    </div>

    <section ref="productPoolEl" class="dashboard-product-pool">
      <div class="section-title"><div class="dashboard-product-pool__heading"><h2>当前产品</h2><span>共 {{ dashboard.product_count }} 个</span></div><el-button link type="primary" @click="$router.push('/hotel/products')">查看全部</el-button></div>
      <div v-if="productLoading" class="panel empty-state">正在读取产品预览…</div>
      <div v-else-if="productError" class="panel empty-state">产品预览暂时无法读取，经营数据仍可查看。{{ productError }} <el-button plain @click="loadProducts">重试</el-button></div>
      <div v-else-if="!productLoaded" class="panel empty-state dashboard-product-pool__hint">产品摘要会在滚动到此区域时加载。</div>
      <div v-else-if="products.length" class="product-grid"><DashboardProductCard v-for="product in prioritizedProducts" :key="product.id" :product="product" /></div>
      <div v-else class="panel empty-state">还没有主题产品，先从一间临期客房开始组包。</div>
    </section>

  </template>
  <div v-else-if="loading" class="dashboard-loading" aria-busy="true" aria-label="正在读取经营数据">
    <div class="metric-grid metric-grid--sales">
      <div v-for="item in 4" :key="item" class="panel dashboard-skeleton-card">
        <i></i><b></b><span></span>
      </div>
    </div>
    <section class="dashboard-charts">
      <article v-for="item in 2" :key="item" class="panel dashboard-skeleton-chart">
        <i></i><b></b><span></span>
      </article>
    </section>
    <div class="metric-grid metric-grid--operations">
      <div v-for="item in 4" :key="item" class="panel dashboard-skeleton-card">
        <i></i><b></b><span></span>
      </div>
    </div>
    <div class="panel dashboard-skeleton-table"><i></i><span></span><span></span></div>
  </div>
  <div v-else-if="error" class="panel empty-state">
    <div>经营数据暂时无法读取</div>
    <small class="muted">{{ error }}</small>
    <el-button type="primary" @click="load">重新加载</el-button>
  </div>
</template>

<style scoped>
.dashboard-loading{display:block}.dashboard-skeleton-card,.dashboard-skeleton-chart,.dashboard-skeleton-table{background:linear-gradient(110deg,#f4f5f3 8%,#fafbf9 18%,#f4f5f3 33%);background-size:200% 100%;animation:dashboard-shimmer 1.2s linear infinite}.dashboard-skeleton-card{min-height:100px;padding:16px}.dashboard-skeleton-card i,.dashboard-skeleton-card b,.dashboard-skeleton-card span,.dashboard-skeleton-chart i,.dashboard-skeleton-chart b,.dashboard-skeleton-chart span,.dashboard-skeleton-table i,.dashboard-skeleton-table span{display:block;border-radius:5px;background:rgba(115,126,119,.12)}.dashboard-skeleton-card i{width:34%;height:12px}.dashboard-skeleton-card b{width:58%;height:24px;margin-top:14px}.dashboard-skeleton-card span{width:76%;height:10px;margin-top:10px}.dashboard-skeleton-chart{height:300px;padding:16px}.dashboard-skeleton-chart i{width:28%;height:12px}.dashboard-skeleton-chart b{width:46%;height:17px;margin-top:10px}.dashboard-skeleton-chart span{height:205px;margin-top:18px;background:repeating-linear-gradient(to bottom,rgba(115,126,119,.10) 0 1px,transparent 1px 48px)}.dashboard-skeleton-table{height:165px;padding:16px}.dashboard-skeleton-table i{width:25%;height:16px;margin-bottom:22px}.dashboard-skeleton-table span{height:24px;margin-top:10px}@keyframes dashboard-shimmer{to{background-position-x:-200%}}.header-actions{display:flex;align-items:center;gap:10px}.metric-link{cursor:pointer;transition:transform .2s}.metric-link:hover{transform:translateY(-3px)}.metric-grid--sales{margin-bottom:12px}.metric-grid--operations{margin-top:12px}.dashboard-charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:18px 0}.chart-panel{padding:14px 15px}.chart-panel header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.chart-panel header span{display:block;color:var(--muted);font-size:10px;letter-spacing:.08em}.chart-panel h2{margin:5px 0 0;font-size:15px}.chart-panel header small{margin-top:4px;color:var(--muted);font-size:10px;text-align:right}.dashboard-chart{width:100%;height:248px;min-width:0;margin-top:4px}.dashboard-product-pool{min-width:0}.dashboard-product-pool :deep(.product-grid){grid-template-columns:repeat(auto-fit,minmax(min(100%,390px),1fr))!important;align-items:stretch;gap:14px}.dashboard-product-pool :deep(.product-card){height:100%;min-width:0;grid-template-columns:140px minmax(0,1fr)!important;min-height:205px}.dashboard-product-pool :deep(.product-card__media img){width:100%;height:100%;object-fit:cover}.dashboard-charts>*{min-width:0}.dashboard-product-pool__hint{min-height:52px;padding:12px}.resource-snapshot-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.resource-snapshot{border:1px solid var(--line);border-radius:12px;background:#fff;padding:16px;text-align:left;color:var(--ink);cursor:pointer;box-shadow:var(--shadow);transition:.2s}.resource-snapshot:hover{border-color:#7bb8a8;box-shadow:0 15px 35px rgba(30,72,64,.12);transform:translateY(-2px)}.resource-snapshot p{margin:11px 0}.resource-snapshot__hint{display:block;margin-top:14px;color:var(--teal);font-size:10px;letter-spacing:.1em}.data-table td.empty-state{height:100px;text-align:center}@media(max-width:900px){.dashboard-charts,.resource-snapshot-grid{grid-template-columns:1fr}}@media(max-width:700px){.metric-grid--sales,.metric-grid--operations{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.header-actions{margin-top:12px}.page-head{display:block}.dashboard-chart{height:220px}.resource-snapshot-grid{grid-template-columns:1fr}}
.dashboard-product-pool :deep(.product-card > .product-card__media){height:100%!important;min-height:100%!important;max-height:none!important}
.dashboard-product-pool :deep(.product-card > .product-card__media > .media-image){height:100%!important;min-height:100%!important;max-height:none!important}
@media(max-width:760px){.dashboard-product-pool :deep(.product-grid){grid-template-columns:1fr!important}.dashboard-product-pool :deep(.product-card){grid-template-columns:112px minmax(0,1fr)!important;min-height:160px}}
</style>

<style scoped>
.dashboard-product-pool :deep(.product-grid) { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; align-items: stretch; gap: 12px; margin-top: 0; }
@media (max-width: 1180px) { .dashboard-product-pool :deep(.product-grid) { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; } }
@media (max-width: 700px) { .dashboard-product-pool :deep(.product-grid) { grid-template-columns: minmax(0, 1fr) !important; } }
</style>

<style scoped>
.dashboard-product-pool { margin-top: 34px; }
.dashboard-product-pool .section-title { min-height: 28px; align-items: center; margin-bottom: 18px; }
.dashboard-product-pool__heading { display: flex; min-width: 0; align-items: baseline; gap: 12px; }
.dashboard-product-pool__heading h2 { margin: 0; font-size: 18px; font-weight: 650; }
.dashboard-product-pool__heading > span { color: #737873; font-size: 13px; }
.dashboard-product-pool .section-title > :deep(.el-button) { margin-left: auto; font-size: 13px; }
.dashboard-product-pool :deep(.product-grid) { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; align-items: stretch; gap: 12px; margin-top: 0; }
@media (max-width: 1180px) { .dashboard-product-pool :deep(.product-grid) { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; } }
@media (max-width: 700px) { .dashboard-product-pool :deep(.product-grid) { grid-template-columns: minmax(0, 1fr) !important; } .dashboard-product-pool__heading { gap: 8px; } }
</style>
