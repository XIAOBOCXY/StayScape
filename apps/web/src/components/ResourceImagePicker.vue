<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, type UploadRequestOptions } from 'element-plus'
import { hotelApi, merchantApi } from '../api'
import { errorMessage } from '../api/client'

const props = withDefaults(defineProps<{
  modelValue?: string
  source?: string
  attribution?: string
  query?: string
  label?: string
  scope?: 'hotel' | 'merchant'
}>(), { modelValue: '', source: '', attribution: '', query: '杭州旅行', label: '图片', scope: 'hotel' })

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:source': [value: string]
  'update:attribution': [value: string]
}>()

const pickerVisible = ref(false)
const query = ref('')
const searching = ref(false)
const importing = ref(false)
const candidates = ref<Array<{ title: string; preview_url: string; source_url: string; source: string; attribution: string; detail_url: string }>>([])

function setImage(asset: { image_url: string; image_source: string; image_attribution: string }) {
  emit('update:modelValue', asset.image_url)
  emit('update:source', asset.image_source)
  emit('update:attribution', asset.image_attribution)
}

async function upload(option: UploadRequestOptions) {
  try {
    const response = await (props.scope === 'merchant' ? merchantApi.uploadMedia(option.file) : hotelApi.uploadMedia(option.file))
    setImage(response.data)
    option.onSuccess?.(response.data)
    ElMessage.success('图片已上传')
  } catch (error) {
    // Element Plus expects its upload-shaped error here; keep the original
    // request failure visible without pretending that the upload succeeded.
    option.onError?.(Object.assign(new Error(errorMessage(error)), { status: 0, method: 'POST', url: '' }) as any)
    ElMessage.error(errorMessage(error))
  }
}

function openPicker() {
  query.value = props.query || '杭州旅行'
  candidates.value = []
  pickerVisible.value = true
  search()
}

async function search() {
  if (query.value.trim().length < 2) { ElMessage.warning('请输入至少两个字的搜索词'); return }
  searching.value = true
  try { candidates.value = (await (props.scope === 'merchant' ? merchantApi.searchMedia(query.value.trim()) : hotelApi.searchMedia(query.value.trim()))).data.items }
  catch (error) { ElMessage.error(errorMessage(error)) }
  finally { searching.value = false }
}

async function choose(item: { source_url: string; source: string; attribution: string }) {
  importing.value = true
  try {
    const response = await (props.scope === 'merchant' ? merchantApi.importMedia({ url: item.source_url, source: item.source, attribution: item.attribution }) : hotelApi.importMedia({ url: item.source_url, source: item.source, attribution: item.attribution }))
    setImage(response.data)
    pickerVisible.value = false
    ElMessage.success('已保存网络图片，可随时替换为实拍图')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { importing.value = false }
}

function clear() { setImage({ image_url: '', image_source: '', image_attribution: '' }) }
</script>

<template>
  <div class="resource-image-picker">
    <div class="resource-image-picker__preview">
      <img v-if="modelValue" :src="modelValue" :alt="label" />
      <span v-else>未设置图片</span>
    </div>
    <div class="resource-image-picker__actions">
      <el-upload :show-file-list="false" accept="image/jpeg,image/png,image/webp" :http-request="upload">
        <el-button size="small">上传实拍图</el-button>
      </el-upload>
      <el-button size="small" plain @click="openPicker">从网络补图</el-button>
      <el-button v-if="modelValue" size="small" link @click="clear">移除</el-button>
      <small>{{ source || '未上传时，游客端将自动检索网络参考图' }}</small>
    </div>
  </div>

  <el-dialog v-model="pickerVisible" title="选择网络参考图片" width="min(94vw, 900px)" top="6vh">
    <div class="network-search"><el-input v-model="query" clearable placeholder="例如：杭州 城市博物馆、亲子 乐园、精品酒店客房" @keyup.enter="search" /><el-button type="primary" :loading="searching" @click="search">搜索</el-button></div>
    <p class="network-note">仅检索 Wikimedia Commons 的公开图片；选中后会保存到服务器，避免直接引用受限网站图片。商户实拍图始终优先。</p>
    <div v-loading="searching" class="network-results"><button v-for="item in candidates" :key="item.source_url" :disabled="importing" @click="choose(item)"><img :src="item.preview_url" :alt="item.title" /><span>{{ item.title }}</span><small>{{ item.attribution || item.source }}</small></button></div>
    <div v-if="!searching && !candidates.length" class="empty-state">没有找到合适图片，可换个更具体的地点或体验名称。</div>
  </el-dialog>
</template>

<style scoped>
.resource-image-picker{display:flex;gap:12px;align-items:stretch}.resource-image-picker__preview{display:grid;place-items:center;flex:0 0 130px;height:94px;overflow:hidden;border:1px dashed var(--line);border-radius:9px;background:var(--panel-soft);color:var(--muted);font-size:11px}.resource-image-picker__preview img{width:100%;height:100%;object-fit:cover}.resource-image-picker__actions{display:flex;flex:1;flex-wrap:wrap;align-content:center;align-items:center;gap:7px}.resource-image-picker__actions small{flex-basis:100%;color:var(--muted);font-size:10px;line-height:1.45}.network-search{display:flex;gap:8px}.network-results{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;min-height:120px;margin-top:14px}.network-results button{overflow:hidden;padding:0 0 8px;border:1px solid var(--line);border-radius:10px;background:#fff;color:var(--ink);text-align:left;cursor:pointer}.network-results button:hover{border-color:var(--teal);box-shadow:0 8px 20px rgba(20,35,29,.09)}.network-results img{display:block;width:100%;height:116px;object-fit:cover}.network-results span,.network-results small{display:block;overflow:hidden;padding:0 8px;text-overflow:ellipsis;white-space:nowrap}.network-results span{margin-top:8px;font-size:12px;font-weight:650}.network-results small{margin-top:4px;color:var(--muted);font-size:9px}@media(max-width:650px){.resource-image-picker{align-items:center}.resource-image-picker__preview{flex-basis:100px;height:82px}.network-results{grid-template-columns:repeat(2,minmax(0,1fr))}.network-results img{height:102px}}
</style>
