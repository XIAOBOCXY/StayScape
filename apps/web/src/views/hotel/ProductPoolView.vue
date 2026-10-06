<script setup lang="ts">
import MediaImage from '../../components/MediaImage.vue'
import { heroMedia, mediaForResource } from '../../utils/productMedia'
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import DateHeatmap from '../../components/DateHeatmap.vue'
import type { TravelProduct } from '../../types'

const calendarOpen = ref(false);
const calendarLabel = computed(() => selectedDate.value ? `出发日期 ${selectedDate.value}` : '全部出发日期');
function chooseDate(value: string) { selectedDate.value = value; calendarOpen.value = false }
const router = useRouter(); const items = ref<TravelProduct[]>([]); const loading = ref(false); const loadingMore = ref(false); const status = ref(''); const selectedDate = ref(''); const viewMode = ref<'cards' | 'list'>('cards'); const preview = ref<TravelProduct | null>(null); const previewVisible = ref(false); const previewLoading = ref(false); const marketingLoading = ref(false); const totalItems = ref(0); const calendarItems = ref<Array<{ target_date: string; sale_quantity: number }>>([]); const pageSize = 24; const fullProductIds = new Set<number>(); let loadSequence = 0
const visibleItems = computed(() => items.value)
const hasMore = computed(() => items.value.length < totalItems.value)
async function load(reset = true) {
  if (!reset && (loading.value || loadingMore.value || !hasMore.value)) return
  const requestId = ++loadSequence
  const offset = reset ? 0 : items.value.length
  if (reset) loading.value = true
  else loadingMore.value = true
  try {
    const response = await hotelApi.products(status.value || undefined, pageSize, false, offset, selectedDate.value || undefined)
    if (requestId !== loadSequence) return
    items.value = reset ? response.data.items : [...items.value, ...response.data.items]
    totalItems.value = Number(response.data.total || 0)
    if (response.data.dates?.length) calendarItems.value = response.data.dates
  } catch (e) {
    if (requestId === loadSequence) ElMessage.error(errorMessage(e))
  } finally {
    if (requestId === loadSequence) { loading.value = false; loadingMore.value = false }
  }
}
function reload() { items.value = []; totalItems.value = 0; void load(true) }
function loadMore() { void load(false) }
watch(selectedDate, () => reload())
async function remove(row: TravelProduct) { try { await ElMessageBox.confirm(`确定删除“${row.product_name}”吗？已有订单的产品会安全归档。`, '删除产品', { type: 'warning' }); const response = await hotelApi.deleteProduct(row.id); ElMessage.success(response.data.message); await load() } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(errorMessage(e)) } }
async function openPreview(row: TravelProduct) {
  preview.value = row
  previewVisible.value = true
  if (fullProductIds.has(row.id)) return
  previewLoading.value = true
  try {
    const response = await hotelApi.product(row.id)
    if (preview.value?.id === row.id) preview.value = response.data
    fullProductIds.add(row.id)
  } catch (e) { ElMessage.error(errorMessage(e)) }
  finally { if (preview.value?.id === row.id) previewLoading.value = false }
}
async function regenerate(row: TravelProduct) { marketingLoading.value = true; try { const updated = (await hotelApi.regenerateMarketing(row.id, { style: 'SEEDING', generate_image: false })).data; fullProductIds.add(row.id); const index = items.value.findIndex(item => item.id === row.id); if (index >= 0) items.value[index] = updated; preview.value = updated; ElMessage.success('已更新产品宣传文案') } catch (e) { ElMessage.error(errorMessage(e)) } finally { marketingLoading.value = false } }
// 卡片主图与游客端一致：优先产品最主要的在地体验实拍图，其次是客房图
function poolMedia(row: any) {
  const focus = row.resources?.find((item: any) => item.resource_type === 'PARTNER_RESOURCE') || row.resources?.[0]
  return focus ? mediaForResource(row, focus) : heroMedia(row)
}

onMounted(() => { void load() })
</script>

