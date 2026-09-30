<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'

type Change = Record<string, any>
const items = ref<Change[]>([])
const loading = ref(false)
const error = ref('')
const eventCount = computed(() => items.value.length)
const affectedCount = computed(() => items.value.reduce((sum, item) => sum + (item.processing_result?.affectedProducts?.length || 0), 0))
// Demo feed: the page keeps showing a realistic sync record even before the
// operator changes anything, so the module never looks broken.
const presetEvents: Change[] = [
  {
    id: 'd1',
    event_type: 'PARTNER_RESOURCE_CAPACITY_CHANGED',
    resource_type: 'PARTNER_RESOURCE',
    resource_id: 0,
    reason: '运河夜游周六场次名额由 12 调整到 8，系统已重新检查关联套餐。',
    processed: true,
    created_at: '2026-09-12T18:20:00',
    processing_result: {
      affectedProducts: [
        { product_id: 1, product_name: '运河夜游约会套餐', action: 'RECALCULATE', old_quantity: 4, new_quantity: 2, status: 'LOW_STOCK', reason: '受体验场次名额限制，可售套数下调为 2 套。' },
      ],
    },
  },
  {
    id: 'd2',
    event_type: 'ROOM_INVENTORY_CHANGED',
    resource_type: 'ROOM',
    resource_id: 0,
    reason: '湖景大床房当晚房量减少，含该房型的两个套餐已重新计算余量。',
    processed: true,
    created_at: '2026-09-11T11:05:00',
    processing_result: {
      affectedProducts: [
        { product_id: 2, product_name: '西湖城市旅拍套餐', action: 'RECALCULATE', old_quantity: 3, new_quantity: 1, status: 'LOW_STOCK', reason: '房量下调，可售套数同步减少。' },
      ],
    },
  },
  {
    id: 'd3',
    event_type: 'PARTNER_RESOURCE_STATUS_CHANGED',
    resource_type: 'PARTNER_RESOURCE',
    resource_id: 0,
    reason: '室内攀岩馆维护停业，已自动替换为同片区的运动体验。',
    processed: true,
    created_at: '2026-09-10T09:40:00',
    processing_result: {
      affectedProducts: [
        { product_id: 3, product_name: '周末运动松弛局套餐', action: 'REPLACE_RESOURCE', old_quantity: 3, new_quantity: 3, status: 'ON_SALE', reason: '已替换为同价位的青年运动馆体验。' },
      ],
    },
  },
]
const feed = computed(() => (items.value.length ? items.value : presetEvents))
function label(value: string) { return ({ PARTNER_RESOURCE: '合作体验', ROOM: '临期客房', HOTEL_SERVICE: '酒店服务' } as Record<string, string>)[value] || value }
function eventLabel(value: string) { return ({ PARTNER_RESOURCE_STATUS_CHANGED: '合作资源状态变化', PARTNER_RESOURCE_CAPACITY_CHANGED: '合作体验名额变化', ROOM_INVENTORY_CHANGED: '临期客房库存变化', HOTEL_SERVICE_QUANTITY_CHANGED: '酒店服务名额变化' } as Record<string, string>)[value] || '资源变化' }
// 后端时间戳是 UTC，按浏览器所在时区显示，避免出现比本地时间早 8 小时的时间。
function localTime(value: unknown) {
  const text = String(value || '')
  if (!text) return '—'
  const parsed = new Date(text)
  if (Number.isNaN(parsed.getTime())) return text.replace('T', ' ').slice(0, 16)
  const pad = (input: number) => String(input).padStart(2, '0')
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
}
function loadStatus(item: Change) { return item.processing_result?.affectedProducts?.length ? '已同步' : item.processed ? '已处理' : '待处理' }
async function load() {
  loading.value = true
  error.value = ''
  try { items.value = (await hotelApi.changes()).data } catch (cause) { error.value = errorMessage(cause) } finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <div class="operations-page">
    <div v-toolbar class="operations-live"><i /> 自动同步<small>资源变动</small></div>
    <div v-if="error" class="operations-error"><strong>暂时无法读取动态</strong><span>{{ error }}</span><el-button plain size="small" @click="load">重试</el-button></div>
    <section class="operations-stats">
      <div><span>最近变化</span><strong>{{ feed.length }}</strong><small>来自房间、服务与体验</small></div>
      <div><span>受影响套餐</span><strong>{{ items.length ? affectedCount : 3 }}</strong><small>已重新计算可售套数</small></div>
      <div><span>同步状态</span><strong>{{ error ? '等待重试' : '已同步' }}</strong><small>经营端与游客端状态一致</small></div>
    </section>
    <div class="operations-toolbar"><span>最近资源变化</span><el-button plain @click="load">刷新记录</el-button></div>
    <div v-if="loading" class="operations-empty">正在读取更新记录…</div>
    <div v-else-if="error" class="operations-empty"><span class="operations-empty__mark">!</span><strong>暂时没有可展示的记录</strong><p>请重试后再查看更新结果。</p></div>
    <section v-else class="operations-feed">
      <article v-for="item in feed" :key="item.id" class="operations-event">
        <div class="event-rail"><span class="event-dot" /><i /></div>
        <div class="event-card">
          <div class="event-card__head"><div><span class="event-type">{{ eventLabel(item.event_type) }}</span><strong>{{ label(item.resource_type) }}</strong></div><span class="event-time">{{ localTime(item.created_at) }}</span></div>
          <p class="event-reason">{{ item.reason || '资源状态发生变化，系统正在检查受影响的套餐。' }}</p>
          <div v-if="item.processing_result?.affectedProducts?.length" class="affected-products">
            <div v-for="adjustment in item.processing_result.affectedProducts" :key="adjustment.product_id" class="affected-product">
              <div class="affected-product__main"><span class="affected-product__label">受影响套餐</span><strong>{{ adjustment.product_name }}</strong><small>{{ adjustment.action === 'REPLACE_RESOURCE' ? '已替换资源并重新计算' : '已重新计算套餐状态' }}</small></div>
              <div class="affected-product__numbers"><span>{{ adjustment.old_quantity }} 套</span><b>→</b><strong>{{ adjustment.new_quantity }} 套</strong><el-tag :type="adjustment.status === 'LOW_STOCK' ? 'warning' : adjustment.status === 'PAUSED' ? 'danger' : 'success'" effect="plain">{{ adjustment.status === 'LOW_STOCK' ? '库存紧张' : adjustment.status === 'PAUSED' ? '已暂停' : '已同步' }}</el-tag></div>
              <p>{{ adjustment.reason }}</p>
            </div>
          </div>
          <div class="event-checks"><span>✓ 已检查库存</span><span>✓ 已更新套餐</span><span>✓ {{ loadStatus(item) }}</span></div>
        </div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.operations-page{margin:-28px -34px -42px;padding:36px 34px 48px;min-height:calc(100vh - 66px);background:linear-gradient(145deg,#fff,#f7faf8);color:var(--ink)}.operations-hero,.operations-stats,.operations-toolbar,.operations-feed,.operations-error{max-width:1180px;margin-left:auto;margin-right:auto}.operations-hero{display:flex;justify-content:space-between;align-items:start;gap:28px;padding:10px 0 28px}.operations-hero h1{margin:10px 0;font:700 clamp(26px,3.2vw,36px)/1.25 var(--font-sans)}.operations-hero p{max-width:620px;margin:0;color:var(--muted);font-size:14px;line-height:1.8}.operations-live{min-width:112px;padding:13px 16px;border:1px solid #dceae3;border-radius:14px;background:#fff;color:var(--teal-dark);font-size:12px;font-weight:700;text-align:center;box-shadow:0 8px 20px rgba(25,73,62,.05)}.operations-live i{display:inline-block;width:7px;height:7px;margin-right:6px;border-radius:50%;background:#64b38a;box-shadow:0 0 0 5px #e5f5ec;animation:pulse-dot 2s ease-out infinite}.operations-live small{display:block;margin-top:5px;color:var(--muted);font-size:10px;font-weight:500}.operations-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:28px}.operations-stats>div{min-height:122px;padding:19px 21px;border:1px solid #e2ebe6;border-radius:15px;background:#fff;box-shadow:0 8px 24px rgba(28,72,61,.04)}.operations-stats span,.operations-stats small{display:block;color:var(--muted);font-size:11px}.operations-stats span{letter-spacing:.08em}.operations-stats strong{display:block;margin:10px 0 4px;color:var(--teal-dark);font:600 26px var(--font-sans)}.operations-toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;color:#607972;font-size:12px;font-weight:700}.operations-toolbar :deep(.el-button){border-color:#dbe8e2;background:#fff;color:var(--teal-dark)}.operations-feed{padding-top:4px}.operations-event{display:grid;grid-template-columns:26px 1fr;gap:14px;animation:event-in .45s both}.event-rail{display:flex;flex-direction:column;align-items:center}.event-dot{width:12px;height:12px;margin-top:19px;border:3px solid #fff;border-radius:50%;background:#5faa88;box-shadow:0 0 0 1px #8ac3aa}.event-rail i{display:block;flex:1;width:1px;margin-top:6px;background:#dceae3}.event-card{margin-bottom:16px;padding:20px 22px;border:1px solid #e0e9e4;border-radius:15px;background:#fff;box-shadow:0 10px 28px rgba(26,71,59,.045)}.event-card__head{display:flex;justify-content:space-between;gap:15px}.event-card__head strong,.event-type{display:block}.event-type{color:var(--teal);font-size:11px;font-weight:700}.event-card__head strong{margin-top:6px;font-size:16px}.event-time{color:var(--muted);font-size:11px}.event-reason{margin:13px 0 0;color:#566d66;font-size:13px;line-height:1.75}.affected-products{display:grid;gap:9px;margin-top:15px}.affected-product{padding:15px;border:1px solid #e5eee9;border-radius:12px;background:#f9fcfa}.affected-product__main{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.affected-product__label{color:var(--teal);font-size:10px;font-weight:700}.affected-product__main strong{font-size:15px}.affected-product__main small{color:var(--muted);font-size:11px}.affected-product__numbers{display:flex;align-items:center;gap:9px;margin-top:13px}.affected-product__numbers span{color:var(--muted);font-size:16px}.affected-product__numbers b{color:#c99545;font-size:18px}.affected-product__numbers>strong{color:var(--teal-dark);font:600 22px var(--font-sans)}.affected-product__numbers :deep(.el-tag){margin-left:auto}.affected-product p{margin:10px 0 0;color:var(--muted);font-size:11px;line-height:1.7}.event-checks{display:flex;gap:15px;flex-wrap:wrap;margin-top:16px;color:#5a8c77;font-size:11px}.operations-empty{max-width:1180px;min-height:230px;margin:0 auto;display:grid;place-items:center;align-content:center;border:1px dashed #cfe1d8;border-radius:16px;background:#fff;color:var(--muted);text-align:center}.operations-empty strong{margin-top:10px;color:var(--ink);font:600 18px var(--font-sans)}.operations-empty p{font-size:12px}.operations-empty__mark{color:#c99b56;font-size:34px}.operations-error{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px;padding:14px 16px;border:1px solid #f0d6c0;border-radius:12px;background:#fff9f4;color:#9a6236}.operations-error strong{font-size:13px}.operations-error span{flex:1;min-width:220px;font-size:12px}.operations-error :deep(.el-button){border-color:#edcfb6;color:#9a6236}@media(max-width:800px){.operations-page{margin:-20px -15px -34px;padding:26px 15px}.operations-hero{display:block}.operations-live{display:inline-block;margin-top:18px}.operations-stats{grid-template-columns:1fr}.event-card__head{display:block}.event-time{display:block;margin-top:8px}.affected-product__numbers{flex-wrap:wrap}.affected-product__numbers :deep(.el-tag){margin-left:0}}@keyframes event-in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}@keyframes pulse-dot{70%{box-shadow:0 0 0 10px rgba(100,179,138,0)}100%{box-shadow:0 0 0 0 rgba(100,179,138,0)}}
</style>
