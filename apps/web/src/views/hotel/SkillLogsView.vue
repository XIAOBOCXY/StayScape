<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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
function fallbackState(row: Record<string, any>) {
  if (row.fallback_used) return '已启用降级'
  return row.call_status === 'SUCCESS' ? '正式调用' : '未启用降级'
}
function dateText(value: unknown) { return value ? String(value).replace('T', ' ').slice(0, 19) : '—' }
function failureReason(row: Record<string, any>) {
  const code = String(row.error_code || '')
  if (code === 'AGENT_FORMAT_ERROR') return '助手返回内容未通过格式校验，系统未能读取推荐结果。'
  if (code.includes('TIMEOUT')) return '助手调用超时，暂未返回可用结果。'
  if (code) return '本次调用未完成，错误代码：' + code
  return row.call_status === 'SUCCESS' ? '无' : '调用未完成，暂无更多错误详情。'
}
const rawJsonBlock = ref<HTMLElement | null>(null)
function legacyCopy(text: string) {
  const field = document.createElement('textarea')
  field.value = text
  field.setAttribute('readonly', '')
  field.style.position = 'fixed'
  field.style.left = '-9999px'
  document.body.appendChild(field)
  try {
    field.focus()
    field.select()
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    field.remove()
  }
}
function selectRawJson() {
  const block = rawJsonBlock.value
  if (!block) return false
  const selection = window.getSelection()
  if (!selection) return false
  const range = document.createRange()
  range.selectNodeContents(block)
  selection.removeAllRanges()
  selection.addRange(range)
  return true
}
const rawJson = computed(() => (selected.value ? JSON.stringify(selected.value, null, 2) : ''))
async function copyRaw() {
  if (!rawJson.value) return
  try {
    if (window.isSecureContext && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(rawJson.value)
      ElMessage.success('已复制原始记录')
      return
    }
  } catch {
    // Embedded browsers can expose the Clipboard API but reject writes.
  }
  if (legacyCopy(rawJson.value)) {
    ElMessage.success('已复制原始记录')
    return
  }
  if (selectRawJson()) ElMessage.warning('浏览器限制自动复制，原始 JSON 已选中，请按 Ctrl+C 复制')
  else ElMessage.warning('复制失败，请在原始 JSON 区域手动选择并复制')
}
onMounted(load)
</script>