<template>
  <div v-toolbar class="header-actions"><el-radio-group v-model="viewMode" class="view-mode-switch" size="small" aria-label="产品展示方式"><el-radio-button label="cards">卡片</el-radio-button><el-radio-button label="list">列表</el-radio-button></el-radio-group><el-button plain @click="load(true)">刷新</el-button><el-button type="primary" @click="router.push('/hotel/products/generate')">＋ 生成新方案</el-button></div>
  <div class="panel filter-bar"><div><el-radio-group v-model="status" @change="reload"><el-radio-button label="">全部</el-radio-button><el-radio-button label="DRAFT">草稿</el-radio-button><el-radio-button label="ON_SALE">在售</el-radio-button><el-radio-button label="LOW_STOCK">库存紧张</el-radio-button><el-radio-button label="PAUSED">已暂停</el-radio-button></el-radio-group><el-popover v-model:visible="calendarOpen" placement="bottom-start" trigger="click" :width="370" popper-class="product-date-popover"><template #reference><el-button plain class="calendar-trigger">{{ calendarLabel }} <span aria-hidden="true">▾</span></el-button></template><DateHeatmap :model-value="selectedDate" :items="calendarItems" date-key="target_date" quantity-key="sale_quantity" label="出发日期" @update:model-value="chooseDate" /></el-popover><span class="product-pool-count">{{ items.length }} / {{ totalItems }} 个产品</span></div></div>
  <div v-if="loading && !items.length" class="product-pool-loading">正在读取产品列表…</div>
   <div v-if="viewMode === 'cards'" v-loading="loading && items.length > 0" class="product-pool-grid"><article v-for="row in visibleItems" :key="row.id" class="pool-card panel"><div class="pool-card__visual" @click="openPreview(row)"><MediaImage :media="poolMedia(row)" aspect="card" /><StatusTag class="pool-card__status" :status="row.status" /><span class="pool-card__date">{{ row.target_date }}</span></div><div class="pool-card__body"><h2>{{ row.product_name }}</h2><div class="pool-card__theme">{{ row.theme }}</div><div class="product-card__resources"><span v-for="resource in row.resources.slice(0, 3)" :key="resource.id">{{ resource.resource_name }}</span></div><div class="pool-card__metrics"><div><small>可售</small><strong>{{ row.sale_quantity }} 套</strong></div><div><small>售价</small><strong>¥{{ row.suggested_price }}</strong></div><div><small>毛利率</small><strong>{{ (Number(row.gross_margin) * 100).toFixed(1) }}%</strong></div></div><div class="pool-card__actions"><el-button plain @click="openPreview(row)">素材预览</el-button><el-button type="primary" @click="router.push(`/hotel/products/${row.id}`)">打开方案</el-button><el-button link type="danger" @click="remove(row)">删除</el-button></div></div></article></div>
  <div v-else class="panel table-wrap"><el-table v-loading="loading" :data="visibleItems" style="width:100%" @row-click="openPreview"><el-table-column prop="product_name" label="产品" min-width="250"><template #default="{row}"><strong>{{ row.product_name }}</strong><div class="muted">{{ row.theme }} · {{ row.target_date }}</div></template></el-table-column><el-table-column label="状态" width="105"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column><el-table-column label="可售" width="85"><template #default="{row}">{{ row.sale_quantity }} 套</template></el-table-column><el-table-column label="售价" width="100"><template #default="{row}">¥{{ row.suggested_price }}</template></el-table-column><el-table-column label="主图" width="120"><template #default="{row}"><span class="success-text">产品实拍图</span></template></el-table-column><el-table-column label="操作" width="150"><template #default="{row}"><el-button link type="primary" @click.stop="openPreview(row)">预览</el-button><el-button link type="primary" @click.stop="router.push(`/hotel/products/${row.id}`)">编辑</el-button><el-button link type="danger" @click.stop="remove(row)">删除</el-button></template></el-table-column></el-table></div>
  <div v-if="items.length && hasMore" class="load-more-row"><el-button plain :loading="loadingMore" @click="loadMore">加载更多（{{ items.length }} / {{ totalItems }}）</el-button></div>
  <div v-if="!loading && !visibleItems.length" class="panel empty-state">这一天暂无产品；可切换日期，或生成一组新方案。</div>

  <el-dialog v-if="preview" v-model="previewVisible" title="产品文案" width="980px" top="4vh"><div class="marketing-workbench" v-loading="previewLoading"><div class="workbench-product-image"><MediaImage :media="poolMedia(preview)" aspect="card" /><div class="product-caption">{{ preview.product_name }} · {{ preview.target_date }} · {{ preview.weather }}</div></div><div class="workbench-copy"><div class="workbench-title"><div><div class="eyebrow">宣传内容</div><h2>{{ preview.marketing_title }}</h2></div><div class="workbench-title__actions"><el-button type="primary" plain :loading="marketingLoading" @click="regenerate(preview)">重新生成文案</el-button></div></div><div v-for="asset in preview.marketing_assets.filter(item => item.asset_type !== 'POSTER')" :key="asset.asset_type" class="copy-card"><div class="product-card__top"><strong>{{ asset.title }}</strong><el-tag size="small" effect="plain">{{ asset.platform }}</el-tag></div><p>{{ asset.content }}</p><small>{{ asset.visual_brief }}</small><b>{{ asset.call_to_action }}</b></div></div></div><template #footer><el-button @click="router.push(`/hotel/products/${preview.id}`)">进入产品详情</el-button><el-button type="primary" @click="previewVisible = false">关闭</el-button></template></el-dialog>
