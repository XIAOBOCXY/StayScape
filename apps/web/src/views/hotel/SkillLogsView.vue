<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import { ElMessage } from 'element-plus'
import StatusTag from '../../components/StatusTag.vue'

const items = ref<Array<Record<string, any>>>([])
const diagnostics = ref<Record<string, any> | null>(null)
const loading = ref(false)
const selected = ref<Record<string, any> | null>(null)
const logDialog = ref(false)
async function load() { loading.value = true; try { const [logs, info] = await Promise.all([hotelApi.skillLogs(), hotelApi.agentDiagnostics()]); items.value = logs.data; diagnostics.value = info.data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
function selectLog(row: Record<string, any>) { selected.value = row; logDialog.value = true }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">AGENT OBSERVABILITY</div><h1>Skill调用日志</h1><p>每次调用都有 Provider、Skill、trace_id、重试次数和 Schema 校验结果，Mock 降级不会伪装成真实 ClawHive 调用。</p></div><el-button plain :loading="loading" @click="load">刷新诊断</el-button></div>
  <div v-if="diagnostics" class="agent-diagnostic-panel"><div><span class="eyebrow">CURRENT PROVIDER</span><strong :class="['OPENCLAW', 'CLAWHIVE'].includes(diagnostics.provider) ? 'live' : 'mock'">{{ diagnostics.provider }}</strong><small>{{ diagnostics.transport }} · agent={{ diagnostics.agent_id || 'local fallback' }}</small></div><div><span class="eyebrow">GATEWAY</span><strong>{{ diagnostics.gateway?.reachable ? 'CONNECTED' : diagnostics.gateway?.configured ? 'UNREACHABLE' : 'NOT CONFIGURED' }}</strong><small v-if="diagnostics.gateway?.error">{{ diagnostics.gateway.error }}</small></div><div class="diagnostic-skills"><span class="eyebrow">INSTALLED SKILLS</span><div><el-tag v-for="skill in diagnostics.skills" :key="skill.name" :type="skill.configured ? 'success' : 'info'" effect="plain">{{ skill.name }} · v{{ skill.version }}</el-tag></div></div></div>
  <div class="panel table-wrap"><el-table v-loading="loading" :data="items" @row-click="selectLog"><el-table-column prop="trace_id" label="Trace ID" min-width="230" /><el-table-column label="Provider" width="115"><template #default="{row}"><el-tag :type="['OPENCLAW', 'CLAWHIVE'].includes(row.provider) ? 'success' : 'warning'" effect="dark">{{ row.provider || 'MOCK' }}</el-tag></template></el-table-column><el-table-column prop="skill_name" label="Skill" min-width="220" /><el-table-column prop="transport" label="Transport" width="120" /><el-table-column prop="agent_id" label="Agent" min-width="130" /><el-table-column label="状态" width="120"><template #default="{row}"><StatusTag :status="row.call_status === 'SUCCESS' ? 'AVAILABLE' : row.call_status === 'FALLBACK' ? 'LOW_STOCK' : 'PAUSED'" /></template></el-table-column><el-table-column label="Fallback" width="90"><template #default="{row}">{{ row.fallback_used ? 'true' : 'false' }}</template></el-table-column><el-table-column prop="retry_count" label="重试" width="70" /><el-table-column prop="duration_ms" label="耗时(ms)" width="95" /></el-table><div v-if="!loading && !items.length" class="empty-state">生成产品或游客推荐后会产生 Skill 日志</div></div>
  <el-dialog v-model="logDialog" title="调用详情" width="720px"><pre v-if="selected" class="json-preview">{{ JSON.stringify(selected, null, 2) }}</pre></el-dialog>
</template>

<style scoped>
.agent-diagnostic-panel{display:grid;grid-template-columns:1fr 1fr 2fr;gap:1px;margin:0 0 18px;background:#cbded5;border:1px solid #cbded5}.agent-diagnostic-panel>div{min-height:96px;padding:17px;background:#173f39;color:#eef8f3}.agent-diagnostic-panel .eyebrow{display:block;color:#a8c8bd;font-size:10px}.agent-diagnostic-panel strong{display:block;margin:9px 0 5px;font:24px Georgia,serif}.agent-diagnostic-panel strong.live{color:#d6edbd}.agent-diagnostic-panel strong.mock{color:#f3cb82}.agent-diagnostic-panel small{display:block;color:#b8d5cb;font-size:11px}.diagnostic-skills>div{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}@media(max-width:900px){.agent-diagnostic-panel{grid-template-columns:1fr 1fr}.diagnostic-skills{grid-column:1/-1}}@media(max-width:620px){.agent-diagnostic-panel{grid-template-columns:1fr}}
</style>
