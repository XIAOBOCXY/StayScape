<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'

type OrderRecord = {
  id: number
  product_id: number
  product_name: string
  category: string
  amount: string | null
  amount_is_estimate: boolean
  target_date: string
  created_at: string
  confirmed_at?: string | null
  status: string
  product_status?: string
  contact_name: string
}

const router = useRouter()
const loading = ref(false)
const drawerVisible = ref(false)
const selected = ref<OrderRecord | null>(null)
const summary = ref({ total: 0, confirmed: 0, confirmed_revenue: '0', sold_product_count: 0, estimated_amount_count: 0, orders: [] as OrderRecord[] })
const items = computed(() => summary.value.orders)

async function load() {
  loading.value = true
  try { summary.value = (await hotelApi.ordersOverview()).data as typeof summary.value }
  catch (error) { ElMessage.error(errorMessage(error)) }
  finally { loading.value = false }
}

function open(item: OrderRecord) { selected.value = item; drawerVisible.value = true }
function viewProduct(id: number) { drawerVisible.value = false; router.push(`/hotel/products/${id}`) }
function money(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  const amount = Number(value)
  return Number.isFinite(amount) ? `¥${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'
}
function orderTime(value?: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? String(value).replace('T', ' ').slice(0, 16) : parsed.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}
function statusText(status: string) {
  return ({ 已成交: '已成交', CONFIRMED: '已成交', 预约中: '预约中', HELD: '预约中', 已取消: '已取消', CANCELLED: '已取消', RELEASED: '已取消' } as Record<string, string>)[status] || status || '—'
}
function statusType(status: string) {
  const text = statusText(status)
  return text === '已成交' ? 'success' : text === '已取消' ? 'info' : 'warning'
}
function abnormalMessage(item: OrderRecord) {
  const status = String(item.product_status || '').toUpperCase()
  if (['OFF_SHELF', 'PAUSED', 'DRAFT'].includes(status)) return '关联产品当前已下架或暂停销售；这笔订单仍作为历史销售记录保留。'
  if (status === 'SOLD_OUT') return '关联产品当前已售罄；这笔订单仍作为历史销售记录保留。'
  return ''
}

onMounted(load)
</script>

<template>
  <div class="orders-page">
    <div v-toolbar class="header-actions"><el-button plain :loading="loading" @click="load">刷新</el-button></div>

    <div class="order-summary">
      <article><span>订单总数</span><strong>{{ summary.total }}</strong><small>其中已成交 {{ summary.confirmed }} 单</small></article>
      <article><span>确认订单金额</span><strong>{{ money(summary.confirmed_revenue) }}</strong><small>以已成交订单统计</small></article>
      <article><span>已售产品数</span><strong>{{ summary.sold_product_count }}</strong><small>至少产生一笔确认订单</small></article>
    </div>

    <section class="panel order-list">
      <div class="order-list__head"><h2>销售订单</h2><span>按下单时间倒序</span></div>
      <el-table v-loading="loading" :data="items" row-key="id" size="default">
        <el-table-column label="产品" min-width="270">
          <template #default="{ row }">
            <button class="product-link" type="button" @click="viewProduct(row.product_id)">{{ row.product_name }}<span>查看产品详情 ↗</span></button>
          </template>
        </el-table-column>
        <el-table-column label="游客" prop="contact_name" min-width="110" />
        <el-table-column label="下单时间" min-width="170"><template #default="{ row }">{{ orderTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="金额" min-width="145">
          <template #default="{ row }"><div class="order-amount">{{ money(row.amount) }}<small v-if="row.amount_is_estimate">估算</small></div></template>
        </el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)" effect="light">{{ statusText(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="" width="86" align="right"><template #default="{ row }"><el-button link type="primary" @click="open(row)">订单详情</el-button></template></el-table-column>
        <template #empty><div class="empty-orders">暂无游客订单。订单产生后，销售结果会显示在这里。</div></template>
      </el-table>
      <p v-if="summary.estimated_amount_count" class="amount-note">{{ summary.estimated_amount_count }} 笔历史订单没有提交时的价格快照，金额按当前产品售价估算并已标记。</p>
    </section>

    <el-drawer v-model="drawerVisible" title="订单详情" size="440px">
      <div v-if="selected" class="order-detail">
        <dl>
          <div><dt>购买产品</dt><dd><button type="button" class="product-link" @click="viewProduct(selected.product_id)">{{ selected.product_name }}<span>打开产品详情 ↗</span></button></dd></div>
          <div><dt>游客</dt><dd>{{ selected.contact_name || '—' }}</dd></div>
          <div><dt>下单时间</dt><dd>{{ orderTime(selected.created_at) }}</dd></div>
          <div><dt>出行日期</dt><dd>{{ selected.target_date || '—' }}</dd></div>
          <div><dt>订单金额</dt><dd>{{ money(selected.amount) }}<small v-if="selected.amount_is_estimate"> · 历史售价估算</small></dd></div>
          <div><dt>订单状态</dt><dd><el-tag :type="statusType(selected.status)" effect="light">{{ statusText(selected.status) }}</el-tag></dd></div>
        </dl>
        <div v-if="abnormalMessage(selected)" class="order-alert"><b>产品状态提示</b><p>{{ abnormalMessage(selected) }}</p><el-button link type="primary" @click="viewProduct(selected.product_id)">查看产品详情</el-button></div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.orders-page{min-width:0}.header-actions{display:flex;justify-content:flex-end;gap:8px}.order-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 14px}.order-summary article{display:grid;gap:6px;padding:15px 17px;border:1px solid var(--line);border-radius:10px;background:var(--paper)}.order-summary span{color:var(--muted);font-size:11px}.order-summary strong{font-size:23px;line-height:1.15;font-variant-numeric:tabular-nums}.order-summary small,.order-list__head span,.amount-note{color:var(--muted);font-size:10.5px}.order-list{padding:14px 16px 12px}.order-list__head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.order-list__head h2{margin:0;font-size:14px}.product-link{display:inline-grid;gap:3px;padding:0;border:0;background:none;color:#2e6355;text-align:left;font-size:12px;font-weight:650;cursor:pointer}.product-link:hover{text-decoration:underline}.product-link span{color:var(--muted);font-size:10px;font-weight:400;text-decoration:none}.order-amount{font-variant-numeric:tabular-nums}.order-amount small{display:block;color:#9a7135;font-size:9.5px}.empty-orders{padding:32px 8px;color:var(--muted);font-size:12px}.amount-note{margin:9px 0 0}.order-detail dl{display:grid;gap:0;margin:0}.order-detail dl>div{display:grid;grid-template-columns:95px 1fr;gap:10px;align-items:center;padding:14px 0;border-bottom:1px solid var(--line)}.order-detail dt{color:var(--muted);font-size:11px}.order-detail dd{margin:0;font-size:12px}.order-detail dd small{color:var(--muted);font-size:10px}.order-alert{margin-top:18px;padding:13px;border:1px solid #f0d8aa;border-radius:9px;background:#fff9ed}.order-alert b{font-size:12px;color:#8b5c1e}.order-alert p{margin:6px 0;color:#68563b;font-size:11px;line-height:1.6}@media(max-width:800px){.order-summary{grid-template-columns:1fr}.header-actions{margin-left:auto}.order-list{padding:12px 8px}.order-list__head{padding:0 8px}}
</style>