</template>

<style scoped>
.filter-bar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:16px;padding:12px 14px}
.filter-bar>div{display:flex;align-items:center;flex-wrap:wrap;gap:10px 14px;min-width:0;width:100%}
.filter-bar :deep(.el-radio-group){display:flex;flex-wrap:wrap;gap:6px}
.filter-bar :deep(.el-radio-button__inner){border-left:1px solid var(--line);border-radius:999px!important;box-shadow:none!important}
.filter-bar .calendar-trigger{height:33px;margin-left:4px;white-space:nowrap}.filter-bar .calendar-trigger span{margin-left:8px;color:var(--muted)}
.product-pool-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));align-items:stretch;gap:16px}
.pool-card{display:flex;min-width:0;flex-direction:column;overflow:hidden;padding:0}
.pool-card__visual{position:relative;aspect-ratio:2/1;min-height:145px;max-height:190px;overflow:hidden;background:#e8efeb;cursor:pointer}
.pool-card__visual :deep(.media-image){width:100%;height:100%;aspect-ratio:auto;border-radius:0}
.pool-card__visual :deep(.media-image img){display:block;width:100%;height:100%;object-fit:cover}
.pool-card__visual :deep(.media-fallback){width:100%;height:100%}
.pool-card__status{position:absolute;top:12px;right:12px;z-index:2}
.pool-card__date{position:absolute;left:12px;top:12px;padding:6px 10px;border-radius:999px;background:rgba(24,43,37,.82);color:#fff;font-size:12px;line-height:1.2}
.visual-hint{position:absolute;right:12px;bottom:12px;padding:6px 10px;border-radius:999px;background:rgba(24,43,37,.82);color:#fff;font-size:11px}
.pool-card__body{display:flex;min-width:0;flex:1;flex-direction:column;padding:16px 18px}
.product-card__top{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:24px}
.pool-card__body .eyebrow{color:var(--muted);font-size:12px;line-height:1.4}
.pool-card__body h2{display:-webkit-box;min-height:42px;margin:8px 0 5px;overflow:hidden;font-size:18px;line-height:1.35;font-weight:700;letter-spacing:-.01em;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.pool-card__copy{display:-webkit-box;min-height:40px;margin:0;overflow:hidden;color:var(--muted);font-size:13px;line-height:1.6;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.pool-card .product-card__resources{display:flex;flex-wrap:wrap;gap:6px;max-height:48px;margin:0;overflow:hidden}
.pool-card .product-card__resources span{padding:4px 9px;border:1px solid var(--line);border-radius:999px;background:var(--panel-soft);color:var(--ink);font-size:11.5px;line-height:1.4}
.pool-card__metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0}
.pool-card__metrics div{display:flex;min-width:0;min-height:52px;flex-direction:column;justify-content:center;gap:4px;padding:7px 9px;border:1px solid #eef1ee;border-radius:9px;background:#f8faf9}
.pool-card__metrics small{color:var(--muted);font-size:11.5px;line-height:1.25}
.pool-card__metrics strong{overflow:hidden;color:var(--teal-dark);font-size:16px;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}
.pool-card__actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:auto;padding-top:12px;border-top:1px solid #edf0ed}
.product-pool-count{margin-left:auto;color:var(--muted);font-size:12px;white-space:nowrap}.product-pool-loading{padding:34px;text-align:center;color:var(--muted);font-size:12px}.load-more-row{display:flex;justify-content:center;margin:18px 0 28px}
.pool-card__actions :deep(.el-button){min-height:34px;padding:7px 11px;font-size:12px}
.pool-card{transition:transform .18s ease,box-shadow .18s ease}
.pool-card:hover{transform:translateY(-2px);box-shadow:0 12px 30px rgba(27,53,44,.10)}
.marketing-workbench{display:grid;grid-template-columns:minmax(280px,.8fr) minmax(0,1.2fr);gap:20px}
.workbench-product-image{position:sticky;top:0;align-self:start;overflow:hidden;border-radius:16px;background:#e7f1ed}
.workbench-product-image :deep(.media-image){width:100%;aspect-ratio:1.42/1;border-radius:0}
.workbench-product-image :deep(.media-image img){display:block;width:100%;height:auto;max-height:58vh;object-fit:contain;background:#eef4f1}
.product-caption{padding:10px 12px;background:#174d46;color:#e4f4ee;font-size:12px}
.workbench-copy{min-width:0;max-height:66vh;overflow:auto;padding-right:4px}
.workbench-title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px}
.workbench-title h2{margin:7px 0 0;font-size:21px}
.workbench-title__actions{display:flex;flex:0 0 auto;gap:8px}
.copy-card{margin-top:10px;padding:12px 0;border:0;border-bottom:1px solid var(--line);border-radius:0;background:transparent}
.copy-card p{margin:10px 0;font-size:13px;line-height:1.75;white-space:pre-wrap}
.copy-card small{display:block;color:var(--muted);line-height:1.6}
.copy-card b{display:block;margin-top:8px;color:var(--teal);font-size:12px}
@media(max-width:900px){.product-pool-grid{grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:12px}.marketing-workbench{grid-template-columns:1fr}.workbench-product-image{position:static}.workbench-copy{max-height:none}}
@media(max-width:700px){.filter-bar{padding:10px}.filter-bar>div{align-items:center}.product-pool-count{margin-left:0}.product-pool-grid{grid-template-columns:1fr}.pool-card__visual{aspect-ratio:1.8/1;min-height:160px}.pool-card__body{padding:16px;gap:10px}.pool-card__body h2{min-height:44px;font-size:17px}.pool-card__metrics{gap:6px;margin:11px 0 9px}.pool-card__metrics div{min-height:52px;padding:7px}.pool-card__metrics strong{font-size:15px}.pool-card__actions{gap:6px}.workbench-title{flex-direction:column}.workbench-title__actions{flex-wrap:wrap}}
@media(max-width:420px){.pool-card__body{padding:12px}.pool-card__metrics small{font-size:11px}.pool-card__metrics strong{font-size:15px}.pool-card__actions :deep(.el-button){padding:5px 8px;font-size:11.5px}}
.header-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;margin:0 0 14px}.header-actions :deep(.el-button){height:32px;min-height:32px;padding:0 12px;font-size:12px;border-radius:8px}.header-actions :deep(.el-radio-button__inner){display:inline-flex;align-items:center;height:32px;padding:0 12px}.filter-bar{padding:13px 15px;background:#fff;border:1px solid #e9eeea;box-shadow:none}.filter-bar :deep(.el-radio-button__inner){min-height:32px;padding:8px 12px;border-color:#e5ebe7;background:#fff;color:#55645b}.filter-bar :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner){background:#eaf3ed;border-color:#bdd1c4;color:#315b46;box-shadow:none}.pool-card{border:1px solid #e8ede9!important;border-radius:13px!important;background:#fff!important;box-shadow:none!important}.pool-card__body{gap:9px;padding:14px 16px 15px}.pool-card__body h2{min-height:0;margin:1px 0 0;font-size:17px;line-height:1.4}.pool-card__theme{color:#728078;font-size:12px;line-height:1.5}.pool-card .product-card__resources span{padding:3px 8px;border:0;background:#f2f6f3;color:#52675a}.pool-card__metrics{gap:0;margin-top:3px;padding:8px 0;border-block:1px solid #edf0ed;background:transparent}.pool-card__metrics div{min-height:42px;padding:5px 9px;border:0;border-right:1px solid #edf0ed;border-radius:0;background:transparent}.pool-card__metrics div:last-child{border-right:0}.pool-card__metrics strong{font-size:15px;color:#304d3e}.pool-card__actions{gap:6px;padding-top:6px;border-top:0}.pool-card__actions :deep(.el-button){height:32px;min-height:32px;border-radius:7px}.pool-card:hover{transform:translateY(-1px);box-shadow:0 8px 20px rgba(27,53,44,.07)!important}@media(max-width:700px){.header-actions{justify-content:space-between}.filter-bar{margin-bottom:12px}.pool-card__body{padding:13px}.pool-card__actions{justify-content:flex-start}}
</style>
