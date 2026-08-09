<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { Adjustment, MarketingAsset, TravelProduct } from '../../types'

const route = useRoute(); const router = useRouter()
const product = ref<TravelProduct | null>(null); const adjustments = ref<Adjustment[]>([]); const loading = ref(true); const editDialog = ref(false); const saving = ref(false); const marketingLoading = ref(false)
const activeAssetType = ref<MarketingAsset['asset_type']>('POSTER')
const form = reactive({ target_date: '', weather: 'RAIN', target_crowd: 'FAMILY', theme: '', product_name: '', marketing_title: '', marketing_content: '', regenerate_marketing: true })
const activeAsset = computed(() => product.value?.marketing_assets?.find((asset) => asset.asset_type === activeAssetType.value) || product.value?.marketing_assets?.[0])

function fillForm(value: TravelProduct) { Object.assign(form, { target_date: value.target_date, weather: value.weather, target_crowd: value.target_crowd, theme: value.theme, product_name: value.product_name, marketing_title: value.marketing_title, marketing_content: value.marketing_content, regenerate_marketing: true }) }
async function load() {
  loading.value = true
  try { const response = await hotelApi.product(Number(route.params.id)); product.value = response.data; adjustments.value = (response.data as TravelProduct & { adjustments?: Adjustment[] }).adjustments || []; fillForm(response.data) }
  catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false }
}
async function setStatus(status: string) { if (!product.value) return; try { product.value = (await hotelApi.productStatus(product.value.id, status)).data; ElMessage.success('产品状态已更新') } catch (e) { ElMessage.error(errorMessage(e)) } }
async function saveEdit() {
  if (!product.value) return
  saving.value = true
  try { const updated = (await hotelApi.updateProduct(product.value.id, { ...form })).data; product.value = updated; fillForm(updated); editDialog.value = false; ElMessage.success('产品内容已保存，库存与财务已重新校验'); await load() }
  catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false }
}
async function regenerateMarketing() {
  if (!product.value) return
  marketingLoading.value = true
  try { product.value = (await hotelApi.regenerateMarketing(product.value.id)).data; ElMessage.success('已生成图文海报、社媒文案和短视频脚本') }
  catch (e) { ElMessage.error(errorMessage(e)) } finally { marketingLoading.value = false }
}
function downloadPoster(asset: MarketingAsset) {
  if (!asset.poster_svg) return
  const url = URL.createObjectURL(new Blob([asset.poster_svg], { type: 'image/svg+xml;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = `${asset.title || 'stayscape-poster'}.svg`; link.click(); URL.revokeObjectURL(url)
}
async function removeProduct() {
  if (!product.value) return
  try {
    await ElMessageBox.confirm('删除后产品将从酒店产品池移除，已有预约意向的产品会被安全归档。确定继续吗？', '删除产品', { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' })
    const response = await hotelApi.deleteProduct(product.value.id)
    ElMessage.success(response.data.message)
    router.push('/hotel/dashboard')
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error(errorMessage(e)) }
}
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div v-if="product">
      <div class="page-head">
        <div><div class="eyebrow">PRODUCT DETAIL · {{ product.product_code }}</div><h1>{{ product.product_name }}</h1><p>{{ product.target_date }} · {{ product.theme }} · {{ product.target_crowd }} · {{ product.weather }}</p></div>
        <div class="header-actions"><StatusTag :status="product.status" /><el-button plain @click="editDialog=true">编辑产品</el-button><el-button v-if="product.status === 'DRAFT'" type="primary" @click="setStatus('ON_SALE')">模拟发布</el-button><el-button v-if="['ON_SALE','LOW_STOCK'].includes(product.status)" plain @click="setStatus('PAUSED')">暂停销售</el-button><el-button type="danger" plain @click="removeProduct">删除</el-button></div>
      </div>
      <div class="metric-grid"><div class="metric-card"><div class="metric-label">可售数量</div><div class="metric-value">{{ product.sale_quantity }} 套</div><div class="metric-hint">瓶颈：{{ product.bottleneck_resource }}</div></div><div class="metric-card"><div class="metric-label">单套成本</div><div class="metric-value">¥{{ product.unit_cost }}</div><div class="metric-hint">房间、服务、合作资源合计</div></div><div class="metric-card"><div class="metric-label">建议售价</div><div class="metric-value">¥{{ product.suggested_price }}</div><div class="metric-hint">最低允许 ¥{{ product.minimum_allowed_price }}</div></div><div class="metric-card"><div class="metric-label">单套毛利</div><div class="metric-value">¥{{ product.gross_profit }}</div><div class="metric-hint">毛利率 {{ (Number(product.gross_margin) * 100).toFixed(2) }}%</div></div></div>

      <div class="detail-grid">
        <div>
          <div class="panel"><div class="section-title" style="margin-top:0"><h2>资源组成与时间</h2><span>确定性校验后的最终组合</span></div><table class="data-table"><thead><tr><th>资源</th><th>日期</th><th>场次</th><th>每套消耗</th><th>单位成本</th></tr></thead><tbody><tr v-for="item in product.resources" :key="item.id"><td><strong>{{ item.resource_name }}</strong><div class="muted">{{ item.resource_type }}<span v-if="item.address"> · {{ item.address }}</span></div></td><td>{{ item.available_date || product.target_date }}</td><td>{{ item.start_time?.slice(0,5) || '--' }} - {{ item.end_time?.slice(0,5) || '--' }}</td><td>{{ item.quantity_per_package }}</td><td>¥{{ item.unit_cost }}</td></tr></tbody></table></div>
          <div class="panel marketing-panel marketing-studio" style="margin-top:18px"><div class="section-title" style="margin-top:0"><div><div class="eyebrow">MARKETING STUDIO</div><h2>把产品变成可发布的内容</h2><span>游客端会直接使用这里的海报、旅行灵感和卖点。</span></div><div class="marketing-panel-actions"><el-button plain @click="router.push(`/visitor/products/${product.id}`)">预览游客端</el-button><el-button type="primary" plain :loading="marketingLoading" @click="regenerateMarketing">重新生成素材</el-button></div></div><h3>{{ product.marketing_title }}</h3><p class="muted marketing-copy">{{ product.marketing_content }}</p><div v-if="product.marketing_assets?.length" class="marketing-tabs"><button v-for="asset in product.marketing_assets" :key="asset.asset_type" :class="{active: activeAsset?.asset_type === asset.asset_type}" @click="activeAssetType = asset.asset_type">{{ asset.asset_type === 'POSTER' ? '海报' : asset.asset_type === 'SOCIAL_POST' ? '社媒种草' : asset.asset_type === 'SHORT_VIDEO_SCRIPT' ? '短视频脚本' : '门店卖点' }}</button></div><div v-if="activeAsset" class="marketing-focus"><div class="marketing-focus__visual"><div v-if="activeAsset.poster_svg" class="marketing-poster" v-html="activeAsset.poster_svg" /><div v-else class="marketing-focus__text"><div class="eyebrow">{{ activeAsset.platform }}</div><h3>{{ activeAsset.title }}</h3><p>{{ activeAsset.content }}</p></div><el-button v-if="activeAsset.poster_svg" size="small" plain @click="downloadPoster(activeAsset)">下载 SVG 海报</el-button></div><div class="marketing-focus__meta"><span>{{ activeAsset.platform }}</span><p>{{ activeAsset.content }}</p><small>视觉方向：{{ activeAsset.visual_brief }}</small><strong>{{ activeAsset.call_to_action }}</strong></div></div><div v-if="!product.marketing_assets?.length" class="empty-state">暂无营销素材，点击重新生成。</div><p class="danger-text" style="line-height:1.7">{{ product.risk_message }}</p></div>
        </div>
        <div>
          <div class="panel"><div class="section-title" style="margin-top:0"><h2>动态调整</h2><span>{{ adjustments.length }} 条</span></div><div v-if="!adjustments.length" class="empty-state">资源变化会出现在这里</div><div v-for="item in adjustments" :key="item.id" style="padding:13px 0;border-top:1px solid var(--line)"><div style="display:flex;justify-content:space-between"><strong>{{ item.old_quantity }} → {{ item.new_quantity }} 套</strong><span class="muted">{{ item.action }}</span></div><p class="muted" style="line-height:1.6">{{ item.reason }}</p></div></div>
          <div class="panel" style="margin-top:18px"><div class="section-title" style="margin-top:0"><h2>推荐说明</h2></div><p class="muted" style="line-height:1.8">{{ product.recommendation_reason }}</p><p class="danger-text" style="line-height:1.7">{{ product.risk_message }}</p></div>
        </div>
      </div>
    </div>
    <div v-else-if="!loading" class="panel empty-state">产品不存在或已被删除</div>
  </div>

  <el-dialog v-model="editDialog" title="编辑产品内容与时间" width="680px">
    <el-form label-position="top"><div class="form-grid"><el-form-item label="产品名称" class="full"><el-input v-model="form.product_name" /></el-form-item><el-form-item label="入住日期"><el-date-picker v-model="form.target_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="天气场景"><el-select v-model="form.weather" style="width:100%"><el-option label="小雨 / 室内友好" value="RAIN" /><el-option label="晴天 / 城市漫游" value="SUNNY" /><el-option label="多云 / 轻户外" value="CLOUDY" /></el-select></el-form-item><el-form-item label="目标客群"><el-select v-model="form.target_crowd" style="width:100%"><el-option label="亲子家庭" value="FAMILY" /><el-option label="情侣" value="COUPLE" /><el-option label="本地周末客" value="LOCAL" /></el-select></el-form-item><el-form-item label="主题方向"><el-input v-model="form.theme" /></el-form-item><el-form-item label="营销标题" class="full"><el-input v-model="form.marketing_title" /></el-form-item><el-form-item label="营销内容" class="full"><el-input v-model="form.marketing_content" type="textarea" :rows="4" /></el-form-item><el-form-item label="保存后重新生成营销素材" class="full"><el-switch v-model="form.regenerate_marketing" active-text="是" inactive-text="否" /></el-form-item></div></el-form>
    <template #footer><el-button @click="editDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveEdit">保存并重算</el-button></template>
  </el-dialog>
</template>

<style scoped>
.header-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}.marketing-copy{font-size:14px;line-height:1.9}.marketing-panel{background:linear-gradient(145deg,#fbfffc,#f4f5ec)}.marketing-panel-actions{display:flex;gap:8px;flex-wrap:wrap}.marketing-tabs{display:flex;gap:7px;border-bottom:1px solid var(--line);padding-bottom:10px;margin-top:18px}.marketing-tabs button{border:0;background:transparent;color:var(--muted);font-size:12px;padding:8px 12px;border-radius:999px;cursor:pointer}.marketing-tabs button.active,.marketing-tabs button:hover{background:var(--teal);color:#fff}.marketing-focus{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:22px;margin-top:18px;padding:16px;background:#fff;border:1px solid #dfece5;border-radius:14px}.marketing-focus__visual{min-width:0}.marketing-focus__visual .marketing-poster{max-width:310px;margin:0 auto 10px;overflow:hidden;border-radius:8px;background:#103d38}.marketing-focus__visual .marketing-poster :deep(svg){display:block;width:100%;height:auto}.marketing-focus__text{min-height:180px;padding:24px;background:#eaf5ef;border-radius:10px}.marketing-focus__text h3{font-size:22px;margin:12px 0}.marketing-focus__text p,.marketing-focus__meta p{font-size:13px;line-height:1.8;white-space:pre-wrap}.marketing-focus__meta{border-left:1px solid var(--line);padding-left:20px}.marketing-focus__meta>span{display:inline-block;color:var(--teal);font-size:10px;letter-spacing:.12em}.marketing-focus__meta small{display:block;color:var(--muted);font-size:11px;line-height:1.7}.marketing-focus__meta strong{display:block;color:var(--teal);font-size:13px;margin-top:18px}.marketing-grid{display:none}.marketing-asset__content{font-size:13px;line-height:1.75;white-space:pre-wrap}.marketing-cta{display:block;color:var(--teal);margin-top:10px}.marketing-poster{margin:14px -2px;overflow:hidden;border-radius:10px;background:#103d38}.marketing-poster :deep(svg){display:block;width:100%;height:auto}@media(max-width:900px){.marketing-focus{grid-template-columns:1fr}.marketing-focus__meta{border-left:0;border-top:1px solid var(--line);padding:15px 0 0}.header-actions{justify-content:flex-start}}
</style>
