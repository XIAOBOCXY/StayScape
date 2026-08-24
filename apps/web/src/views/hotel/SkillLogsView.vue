<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import { ElMessage } from 'element-plus'

const items = ref<Array<Record<string, any>>>([])
const diagnostics = ref<Record<string, any> | null>(null)
const loading = ref(false)
const selected = ref<Record<string, any> | null>(null)
const logDialog = ref(false)
async function load() { loading.value = true; try { const [logs, info] = await Promise.all([hotelApi.skillLogs(), hotelApi.agentDiagnostics()]); items.value = logs.data; diagnostics.value = info.data } catch (e) { ElMessage.error(errorMessage(e)) } finally { loading.value = false } }
function selectLog(row: Record<string, any>) { selected.value = row; logDialog.value = true }
function callState(row: Record<string, any>) { return row.call_status === 'SUCCESS' ? '调用成功' : row.call_status === 'FALLBACK' ? '已启用保护性降级' : '调用未完成' }
function fallbackState(row: Record<string, any>) { return row.fallback_used ? '已降级' : '正式调用' }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">运行状态</div><h1>智能调用日志</h1><p>这里用于核对正式服务、能力调用和耗时；“正式调用”表示没有使用演示降级结果。</p></div><el-button plain :loading="loading" @click="load">刷新</el-button></div>
  <div v-if="diagnostics" class="agent-diagnostic-panel"><div><span class="eyebrow">当前服务</span><strong :class="diagnostics.provider === 'OPENCLAW' ? 'live' : 'mock'">{{ diagnostics.provider === 'OPENCLAW' ? '正式服务' : '演示服务' }}</strong><small>{{ diagnostics.transport }} · {{ diagnostics.agent_id || '本地执行器' }}</small></div><div><span class="eyebrow">网关连接</span><strong>{{ diagnostics.gateway?.reachable ? '已连接' : diagnostics.gateway?.configured ? '未连接' : '未配置' }}</strong><small v-if="diagnostics.gateway?.error">{{ diagnostics.gateway.error }}</small></div><div class="diagnostic-skills"><span class="eyebrow">已安装能力</span><div><el-tag v-for="skill in diagnostics.skills" :key="skill.name" :type="skill.configured ? 'success' : 'info'" effect="plain">{{ skill.name }} · v{{ skill.version }}</el-tag></div></div></div>
  <div class="panel table-wrap"><el-table v-loading="loading" :data="items" @row-click="selectLog"><el-table-column prop="trace_id" label="调用标识" min-width="210" /><el-table-column label="服务方" width="105"><template #default="{row}"><el-tag :type="row.provider === 'OPENCLAW' ? 'success' : 'warning'" effect="plain">{{ row.provider === 'OPENCLAW' ? 'OpenClaw' : '演示' }}</el-tag></template></el-table-column><el-table-column prop="skill_name" label="能力" min-width="190" /><el-table-column prop="transport" label="调用路径" width="120" /><el-table-column label="结果" width="130"><template #default="{row}"><el-tag :type="row.call_status === 'SUCCESS' ? 'success' : row.call_status === 'FALLBACK' ? 'warning' : 'danger'" effect="plain">{{ callState(row) }}</el-tag></template></el-table-column><el-table-column label="执行方式" width="105"><template #default="{row}"><span :class="row.fallback_used ? 'warning-text' : 'success-text'">{{ fallbackState(row) }}</span></template></el-table-column><el-table-column prop="retry_count" label="重试" width="65" /><el-table-column prop="duration_ms" label="耗时" width="90"><template #default="{row}">{{ row.duration_ms }} ms</template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">生成产品或游客推荐后会出现调用记录。</div></div>
  <el-dialog v-model="logDialog" title="调用详情" width="720px"><pre v-if="selected" class="json-preview">{{ JSON.stringify(selected, null, 2) }}</pre></el-dialog>
</template>

<style scoped>
.agent-diagnostic-panel{display:grid;grid-template-columns:1fr 1fr 2fr;gap:1px;margin:0 0 18px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--line)}.agent-diagnostic-panel>div{min-height:92px;padding:16px;background:var(--paper);color:var(--ink)}.agent-diagnostic-panel .eyebrow{display:block;color:var(--muted);font-size:10px}.agent-diagnostic-panel strong{display:block;margin:9px 0 5px;font:650 19px var(--font-sans)}.agent-diagnostic-panel strong.live{color:#47675e}.agent-diagnostic-panel strong.mock{color:#9a7135}.agent-diagnostic-panel small{display:block;color:var(--muted);font-family:var(--font-mono);font-size:10px}.diagnostic-skills>div{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}.success-text{color:#40665b;font-size:11px;font-weight:600}@media(max-width:900px){.agent-diagnostic-panel{grid-template-columns:1fr 1fr}.diagnostic-skills{grid-column:1/-1}}@media(max-width:620px){.agent-diagnostic-panel{grid-template-columns:1fr}}
</style>
