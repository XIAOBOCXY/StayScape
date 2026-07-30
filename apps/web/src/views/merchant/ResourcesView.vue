<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { merchantApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { PartnerResource } from '../../types'

const emptyForm = () => ({
  resource_name: '', category: 'CULTURE', description: '', available_date: '', start_time: '', end_time: '',
  remaining_capacity: 0, settlement_price: '0', market_price: '0', suitable_crowds: 'FAMILY', minimum_age: undefined as number | undefined,
  maximum_age: undefined as number | undefined, indoor: true, weather_tags: 'RAIN,SUNNY,CLOUDY', address: '', booking_notice: '',
  cancellation_rule: '', package_enabled: false, status: 'AVAILABLE', reason: '合作资源更新'
})

const items = ref<PartnerResource[]>([])
const loading = ref(false)
const dialog = ref(false)
const saving = ref(false)
const current = ref<PartnerResource | null>(null)
const form = reactive(emptyForm())
const referencesDialog = ref(false)
const references = ref<Array<Record<string, unknown>>>([])

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
    <div><div class="eyebrow">MY CULTURAL RESOURCES</div><h1>我的文旅资源</h1><p>资源名称、活动日期、场次、名额和结算价由商户维护；更新后酒店产品会立即重算。</p></div>
    <div><el-button plain @click="load">刷新</el-button><el-button type="primary" @click="openCreate">＋ 新增资源</el-button></div>
  </div>
  <div class="panel table-wrap">
    <el-table v-loading="loading" :data="items" style="width:100%">
      <el-table-column prop="resource_name" label="资源名称" min-width="190" />
      <el-table-column prop="category" label="类别" width="110" />
      <el-table-column prop="available_date" label="活动日期" width="125" />
      <el-table-column label="活动场次" width="160"><template #default="{row}">{{ row.start_time?.slice(0,5) || '--' }} - {{ row.end_time?.slice(0,5) || '--' }}</template></el-table-column>
      <el-table-column label="剩余名额" width="110"><template #default="{row}"><strong :class="row.remaining_capacity <= 5 ? 'warning-text' : ''">{{ row.remaining_capacity }}</strong></template></el-table-column>
      <el-table-column label="结算价" width="100"><template #default="{row}">¥{{ row.settlement_price }}</template></el-table-column>
      <el-table-column label="组包许可" width="110"><template #default="{row}"><StatusTag :status="row.package_enabled ? 'AVAILABLE' : 'UNAVAILABLE'" /></template></el-table-column>
      <el-table-column label="状态" width="105"><template #default="{row}"><StatusTag :status="row.status" /></template></el-table-column>
      <el-table-column label="引用产品" width="100"><template #default="{row}"><el-button link type="primary" @click="viewReferences(row)">{{ row.referenced_product_count }} 个</el-button></template></el-table-column>
      <el-table-column label="操作" width="130"><template #default="{row}"><el-button link type="primary" @click="openEdit(row)">编辑资源</el-button></template></el-table-column>
    </el-table>
    <div v-if="!loading && !items.length" class="empty-state">暂无资源，先新增一项可预约的杭州文化体验。</div>
  </div>

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
