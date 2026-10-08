<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'

type KnowledgeRecord = Record<string, any>

const items = ref<KnowledgeRecord[]>([])
const categories = ref<Array<{ value: string; label: string }>>([])
const loading = ref(false)
const keyword = ref('')
const category = ref('')
const selected = ref<KnowledgeRecord | null>(null)
const refreshing = ref(false)

const statusLabel = computed(() => (status: string) => ({
  ACTIVE: '已核验',
  VERIFY_REQUIRED: '需确认',
  STALE: '待复核',
  UNAVAILABLE: '不可用'
} as Record<string, string>)[status] || status)

const statusType = computed(() => (status: string) => (status === 'ACTIVE' ? 'success' : status === 'STALE' ? 'warning' : 'info'))

function durationText(minutes?: number | null) {
  if (!minutes) return '未标注'
  return minutes >= 60 ? `约 ${Math.round(minutes / 60 * 10) / 10} 小时` : `约 ${minutes} 分钟`
}

async function load() {
  loading.value = true
  try {
    const response = await hotelApi.knowledge({ q: keyword.value || undefined, category: category.value || undefined, limit: 120 })
    items.value = response.data.items || []
    categories.value = (response.data.categories || []) as unknown as Array<{ value: string; label: string }>
    if (!selected.value && items.value.length) selected.value = items.value[0]
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { loading.value = false }
}

function reset() { keyword.value = ''; category.value = ''; void load() }

async function refreshSources() {
  refreshing.value = true
  try {
    const response = await hotelApi.refreshKnowledge()
    const data = response.data
    ElMessage.success(`已检查 ${data.checked} 条来源`)
    await load()
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { refreshing.value = false }
}

const reviewFields = [
  'name', 'category', 'area', 'address', 'indoor_outdoor', 'suitable_crowds',
  'minimum_age', 'maximum_age', 'suggested_duration_minutes', 'opening_hours',
  'weather_adaptations', 'reservation_notice', 'description', 'source_name', 'source_url'
]

async function verifySelected() {
  if (!selected.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请先打开来源页面，逐项对照地点名称、类别、区域、地址、适合人群、年龄、时长、开放时间、天气适配、预约提示、介绍及来源信息。确认全部一致后，填写简要核验说明。',
      '人工核验文旅事实',
      { confirmButtonText: '确认已逐项核对', cancelButtonText: '取消', inputPlaceholder: '例如：已对照景区官网开放时间与地址，2026-10-01', inputValidator: (v: string) => v.trim().length >= 8 || '请填写至少 8 个字符的核验说明' }
    )
    const id = selected.value.id
    await hotelApi.verifyKnowledge(id, reviewFields, value)
    ElMessage.success('已记录人工核验')
    await load()
    selected.value = items.value.find(item => item.id === id) || null
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

onMounted(load)
</script>

<template>
  <div class="knowledge-page">
    <div v-toolbar class="header-actions"><span class="live-pill"><i /> {{ items.length }} 条记录</span><el-button plain :loading="loading" @click="load">刷新列表</el-button><el-button type="primary" :loading="refreshing" @click="refreshSources">检查来源链接</el-button></div>

    <section class="knowledge-filter">
      <el-input v-model="keyword" placeholder="搜索地点、类别、开放时间或来源" clearable @keyup.enter="load" />
      <el-select v-model="category" placeholder="全部类别" clearable>
        <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <el-button plain @click="reset">重置</el-button>
    </section>

    <section class="knowledge-layout" :class="{ 'has-selection': selected }">
      <div class="panel knowledge-table">
        <div v-loading="loading" class="knowledge-list">
          <button
            v-for="row in items"
            :key="row.id"
            type="button"
            class="knowledge-row"
            :class="{ selected: selected?.id === row.id }"
            :aria-pressed="selected?.id === row.id"
            @click="selected = row"
          >
            <span class="knowledge-row__heading"><strong>{{ row.name }}</strong><el-tag :type="statusType(row.status)" effect="light">{{ statusLabel(row.status) }}</el-tag></span>
            <span class="knowledge-row__meta">{{ row.category_label }} · {{ row.area }} <i>·</i> {{ durationText(row.suggested_duration_minutes) }}</span>
            <span class="knowledge-row__opening">{{ row.opening_hours || '开放时间未收录' }}</span>
            <span class="knowledge-row__source">来源：{{ row.source_name || '未注明' }}</span>
          </button>
        </div>
        <div v-if="!loading && !items.length" class="empty-state">没有匹配的知识记录，换一个关键词试试。</div>
      </div>

      <aside v-if="selected" class="panel knowledge-detail">
        <template v-if="selected">
          <div class="eyebrow">{{ selected.category_label }} · {{ selected.area }}</div>
          <div class="knowledge-detail__title"><h2>{{ selected.name }}</h2><el-tag :type="statusType(selected.status)" effect="light">{{ statusLabel(selected.status) }}</el-tag></div>
          <div class="detail-tags">
            <span>{{ selected.indoor_outdoor_label }}</span>
            <span>适合 {{ selected.suitable_crowds_label }}</span>
            <span v-if="selected.minimum_age">{{ selected.minimum_age }}–{{ selected.maximum_age ?? 70 }} 岁</span>
            <span>{{ durationText(selected.suggested_duration_minutes) }}</span>
            <span>{{ selected.weather_adaptations_label }}</span>
          </div>
          <dl>
            <dt>地址</dt><dd>{{ selected.address || '未收录' }}</dd>
            <dt>开放时间</dt><dd>{{ selected.opening_hours || '未收录' }}</dd>
            <dt>预约提示</dt><dd>{{ selected.reservation_notice || '未收录' }}</dd>
            <dt>天气适配</dt><dd>{{ selected.weather_adaptations_label || selected.weather_adaptations || '未标注' }}</dd>
            <dt>原文</dt><dd class="verbatim">{{ selected.description || '未收录' }}</dd>
            <dt>来源</dt><dd>{{ selected.source_name }}<a v-if="selected.source_url" :href="selected.source_url" target="_blank" rel="noreferrer">打开来源</a></dd>
            <dt>核验记录</dt><dd>{{ selected.verified_at ? String(selected.verified_at).slice(0, 10) : '尚未核验' }}</dd>
          </dl>
          <el-button v-if="selected.status !== 'ACTIVE'" type="primary" plain :disabled="!selected.source_url" @click="verifySelected">对照来源并记录核验</el-button>
        </template>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.knowledge-page { display: grid; gap: 12px; min-width: 0; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.knowledge-filter { display: grid; min-width: 0; grid-template-columns: minmax(220px, 1.4fr) 180px auto auto; gap: 10px; align-items: center; padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper); }
.knowledge-layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; align-items: start; min-width: 0; }
.knowledge-layout.has-selection { grid-template-columns: minmax(0, 1.7fr) minmax(300px, .9fr); }
.knowledge-table { min-width: 0; padding: 8px 12px 12px; }
.knowledge-list { display: grid; max-height: 720px; overflow: auto; }
.knowledge-row { display: grid; gap: 5px; width: 100%; min-width: 0; padding: 12px 10px; border: 0; border-bottom: 1px solid #edf0ed; background: transparent; color: var(--ink); text-align: left; cursor: pointer; }
.knowledge-row:hover,.knowledge-row.selected { background: #f5f8f5; }
.knowledge-row.selected { box-shadow: inset 3px 0 #507461; }
.knowledge-row__heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.knowledge-row__heading strong { min-width: 0; font-size: 14px; line-height: 1.45; }
.knowledge-row__heading :deep(.el-tag) { flex: 0 0 auto; }
.knowledge-row__meta,.knowledge-row__opening,.knowledge-row__source { overflow: hidden; color: #68736c; font-size: 12px; line-height: 1.5; text-overflow: ellipsis; white-space: nowrap; }
.knowledge-row__meta i { margin: 0 3px; color: #a4ada6; font-style: normal; }
.knowledge-row__source { color: #818a83; font-size: 11.5px; }
.knowledge-detail { min-width: 0; padding: 16px; }
.knowledge-detail__title { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.knowledge-detail h2 { min-width:0; margin: 7px 0 10px; font-size: 19px; }
.detail-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.detail-tags span { padding: 4px 8px; border-radius: 999px; background: var(--panel-soft); color: var(--muted); font-size: 10px; }
.knowledge-detail dl { margin: 0; }
.knowledge-detail dt { margin-top: 12px; color: var(--muted); font-size: 10px; letter-spacing: .08em; }
.knowledge-detail dd { margin: 5px 0 0; color: var(--ink); font-size: 12px; line-height: 1.7; }
.knowledge-detail dd a { margin-left: 8px; color: var(--teal); font-size: 11px; }
.knowledge-detail .verbatim { padding: 10px 12px; border-left: 2px solid var(--teal); background: var(--panel-soft); font-size: 12px; }
.empty-state { padding: 26px; color: var(--muted); font-size: 12px; text-align: center; }
@media (max-width: 1080px) {
  .knowledge-layout, .knowledge-layout.has-selection { grid-template-columns: minmax(0, 1fr); }
  .knowledge-list { max-height: 480px; }
  .knowledge-filter { grid-template-columns: 1fr 1fr; }
}
</style>
