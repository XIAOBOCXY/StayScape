<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { merchantApi } from '../../api'
import { errorMessage } from '../../api/client'
import DateHeatmap from '../../components/DateHeatmap.vue'
import MediaImage from '../../components/MediaImage.vue'
import StatusTag from '../../components/StatusTag.vue'
import ResourceImagePicker from '../../components/ResourceImagePicker.vue'
import type { PartnerResource } from '../../types'
import { automaticNetworkMedia, MEDIA_LIBRARY } from '../../utils/productMedia'

const emptyForm = () => ({
  resource_name: '', category: 'CULTURE', description: '', available_date: '', start_time: '', end_time: '',
  remaining_capacity: 0, settlement_price: '0', market_price: '0', suitable_crowds: 'FAMILY', minimum_age: undefined as number | undefined,
  maximum_age: undefined as number | undefined, indoor: true, weather_tags: 'RAIN,SUNNY,CLOUDY', address: '', booking_notice: '',
  cancellation_rule: '', image_url: '', image_source: '', image_attribution: '', package_enabled: false, status: 'AVAILABLE', reason: '合作资源更新'
})

const items = ref<PartnerResource[]>([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const current = ref<PartnerResource | null>(null)
const form = reactive(emptyForm())
const referencesDialog = ref(false)
const references = ref<Array<Record<string, unknown>>>([])
const selectedDate = ref('')
const viewMode = ref<'cards' | 'list'>('cards')
const visibleItems = computed(() => selectedDate.value ? items.value.filter((item) => item.available_date === selectedDate.value) : items.value)

function resourceMedia(row: PartnerResource) {
  if (row.image_url) return { ...MEDIA_LIBRARY.city, id: `merchant-resource-${row.id}`, url: row.image_url, source: row.image_source || '商户图片', source_url: row.image_attribution || row.image_url }
  const text = `${row.resource_name} ${row.category} ${row.description || ''}`.toLowerCase()
  const fallback = /博物馆|展览|良渚|丝绸/.test(text) ? MEDIA_LIBRARY.liangzhuMuseum
    : /乐园|游乐/.test(text) ? MEDIA_LIBRARY.songcheng
      : /运动|攀岩|卡丁车/.test(text) ? MEDIA_LIBRARY.climbing
        : /西溪|自然|湿地/.test(text) ? MEDIA_LIBRARY.xixi
          : /美食|餐|咖啡/.test(text) ? MEDIA_LIBRARY.warmFood
            : /茶|龙井/.test(text) ? MEDIA_LIBRARY.longjing
              : MEDIA_LIBRARY.city
  return automaticNetworkMedia(`${row.resource_name} ${row.address || '杭州'} ${row.category || ''}`, fallback.kind)
}
function session(row: PartnerResource) { return row.start_time && row.end_time ? `${row.start_time.slice(0, 5)} – ${row.end_time.slice(0, 5)}` : '预约后确认时间' }

function resetForm() { Object.assign(form, emptyForm()) }
function normalizeTime(value?: string) { return value ? value.slice(0, 5) : '' }
function openCreate() { current.value = null; resetForm(); dialog.value = true }
function openEdit(row: PartnerResource) {
  current.value = row
  Object.assign(form, {
    ...row,
    start_time: normalizeTime(row.start_time),
    end_time: normalizeTime(row.end_time),
    reason: row.remaining_capacity > 0 ? '商户更新活动场次与实时名额' : '商户暂停资源'
  })
  dialog.value = true
}
async function load() { loading.value = true; try { items.value = (await merchantApi.resources()).data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
async function save() {
  if (!form.resource_name.trim()) { ElMessage.warning('请先填写资源名称'); return }
  if (form.start_time && form.end_time && form.start_time >= form.end_time) { ElMessage.warning('活动开始时间必须早于结束时间'); return }
  if (form.minimum_age !== undefined && form.maximum_age !== undefined && form.maximum_age < form.minimum_age) { ElMessage.warning('最大适龄年龄不能小于最小适龄年龄'); return }
  saving.value = true
  try {
    const payload = { ...form, resource_name: form.resource_name.trim(), start_time: form.start_time || undefined, end_time: form.end_time || undefined }
    if (current.value) {
      const response = await merchantApi.updateResource(current.value.id, payload)
      ElMessage.success((response.data.message as string) || '资源更新成功，受影响产品已重算')
    } else {
      await merchantApi.createResource(payload)
      ElMessage.success('资源已新增，可在酒店资源池中申请组包')
    }
    dialog.value = false
    await load()
  } catch (e) { ElMessage.error(errorMessage(e)) } finally { saving.value = false }
}
async function viewReferences(row: PartnerResource) {
  try { references.value = (await merchantApi.references(row.id)).data; referencesDialog.value = true } catch (e) { ElMessage.error(errorMessage(e)) }
}
onMounted(load)
</script>

<template>
  <div class="page-head">
    <div><div class="eyebrow">我的资源</div><h1>合作资源管理</h1><p>按日期维护活动、场次、名额、价格与展示图片；变更会同步到相关产品。</p></div>
    <div class="header-actions"><el-radio-group v-model="viewMode" class="view-mode-switch" size="small" aria-label="资源展示方式"><el-radio-button label="cards">卡片</el-radio-button><el-radio-button label="list">列表</el-radio-button></el-radio-group><el-button plain @click="load">刷新</el-button><el-button type="primary" @click="openCreate">＋ 新增资源</el-button></div>
  </div>
  <div class="merchant-toolbar panel"><DateHeatmap v-model="selectedDate" :items="items" quantity-key="remaining_capacity" label="活动日期" /></div>
  <div v-if="viewMode === 'cards'" v-loading="loading" class="merchant-resource-grid">
    <button v-for="row in visibleItems" :key="row.id" class="merchant-resource-card" @click="openEdit(row)"><MediaImage :media="resourceMedia(row)" aspect="card" /><div class="merchant-resource-card__body"><div class="merchant-resource-card__top"><span>{{ row.category || '体验活动' }}</span><strong :class="row.remaining_capacity <= 5 ? 'warning-text' : ''">余 {{ row.remaining_capacity }}</strong></div><h2>{{ row.resource_name }}</h2><p>{{ row.available_date }} · {{ session(row) }}</p><div class="merchant-resource-card__bottom"><span>¥{{ row.settlement_price }}</span><StatusTag :status="row.status" /></div></div></button>
  </div>
  <div v-else class="panel table-wrap">
    <el-table v-loading="loading" :data="visibleItems" style="width:100%" @row-click="openEdit">
      <el-table-column prop="resource_name" label="资源名称" min-width="190"><template #default="{row}"><strong>{{ row.resource_name }}</strong><div class="muted">{{ row.category || '体验活动' }}</div></template></el-table-column>
      <el-table-column prop="category" label="类别" width="110" />
      <el-table-column prop="available_date" label="活动日期" width="125" />
      <el-table-column label="活动场次" width="160"><template #default="{row}">{{ row.start_time?.slice(0,5) || '--' }} - {{ row.end_time?.slice(0,5) || '--' }}</template></el-table-column>
      <el-table-column label="剩余名额" width="110"><template #default="{row}"><strong :class="row.remaining_capacity <= 5 ? 'warning-text' : ''">{{ row.remaining_capacity }}</strong></template></el-table-column>
      <el-table-column label="结算价" width="100"><template #default="{row}">¥{{ row.settlement_price }}</template></el-table-column>
      <el-table-column label="组包许可" width="110"><template #default="{row}"><StatusTag :status="row.package_enabled ? 'AVAILABLE' : 'UNAVAILABLE'" /></template></el-table-column>
      <el-table-column label="状态" width="105"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column>
      <el-table-column label="引用产品" width="100"><template #default="{row}"><el-button link type="primary" @click="viewReferences(row)">{{ row.referenced_product_count }} 个</el-button></template></el-table-column>
      <el-table-column label="操作" width="130"><template #default="{row}"><el-button link type="primary" @click.stop="openEdit(row)">编辑资源</el-button></template></el-table-column>
    </el-table>
  </div>
  <div v-if="!loading && !visibleItems.length" class="panel empty-state">这一天暂无资源，可新增一项体验或切换日期。</div>

  <el-dialog v-model="dialog" :title="current ? '编辑文旅资源' : '新增文旅资源'" width="760px" top="5vh">
    <el-form label-position="top">
      <div class="form-grid">
        <el-form-item class="full" label="资源名称" required><el-input v-model="form.resource_name" placeholder="例如：室内宋韵点茶体验" maxlength="160" show-word-limit /></el-form-item>
        <el-form-item label="资源类别"><el-select v-model="form.category" style="width:100%"><el-option label="文化体验" value="CULTURE" /><el-option label="亲子旅拍" value="PHOTO" /><el-option label="景区活动" value="ATTRACTION" /><el-option label="餐饮体验" value="DINING" /></el-select></el-form-item>
        <el-form-item label="适合客群"><el-select v-model="form.suitable_crowds" style="width:100%"><el-option label="亲子家庭" value="FAMILY" /><el-option label="情侣" value="COUPLE" /><el-option label="本地周末客" value="LOCAL" /><el-option label="全部客群" value="ALL" /></el-select></el-form-item>
        <el-form-item label="活动日期" required><el-date-picker v-model="form.available_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="活动场次"><div style="display:flex;gap:8px;width:100%"><el-time-picker v-model="form.start_time" value-format="HH:mm" format="HH:mm" placeholder="开始" style="width:50%" /><el-time-picker v-model="form.end_time" value-format="HH:mm" format="HH:mm" placeholder="结束" style="width:50%" /></div></el-form-item>
        <el-form-item label="实时剩余名额"><el-input-number v-model="form.remaining_capacity" :min="0" :max="99999" style="width:100%" /></el-form-item>
        <el-form-item label="酒店结算价"><el-input v-model="form.settlement_price"><template #prepend>¥</template></el-input></el-form-item>
        <el-form-item label="游客参考价"><el-input v-model="form.market_price"><template #prepend>¥</template></el-input></el-form-item>
        <el-form-item label="适龄范围"><div style="display:flex;gap:8px;width:100%"><el-input-number v-model="form.minimum_age" :min="0" :max="120" placeholder="最小" style="width:50%" /><el-input-number v-model="form.maximum_age" :min="0" :max="120" placeholder="最大" style="width:50%" /></div></el-form-item>
        <el-form-item label="天气标签"><el-input v-model="form.weather_tags" placeholder="RAIN,SUNNY,CLOUDY" /></el-form-item>
        <el-form-item label="活动地址"><el-input v-model="form.address" placeholder="例如：拱宸桥非遗工坊" /></el-form-item>
        <el-form-item label="室内活动"><el-switch v-model="form.indoor" active-text="室内" inactive-text="户外" /></el-form-item>
        <el-form-item label="组包许可"><el-switch v-model="form.package_enabled" active-text="允许酒店组包" /></el-form-item>
        <el-form-item v-if="current" label="资源状态"><el-select v-model="form.status" style="width:100%"><el-option label="可用" value="AVAILABLE" /><el-option label="暂停" value="SUSPENDED" /><el-option label="不可用" value="UNAVAILABLE" /></el-select></el-form-item>
        <el-form-item class="full" label="资源介绍"><el-input v-model="form.description" type="textarea" :rows="2" placeholder="介绍体验内容、适合人群和特色" /></el-form-item>
        <el-form-item class="full" label="展示图片"><ResourceImagePicker v-model="form.image_url" v-model:source="form.image_source" v-model:attribution="form.image_attribution" scope="merchant" :query="`${form.resource_name || '杭州'} ${form.address || '文旅体验'}`" /></el-form-item>
        <el-form-item label="预约须知"><el-input v-model="form.booking_notice" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="取消规则"><el-input v-model="form.cancellation_rule" type="textarea" :rows="2" /></el-form-item>
        <el-form-item class="full" label="变更原因"><el-input v-model="form.reason" type="textarea" :rows="2" /></el-form-item>
      </div>
    </el-form>
    <template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存资源</el-button></template>
  </el-dialog>

  <el-dialog v-model="referencesDialog" title="被哪些酒店产品引用" width="560px">
    <el-table :data="references"><el-table-column prop="product_name" label="产品" min-width="220" /><el-table-column prop="sale_quantity" label="可售" width="80" /><el-table-column prop="status" label="状态" width="100" /></el-table>
    <div v-if="!references.length" class="empty-state">暂时没有酒店产品引用此资源。</div>
  </el-dialog>
</template>

<style scoped>
.header-actions,.merchant-toolbar{display:flex;align-items:center;gap:10px}.header-actions{justify-content:flex-end;flex-wrap:wrap}.view-mode-switch{order:-1}.merchant-toolbar{margin-bottom:12px;padding:10px}.merchant-toolbar :deep(.date-heatmap){width:100%;border:0;padding:0;background:transparent}.merchant-resource-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:10px}.merchant-resource-card{display:grid;grid-template-columns:98px minmax(0,1fr);min-height:128px;overflow:hidden;padding:0;border:1px solid var(--line);border-radius:12px;background:var(--paper);color:var(--ink);text-align:left;cursor:pointer;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}.merchant-resource-card:hover{transform:translateY(-2px);border-color:#b9c8c2;box-shadow:0 12px 26px rgba(20,25,23,.08)}.merchant-resource-card :deep(.media-image){height:100%;min-height:128px;aspect-ratio:auto;border-radius:0}.merchant-resource-card__body{min-width:0;padding:11px}.merchant-resource-card__top,.merchant-resource-card__bottom{display:flex;align-items:center;justify-content:space-between;gap:8px}.merchant-resource-card__top span{overflow:hidden;color:var(--muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.merchant-resource-card__top strong{font-family:var(--font-mono);font-size:13px}.merchant-resource-card h2{overflow:hidden;margin:7px 0 4px;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.merchant-resource-card p{overflow:hidden;margin:0;color:var(--muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.merchant-resource-card__bottom{margin-top:10px;padding-top:8px;border-top:1px solid var(--line);font-family:var(--font-mono);font-size:12px}.merchant-resource-card__bottom :deep(.status-tag){font-family:var(--font-sans)}@media(max-width:700px){.header-actions{justify-content:flex-start;margin-top:12px}.merchant-toolbar{align-items:stretch;flex-direction:column}.merchant-resource-grid{grid-template-columns:1fr}.merchant-resource-card{grid-template-columns:92px minmax(0,1fr);min-height:118px}.merchant-resource-card :deep(.media-image){min-height:118px}.merchant-resource-card__body{padding:9px}}
</style>
