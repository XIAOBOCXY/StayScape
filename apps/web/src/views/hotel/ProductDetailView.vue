<script setup lang="ts">
import { posterSvgDataUri } from '../../utils/posterSvg'
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
const marketingDialog = ref(false)
const marketingOptions = reactive({ style: 'SEEDING' as 'ARTISTIC' | 'PROMOTIONAL' | 'EMPATHETIC' | 'SEEDING', generate_image: true })
const marketingStyles = [
  { value: 'ARTISTIC' as const, label: '文艺叙事', hint: '像一段有画面的杭州周末随笔' },
  { value: 'PROMOTIONAL' as const, label: '直接推荐', hint: '清楚说出适合谁、怎么玩、怎么出发' },
  { value: 'EMPATHETIC' as const, label: '情绪共鸣', hint: '从想放松、想陪伴、想换节奏的心情出发' },
  { value: 'SEEDING' as const, label: '轻松种草', hint: '朋友分享式的亮点和周末灵感' }
]
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
  try { const updated = (await hotelApi.updateProduct(product.value.id, { ...form })).data; product.value = updated; fillForm(updated); editDialog.value = false; ElMessage.success('产品内容已保存，出行信息已更新'); await load() }
  catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false }
}
function openMarketingStudio() { marketingDialog.value = true }
async function regenerateMarketing() {
  if (!product.value) return
  marketingLoading.value = true
  try {
    product.value = (await hotelApi.regenerateMarketing(product.value.id, { ...marketingOptions })).data
    marketingDialog.value = false
    ElMessage.success(marketingOptions.generate_image ? '已生成文案、SVG 海报和一张 AI 配图' : '已生成图文海报、社媒文案和短视频脚本')
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { marketingLoading.value = false }
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
        <div><div class="eyebrow">产品详情 · {{ product.product_code }}</div><h1>{{ product.product_name }}</h1><p>{{ product.target_date }} · {{ product.theme }} · {{ product.target_crowd }}</p></div>
        <div class="header-actions"><StatusTag :status="product.status" /><el-button plain @click="editDialog=true">编辑产品</el-button><el-button v-if="product.status === 'DRAFT'" type="primary" @click="setStatus('ON_SALE')">模拟发布</el-button><el-button v-if="['ON_SALE','LOW_STOCK'].includes(product.status)" plain @click="setStatus('PAUSED')">暂停销售</el-button><el-button type="danger" plain @click="removeProduct">删除</el-button></div>
      </div>
      <div class="metric-grid"><div class="metric-card"><div class="metric-label">可售数量</div><div class="metric-value">{{ product.sale_quantity }} 套</div><div class="metric-hint">瓶颈：{{ product.bottleneck_resource }}</div></div><div class="metric-card"><div class="metric-label">单套成本</div><div class="metric-value">¥{{ product.unit_cost }}</div><div class="metric-hint">房间、服务、合作资源合计</div></div><div class="metric-card"><div class="metric-label">建议售价</div><div class="metric-value">¥{{ product.suggested_price }}</div><div class="metric-hint">最低允许 ¥{{ product.minimum_allowed_price }}</div></div><div class="metric-card"><div class="metric-label">单套毛利</div><div class="metric-value">¥{{ product.gross_profit }}</div><div class="metric-hint">毛利率 {{ (Number(product.gross_margin) * 100).toFixed(2) }}%</div></div></div>

      <div class="detail-grid">
        <div>
          <div class="panel"><div class="section-title" style="margin-top:0"><h2>资源组成与时间</h2><span>这次出行包含什么</span></div><table class="data-table"><thead><tr><th>资源</th><th>日期</th><th>场次</th><th>每套消耗</th><th>单位成本</th></tr></thead><tbody><tr v-for="item in product.resources" :key="item.id"><td><strong>{{ item.resource_name }}</strong><div class="muted">{{ item.resource_type }}<span v-if="item.address"> · {{ item.address }}</span></div></td><td>{{ item.available_date || product.target_date }}</td><td>{{ item.start_time?.slice(0,5) || '--' }} - {{ item.end_time?.slice(0,5) || '--' }}</td><td>{{ item.quantity_per_package }}</td><td>¥{{ item.unit_cost }}</td></tr></tbody></table></div>
          <div class="panel marketing-panel marketing-studio" style="margin-top:18px"><div class="section-title" style="margin-top:0"><div><div class="eyebrow">宣传素材</div><h2>把产品变成可发布的内容</h2><span>游客端会直接使用这里的海报、旅行灵感和卖点。</span></div><div class="marketing-panel-actions"><el-button plain @click="router.push(`/visitor/products/${product.id}`)">预览游客端</el-button><el-button type="primary" plain :loading="marketingLoading" @click="openMarketingStudio">生成宣传素材</el-button></div></div><h3>{{ product.marketing_title }}</h3><p class="muted marketing-copy">{{ product.marketing_content }}</p><div v-if="product.marketing_assets?.length" class="marketing-tabs"><button v-for="asset in product.marketing_assets" :key="asset.asset_type" :class="{active: activeAsset?.asset_type === asset.asset_type}" @click="activeAssetType = asset.asset_type">{{ asset.asset_type === 'POSTER' ? '海报' : asset.asset_type === 'SOCIAL_POST' ? '社媒种草' : asset.asset_type === 'SHORT_VIDEO_SCRIPT' ? '短视频脚本' : '门店卖点' }}</button></div><div v-if="activeAsset" class="marketing-focus"><div class="marketing-focus__visual"><img v-if="activeAsset.image_url" class="marketing-poster__image" :src="activeAsset.image_url" :alt="activeAsset.title" /><img v-else-if="activeAsset.poster_svg" class="marketing-poster__image" :src="posterSvgDataUri(activeAsset.poster_svg)" :alt="activeAsset.title" /><div v-else class="marketing-focus__text"><div class="eyebrow">{{ activeAsset.platform }}</div><h3>{{ activeAsset.title }}</h3><p>{{ activeAsset.content }}</p></div><el-button v-if="activeAsset.poster_svg" size="small" plain @click="downloadPoster(activeAsset)">下载 SVG 海报</el-button><small v-if="activeAsset.image_url" class="ai-image-note">AI 配图 · {{ activeAsset.image_model }}<span v-if="activeAsset.image_watermarked"> · 已加 AI 标识</span></small></div><div class="marketing-focus__meta"><span>{{ activeAsset.platform }}</span><p>{{ activeAsset.content }}</p><small>视觉方向：{{ activeAsset.visual_brief }}</small><strong>{{ activeAsset.call_to_action }}</strong></div></div><div v-if="!product.marketing_assets?.length" class="empty-state">暂无营销素材，点击重新生成。</div><p class="danger-text" style="line-height:1.7">{{ product.risk_message }}</p></div>
        </div>
        <div>
          <div class="panel"><div class="section-title" style="margin-top:0"><h2>动态调整</h2><span>{{ adjustments.length }} 条</span></div><div v-if="!adjustments.length" class="empty-state">资源变化会出现在这里</div><div v-for="item in adjustments" :key="item.id" style="padding:13px 0;border-top:1px solid var(--line)"><div style="display:flex;justify-content:space-between"><strong>{{ item.old_quantity }} → {{ item.new_quantity }} 套</strong><span class="muted">{{ item.action }}</span></div><p class="muted" style="line-height:1.6">{{ item.reason }}</p></div></div>
          <div class="panel" style="margin-top:18px"><div class="section-title" style="margin-top:0"><h2>推荐说明</h2></div><p class="muted" style="line-height:1.8">{{ product.recommendation_reason }}</p><p class="danger-text" style="line-height:1.7">{{ product.risk_message }}</p></div>
        </div>
      </div>
    </div>
    <div v-else-if="!loading" class="panel empty-state">产品不存在或已被删除</div>
  </div>

  <el-dialog v-model="marketingDialog" title="生成宣传素材" width="620px">
    <el-form label-position="top">
      <el-form-item label="文案风格">
        <div class="marketing-style-grid"><button v-for="item in marketingStyles" :key="item.value" type="button" :class="{ active: marketingOptions.style === item.value }" @click="marketingOptions.style = item.value"><strong>{{ item.label }}</strong><span>{{ item.hint }}</span></button></div>
      </el-form-item>
      <el-form-item label="产品专属主图">
        <el-switch v-model="marketingOptions.generate_image" active-text="生成产品专属主图" inactive-text="使用精选参考图" />
        <p class="muted form-note">点击生成时，系统会调用百炼万相制作一张与当前产品主题匹配的主图，并嵌入可下载海报。每次仅生成 1 张，可能产生图像费用；浏览器不会接触 API Key。</p>
      </el-form-item>
      <p v-if="marketingOptions.generate_image" class="muted form-note">出图模型由服务器 `.env` 的 `WAN_IMAGE_MODEL` 统一控制，页面不会保存或暴露任何密钥。</p>
    </el-form>
    <template #footer><el-button @click="marketingDialog=false">取消</el-button><el-button type="primary" :loading="marketingLoading" @click="regenerateMarketing">{{ marketingOptions.generate_image ? '生成可发布海报与主图' : '生成文案与 SVG 海报' }}</el-button></template>
  </el-dialog>

  <el-dialog v-model="editDialog" title="编辑产品内容与时间" width="680px">
    <el-form label-position="top"><div class="form-grid"><el-form-item label="产品名称" class="full"><el-input v-model="form.product_name" /></el-form-item><el-form-item label="入住日期"><el-date-picker v-model="form.target_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item><el-form-item label="天气场景"><el-select v-model="form.weather" style="width:100%"><el-option label="小雨 / 室内友好" value="RAIN" /><el-option label="晴天 / 城市漫游" value="SUNNY" /><el-option label="多云 / 轻户外" value="CLOUDY" /></el-select></el-form-item><el-form-item label="目标客群"><el-select v-model="form.target_crowd" style="width:100%"><el-option label="亲子家庭" value="FAMILY" /><el-option label="情侣" value="COUPLE" /><el-option label="本地周末客" value="LOCAL" /></el-select></el-form-item><el-form-item label="主题方向"><el-input v-model="form.theme" /></el-form-item><el-form-item label="营销标题" class="full"><el-input v-model="form.marketing_title" /></el-form-item><el-form-item label="营销内容" class="full"><el-input v-model="form.marketing_content" type="textarea" :rows="4" /></el-form-item><el-form-item label="保存后重新生成营销素材" class="full"><el-switch v-model="form.regenerate_marketing" active-text="是" inactive-text="否" /></el-form-item></div></el-form>
    <template #footer><el-button @click="editDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveEdit">保存并重算</el-button></template>
  </el-dialog>
</template>

<style scoped>
.marketing-style-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;width:100%}.marketing-style-grid button{text-align:left;border:1px solid var(--line);background:#fff;padding:12px;border-radius:10px;color:var(--ink);cursor:pointer}.marketing-style-grid button.active{border-color:var(--teal);background:#eef8f3}.marketing-style-grid strong,.marketing-style-grid span{display:block}.marketing-style-grid span,.form-note,.ai-image-note{font-size:11px;line-height:1.6;color:var(--muted);margin-top:5px}.ai-image-note{display:block;text-align:center}.header-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}.marketing-copy{font-size:14px;line-height:1.9}.marketing-panel{background:linear-gradient(145deg,#fbfffc,#f4f5ec)}.marketing-panel-actions{display:flex;gap:8px;flex-wrap:wrap}.marketing-tabs{display:flex;gap:7px;border-bottom:1px solid var(--line);padding-bottom:10px;margin-top:18px}.marketing-tabs button{border:0;background:transparent;color:var(--muted);font-size:12px;padding:8px 12px;border-radius:999px;cursor:pointer}.marketing-tabs button.active,.marketing-tabs button:hover{background:var(--teal);color:#fff}.marketing-focus{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:22px;margin-top:18px;padding:16px;background:#fff;border:1px solid #dfece5;border-radius:14px}.marketing-focus__visual{min-width:0}.marketing-focus__visual .marketing-poster{max-width:310px;margin:0 auto 10px;overflow:hidden;border-radius:8px;background:#103d38}.marketing-focus__visual .marketing-poster :deep(svg){display:block;width:100%;height:auto}.marketing-focus__text{min-height:180px;padding:24px;background:#eaf5ef;border-radius:10px}.marketing-focus__text h3{font-size:22px;margin:12px 0}.marketing-focus__text p,.marketing-focus__meta p{font-size:13px;line-height:1.8;white-space:pre-wrap}.marketing-focus__meta{border-left:1px solid var(--line);padding-left:20px}.marketing-focus__meta>span{display:inline-block;color:var(--teal);font-size:10px;letter-spacing:.12em}.marketing-focus__meta small{display:block;color:var(--muted);font-size:11px;line-height:1.7}.marketing-focus__meta strong{display:block;color:var(--teal);font-size:13px;margin-top:18px}.marketing-grid{display:none}.marketing-asset__content{font-size:13px;line-height:1.75;white-space:pre-wrap}.marketing-cta{display:block;color:var(--teal);margin-top:10px}.marketing-poster{margin:14px -2px;overflow:hidden;border-radius:10px;background:#103d38}.marketing-poster :deep(svg){display:block;width:100%;height:auto}@media(max-width:900px){.marketing-focus{grid-template-columns:1fr}.marketing-focus__meta{border-left:0;border-top:1px solid var(--line);padding:15px 0 0}.header-actions{justify-content:flex-start}}

/* Stable SVG image rendering */
.marketing-poster__image{display:block;width:100%;height:auto;max-width:100%;border-radius:10px;background:#e8f1ec}
.marketing-focus{gap:18px;padding:18px}.marketing-focus__meta{font-size:14px}.marketing-focus__meta p{font-size:14px;line-height:1.85}
.marketing-panel{padding:24px}.marketing-panel h3{font-size:24px;line-height:1.35;margin:10px 0}.marketing-tabs{margin-top:14px}
@media(max-width:800px){.marketing-panel{padding:18px}.marketing-focus{padding:12px;gap:14px}.marketing-panel h3{font-size:21px}}
</style>

<style scoped>
.detail-grid{gap:22px;margin-top:22px}.metric-grid{gap:12px}.metric-card{padding:18px}.metric-value{font-size:25px}.marketing-panel{background:linear-gradient(135deg,#fff,#f8fbf9 72%,#fcf6ea)}.marketing-focus{grid-template-columns:minmax(300px,.95fr) minmax(220px,.75fr);align-items:center}.marketing-focus__visual{display:flex;flex-direction:column;align-items:center}.marketing-focus__visual .marketing-poster__image{width:min(100%,355px);max-height:470px;object-fit:contain;box-shadow:0 16px 35px rgba(27,65,55,.13);border-radius:14px}.marketing-focus__meta{padding-left:22px}.marketing-focus__meta p{margin-top:12px}.marketing-panel-actions .el-button{min-height:34px}.header-actions{gap:7px}@media(max-width:900px){.marketing-focus{grid-template-columns:1fr}.marketing-focus__visual .marketing-poster__image{max-width:330px}.marketing-focus__meta{padding:16px 0 0;border-left:0;border-top:1px solid var(--line)}}@media(max-width:620px){.metric-grid{grid-template-columns:1fr 1fr}.header-actions{justify-content:flex-start}.marketing-panel-actions{margin-top:10px}}
</style>
