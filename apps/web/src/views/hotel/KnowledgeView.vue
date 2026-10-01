<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'

type KnowledgeRecord = Record<string, any>

const items = ref<KnowledgeRecord[]>([])
const categories = ref<Array<{ value: string; label: string }>>([])
const disclosure = ref('')
const loading = ref(false)
const keyword = ref('')
const category = ref('')
const selected = ref<KnowledgeRecord | null>(null)
const refreshing = ref(false)
const refreshNote = ref('')

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
    disclosure.value = response.data.disclosure || ''
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { loading.value = false }
}

function reset() { keyword.value = ''; category.value = ''; void load() }

async function refreshSources() {
  refreshing.value = true
  try {
    const response = await hotelApi.refreshKnowledge()
    const data = response.data
    refreshNote.value = '已检查 ' + data.checked + ' 条来源链接，其中 ' + data.reachable_count + ' 条可访问；这不代表事实已核验。'
    ElMessage.success('来源链接检查完成')
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
      <small>{{ disclosure }}</small>
      <small v-if="refreshNote" class="refresh-note">{{ refreshNote }}</small>
    </section>

    <section class="knowledge-layout">
      <div class="panel knowledge-table">
        <el-table v-loading="loading" :data="items" height="560" @row-click="(row: KnowledgeRecord) => selected = row">
          <el-table-column label="地点 / 类别" min-width="210">
            <template #default="{ row }"><strong>{{ row.name }}</strong><small class="table-subline">{{ row.category_label }} · {{ row.area }}</small></template>
          </el-table-column>
          <el-table-column label="建议停留" width="110"><template #default="{ row }">{{ durationText(row.suggested_duration_minutes) }}</template></el-table-column>
          <el-table-column label="开放时间" min-width="170"><template #default="{ row }">{{ row.opening_hours || '未收录' }}</template></el-table-column>
          <el-table-column label="来源" min-width="150"><template #default="{ row }">{{ row.source_name }}</template></el-table-column>
          <el-table-column label="人工核验" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)" effect="light">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="核验日期" width="110"><template #default="{ row }">{{ row.verified_at ? String(row.verified_at).slice(0, 10) : '未核验' }}</template></el-table-column>
        </el-table>
        <div v-if="!loading && !items.length" class="empty-state">没有匹配的知识记录，换一个关键词试试。</div>
      </div>

      <aside class="panel knowledge-detail">
        <template v-if="selected">
          <div class="eyebrow">{{ selected.category_label }} · {{ selected.area }}</div>
          <h2>{{ selected.name }}</h2>
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
            <dt>核验</dt><dd>{{ statusLabel(selected.status) }}<template v-if="selected.source_age_days !== null"> · 已过 {{ selected.source_age_days }} 天（复核窗口 {{ selected.review_window_days }} 天）</template></dd>
          </dl>
          <p class="detail-note">链接可访问不代表事实准确。{{ selected.source_checked_at ? '最近检查：' + String(selected.source_checked_at).slice(0, 16).replace('T', ' ') + '；' + (selected.source_reachable ? '来源可访问' : '来源暂不可访问') + '。' : '尚未检查来源链接。' }}</p>
          <el-button v-if="selected.status !== 'ACTIVE'" type="primary" plain :disabled="!selected.source_url" @click="verifySelected">对照来源并记录核验</el-button>
        </template>
        <div v-else class="empty-state">从左侧选择一条记录查看公开资料原文与来源。</div>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.knowledge-page { display: grid; gap: 14px; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.knowledge-filter { display: grid; grid-template-columns: minmax(220px, 1.4fr) 180px auto auto; gap: 10px; align-items: center; padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper); }
.knowledge-filter small { grid-column: 1 / -1; color: var(--muted); font-size: 10px; line-height: 1.6; }
.knowledge-filter .refresh-note { color: var(--teal); }
.knowledge-layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(300px, 1fr); gap: 12px; align-items: start; }
.knowledge-table { padding: 8px 12px 12px; }
.knowledge-table :deep(.el-table__row) { cursor: pointer; }
.table-subline { display: block; margin-top: 4px; color: var(--muted); font-size: 11px; }
.knowledge-detail { padding: 18px; }
.knowledge-detail h2 { margin: 7px 0 10px; font-size: 20px; }
.detail-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.detail-tags span { padding: 4px 8px; border-radius: 999px; background: var(--panel-soft); color: var(--muted); font-size: 10px; }
.knowledge-detail dl { margin: 0; }
.knowledge-detail dt { margin-top: 12px; color: var(--muted); font-size: 10px; letter-spacing: .08em; }
.knowledge-detail dd { margin: 5px 0 0; color: var(--ink); font-size: 12px; line-height: 1.7; }
.knowledge-detail dd a { margin-left: 8px; color: var(--teal); font-size: 11px; }
.knowledge-detail .verbatim { padding: 10px 12px; border-left: 2px solid var(--teal); background: var(--panel-soft); font-size: 12px; }
.detail-note { margin: 16px 0 0; padding-top: 12px; border-top: 1px solid var(--line); color: var(--muted); font-size: 10px; line-height: 1.65; }
.empty-state { padding: 26px; color: var(--muted); font-size: 12px; text-align: center; }
@media (max-width: 1080px) {
  .knowledge-layout { grid-template-columns: 1fr; }
  .knowledge-filter { grid-template-columns: 1fr 1fr; }
}
</style>