<template>
  <div v-toolbar class="header-actions"><el-button plain :loading="loading" @click="load">刷新</el-button></div>
  <div v-if="diagnostics" class="agent-diagnostic-panel"><div><span class="eyebrow">当前服务</span><strong :class="diagnostics.provider === 'OPENCLAW' ? 'live' : 'mock'">{{ diagnostics.provider === 'OPENCLAW' ? '正式服务' : '演示服务' }}</strong><small>{{ diagnostics.transport }} · {{ diagnostics.agent_id || '本地执行器' }}</small></div><div><span class="eyebrow">网关连接</span><strong>{{ diagnostics.gateway?.reachable ? '已连接' : diagnostics.gateway?.configured ? '未连接' : '未配置' }}</strong><small v-if="diagnostics.gateway?.error">{{ diagnostics.gateway.error }}</small></div><div class="diagnostic-skills"><span class="eyebrow">已安装能力</span><div><el-tag v-for="skill in diagnostics.skills" :key="skill.name" :type="skill.configured ? 'success' : 'info'" effect="plain">{{ skill.name }} · v{{ skill.version }}</el-tag></div></div></div>
  <div class="panel table-wrap"><el-table v-loading="loading" :data="items" @row-click="selectLog"><el-table-column prop="trace_id" label="调用标识" min-width="210" /><el-table-column label="服务方" width="105"><template #default="{row}"><el-tag :type="row.provider === 'OPENCLAW' ? 'success' : 'warning'" effect="plain">{{ row.provider === 'OPENCLAW' ? 'OpenClaw' : '演示' }}</el-tag></template></el-table-column><el-table-column prop="skill_name" label="能力" min-width="190" /><el-table-column prop="transport" label="调用路径" width="120" /><el-table-column label="结果" width="130"><template #default="{row}"><el-tag :type="row.call_status === 'SUCCESS' ? 'success' : row.call_status === 'FALLBACK' ? 'warning' : 'danger'" effect="plain">{{ callState(row) }}</el-tag></template></el-table-column><el-table-column label="执行方式" width="105"><template #default="{row}"><span :class="row.fallback_used ? 'warning-text' : 'success-text'">{{ fallbackState(row) }}</span></template></el-table-column><el-table-column prop="retry_count" label="重试" width="65" /><el-table-column prop="duration_ms" label="耗时" width="90"><template #default="{row}">{{ row.duration_ms }} ms</template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">生成产品或游客推荐后会出现调用记录。</div></div>
  <el-dialog v-model="logDialog" title="调用详情" width="min(94vw, 720px)">
    <div v-if="selected" class="log-detail">
      <div class="log-detail__head">
        <div><span>调用标识</span><strong>{{ selected.trace_id }}</strong></div>
        <el-tag :type="selected.call_status === 'SUCCESS' ? 'success' : selected.call_status === 'FALLBACK' ? 'warning' : 'danger'" effect="light">{{ callState(selected) }}</el-tag>
      </div>
      <div class="log-detail__grid">
        <div><span>服务方</span><b>{{ selected.provider === 'OPENCLAW' ? '正式服务' : '演示服务' }}</b></div>
        <div><span>能力</span><b>{{ selected.skill_name }}</b></div>
        <div><span>调用路径</span><b>{{ selected.transport }}</b></div>
        <div><span>执行方式</span><b>{{ fallbackState(selected) }}</b></div>
        <div><span>耗时</span><b>{{ selected.duration_ms }} 毫秒</b></div>
        <div><span>重试</span><b>{{ selected.retry_count ?? 0 }} 次</b></div>
        <div><span>记录时间</span><b>{{ dateText(selected.created_at) }}</b></div>
        <div><span>失败原因</span><b>{{ failureReason(selected) }}</b></div>
      </div>
      <div class="log-detail__raw">
        <div class="log-detail__raw-head"><span>原始记录（用于核对真实调用与耗时）</span><el-button size="small" plain @click="copyRaw">复制 JSON</el-button></div>
        <pre ref="rawJsonBlock">{{ rawJson }}</pre>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.agent-diagnostic-panel{display:grid;grid-template-columns:1fr 1fr 2fr;gap:1px;margin:0 0 18px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--line)}.agent-diagnostic-panel>div{min-height:92px;padding:16px;background:var(--paper);color:var(--ink)}.agent-diagnostic-panel .eyebrow{display:block;color:var(--muted);font-size:10px}.agent-diagnostic-panel strong{display:block;margin:9px 0 5px;font:650 19px var(--font-sans)}.agent-diagnostic-panel strong.live{color:#47675e}.agent-diagnostic-panel strong.mock{color:#9a7135}.agent-diagnostic-panel small{display:block;color:var(--muted);font-family:var(--font-mono);font-size:10px}.diagnostic-skills>div{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}.success-text{color:#40665b;font-size:11px;font-weight:600}@media(max-width:900px){.agent-diagnostic-panel{grid-template-columns:1fr 1fr}.diagnostic-skills{grid-column:1/-1}}@media(max-width:620px){.agent-diagnostic-panel{grid-template-columns:1fr}}
</style>


<style scoped>
.log-detail { display: grid; gap: 14px; }
.log-detail__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.log-detail__head span { display: block; color: var(--muted); font-size: 10px; }
.log-detail__head strong { display: block; margin-top: 4px; font-family: var(--font-mono); font-size: 13px; word-break: break-all; }
.log-detail__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.log-detail__grid > div { min-width: 0; padding: 10px 12px; border: 1px solid var(--line); border-radius: 9px; background: var(--panel-soft); }
.log-detail__grid span { display: block; color: var(--muted); font-size: 10px; }
.log-detail__grid b { display: block; margin-top: 5px; font-size: 12px; font-weight: 600; word-break: break-word; }
.log-detail__raw-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.log-detail__raw-head span { color: var(--muted); font-size: 11px; }
.log-detail__raw pre { max-height: 320px; overflow: auto; margin: 10px 0 0; padding: 12px; border: 1px solid var(--line); border-radius: 9px; background: #f8faf9; color: #42524c; font-size: 11px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
@media (max-width: 620px) { .log-detail__grid { grid-template-columns: 1fr; } }
</style>
