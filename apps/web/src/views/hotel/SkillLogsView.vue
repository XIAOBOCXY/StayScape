<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
const items = ref<Array<Record<string, any>>>([]); const loading = ref(false); const selected = ref<Record<string, any> | null>(null); const logDialog = ref(false)
async function load() { loading.value = true; try { items.value = (await hotelApi.skillLogs()).data } catch (e) { errorMessage(e) } finally { loading.value = false } }
function selectLog(row: Record<string, any>) { selected.value = row; logDialog.value = true }
onMounted(load)
</script>
<template><div class="page-head"><div><div class="eyebrow">AGENT OBSERVABILITY</div><h1>Skill调用日志</h1><p>每次调用都有 trace_id、状态、重试次数和Schema校验结果，便于比赛演示时审计AI边界。</p></div><el-button plain @click="load">刷新</el-button></div><div class="panel table-wrap"><el-table v-loading="loading" :data="items" @row-click="selectLog"><el-table-column prop="trace_id" label="Trace ID" min-width="230" /><el-table-column prop="skill_name" label="Skill" min-width="220" /><el-table-column prop="business_scene" label="场景" width="150" /><el-table-column label="状态" width="120"><template #default="{row}"><StatusTag :status="row.call_status === 'SUCCESS' ? 'AVAILABLE' : row.call_status === 'FALLBACK' ? 'LOW_STOCK' : 'PAUSED'" /></template></el-table-column><el-table-column prop="retry_count" label="重试" width="70" /><el-table-column prop="duration_ms" label="耗时(ms)" width="95" /><el-table-column prop="created_at" label="调用时间" width="160" /></el-table><div v-if="!loading && !items.length" class="empty-state">生成产品或游客推荐后会产生Skill日志</div></div><el-dialog v-model="logDialog" title="调用详情" width="720px"><pre v-if="selected" class="json-preview">{{ JSON.stringify(selected, null, 2) }}</pre></el-dialog></template>
