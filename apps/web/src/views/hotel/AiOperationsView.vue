<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { showToast } from 'vant'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'

type AnyRecord = Record<string, any>

const overview = ref<AnyRecord>({})
const conversations = ref<AnyRecord[]>([])
const proposals = ref<AnyRecord[]>([])
const activeConversationId = ref<number | null>(null)
const brief = ref('')
const loading = ref(false)
const submitting = ref(false)

const activeConversation = computed(() => conversations.value.find((item) => Number(item.id) === activeConversationId.value) || null)
const signals = computed(() => Array.isArray(overview.value.operations_insights?.recommendation_signals) ? overview.value.operations_insights.recommendation_signals : [])
const execution = computed(() => activeConversation.value?.last_execution as AnyRecord | undefined)

async function load() {
  loading.value = true
  try {
    const [facts, tasks, pending] = await Promise.all([hotelApi.aiOverview(), hotelApi.aiConversations(), hotelApi.aiProposals('PENDING_CONFIRMATION')])
    overview.value = facts.data
    conversations.value = tasks.data
    proposals.value = pending.data
    if (!activeConversationId.value && conversations.value.length) activeConversationId.value = Number(conversations.value[0].id)
  } catch (error) { showToast(errorMessage(error)) }
  finally { loading.value = false }
}

async function ensureConversation() {
  if (activeConversationId.value) return activeConversationId.value
  const response = await hotelApi.createAiConversation()
  const item = response.data
  conversations.value.unshift(item)
  activeConversationId.value = Number(item.id)
  return activeConversationId.value
}

async function submit() {
  if (!brief.value.trim()) { showToast('请用一句话说明想生成什么产品'); return }
  submitting.value = true
  try {
    const conversationId = await ensureConversation()
    const response = await hotelApi.sendAiMessage(Number(conversationId), brief.value.trim())
    const data = response.data
    const conversation = data.conversation as AnyRecord
    const index = conversations.value.findIndex((item) => Number(item.id) === Number(conversation.id))
    if (index >= 0) conversations.value.splice(index, 1, conversation)
    else conversations.value.unshift(conversation)
    proposals.value = [...(data.proposals as AnyRecord[]), ...proposals.value]
    brief.value = ''
    showToast('候选已生成，等待你确认')
  } catch (error) { showToast(errorMessage(error)) }
  finally { submitting.value = false }
}

async function confirm(proposal: AnyRecord, action: 'DRAFT' | 'PUBLISH') {
  try {
    await hotelApi.confirmAiProposal(Number(proposal.id), action)
    proposals.value = proposals.value.filter((item) => Number(item.id) !== Number(proposal.id))
    showToast(action === 'PUBLISH' ? '产品已发布并完成库存复核' : '已加入产品草稿')
  } catch (error) { showToast(errorMessage(error)) }
}

function label(status: string) {
  return ({ ACTIVE: '已核验', VERIFY_REQUIRED: '需确认', CHECKED: '已查询', PASSED: '已通过', PENDING: '待确认', NONE: '未降级' } as Record<string, string>)[status] || status
}

function toolName(tool: unknown) {
  if (typeof tool === 'string') return tool
  return String((tool as AnyRecord)?.name || 'StayScape 服务')
}

function toolKind(tool: unknown) {
  if (typeof tool === 'string') return ''
  return String((tool as AnyRecord)?.kind || '')
}

function durationText(value: unknown) {
  const milliseconds = Number(value || 0)
  if (!Number.isFinite(milliseconds) || milliseconds <= 0) return '已记录'
  return milliseconds >= 1000 ? `${(milliseconds / 1000).toFixed(1)} 秒` : `${milliseconds} ms`
}

onMounted(load)
</script>

<template>
  <main class="ai-operations">
    <header class="page-head"><div><span>酒店 AI 运营</span><h1>把一句经营想法变成待确认产品</h1><p>OpenClaw 负责编排与 Skill 调用；库存、价格、时间和发布资格均由系统重新校验。</p></div><el-button :loading="loading" @click="load">刷新事实</el-button></header>

    <section class="fact-strip">
      <article><span>近 14 天已确认</span><strong>{{ overview.operations_insights?.confirmed_order_count ?? 0 }} 单</strong><small>仅使用汇总经营数据</small></article>
      <article><span>天气参考</span><strong>{{ overview.weather?.scenario === 'RAIN' ? '雨天倾向' : overview.weather?.scenario === 'SUNNY' ? '晴天倾向' : '天气待确认/多云' }}</strong><small>{{ overview.weather?.advisory || '读取中' }}</small></article>
      <article><span>文旅知识</span><strong>{{ (overview.knowledge || []).length }} 条</strong><small>每条均保留来源与核验状态</small></article>
      <article><span>待人工确认</span><strong>{{ overview.pending_confirmation_count ?? 0 }} 个</strong><small>确认前不会出现在游客端</small></article>
    </section>

    <section class="workspace-grid">
      <article class="task-panel">
        <div class="section-head"><div><span>自然语言任务</span><h2>告诉我你想卖什么</h2></div><el-select v-model="activeConversationId" placeholder="新建任务" clearable><el-option v-for="item in conversations" :key="item.id" :label="item.title" :value="Number(item.id)" /></el-select></div>
        <textarea v-model="brief" placeholder="例如：周六还剩不少亲子房，做 3 套适合 6—10 岁孩子的杭州博物馆与科学探索产品，预算 700 元左右。" @keydown.ctrl.enter.prevent="submit" />
        <div class="task-actions"><span>Ctrl + Enter 生成候选</span><el-button type="primary" :loading="submitting" @click="submit">生成待确认候选</el-button></div>
        <div v-if="activeConversation?.messages?.length" class="task-messages"><p v-for="(message, index) in activeConversation.messages.slice(-6)" :key="index" :class="message.role"><b>{{ message.role === 'user' ? '你' : '助手' }}</b>{{ message.content }}</p></div>
      </article>

      <article class="audit-panel"><div class="section-head"><div><span>可审计输入</span><h2>为什么这样推荐</h2></div></div><ul><li v-for="(signal, index) in signals" :key="index"><i />{{ signal.message }}</li></ul><div v-if="execution" class="execution-record"><span>本次执行记录</span><div class="execution-main"><b>{{ execution.agent || 'stayscape-main' }}</b><em>{{ execution.skill || 'stayscape-product-generator' }}</em><small>{{ durationText(execution.duration_ms) }} · {{ execution.fallback_used ? '发生降级' : '未发生降级' }}</small></div><div class="execution-tools"><span v-for="(tool, index) in execution.tool_calls || []" :key="index"><b>{{ toolName(tool) }}</b>{{ toolKind(tool) ? ` · ${toolKind(tool)}` : '' }}</span></div><p>{{ execution.used_knowledge ? `已查询 ${execution.used_knowledge} 条文旅知识` : '本次未命中文旅知识' }}{{ execution.used_weather ? '，已读取天气信息。' : '，天气信息需确认。' }}</p></div><p class="audit-note">文旅知识中标记“需确认”的开放时间、地址和预约说明不会被当作可售承诺；这里只展示执行步骤，不展示模型内部推理。</p></article>
    </section>

    <section class="proposal-section"><div class="section-head"><div><span>人工确认队列</span><h2>候选产品</h2></div><small>发布时再次检查实时库存</small></div><div v-if="proposals.length" class="proposal-grid"><article v-for="proposal in proposals" :key="proposal.id" class="proposal-card"><header><div><span>候选 #{{ proposal.id }}</span><h3>{{ proposal.product?.product_name }}</h3><p>{{ proposal.product?.theme }} · {{ proposal.product?.target_date }}</p></div><b>¥{{ proposal.product?.suggested_price }}</b></header><div class="proposal-meta"><span v-for="step in proposal.execution_steps?.slice(0, 5) || []" :key="`${step.name}-${step.at}`" :class="step.status"><i />{{ step.name }} · {{ label(step.status) }}</span></div><p class="proposal-reason">{{ proposal.product?.recommendation_reason }}</p><footer><el-button @click="confirm(proposal, 'DRAFT')">加入草稿</el-button><el-button type="primary" @click="confirm(proposal, 'PUBLISH')">确认发布</el-button></footer></article></div><div v-else class="empty-state">暂无待确认候选。生成后，先由你确认，再进入草稿或游客端。</div></section>
  </main>
</template>

<style scoped>
.ai-operations{display:grid;gap:14px}.page-head,.section-head{display:flex;align-items:end;justify-content:space-between;gap:14px}.page-head>div>span,.section-head span{color:var(--muted);font-size:10px;letter-spacing:.09em}.page-head h1{margin:5px 0 0;font-size:25px;letter-spacing:-.7px}.page-head p{max-width:680px;margin:7px 0 0;color:var(--muted);font-size:12px;line-height:1.65}.fact-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.fact-strip article,.task-panel,.audit-panel,.proposal-card{border:1px solid var(--line);border-radius:11px;background:var(--paper)}.fact-strip article{display:grid;gap:4px;padding:12px}.fact-strip span,.fact-strip small{color:var(--muted);font-size:10px}.fact-strip strong{font-family:var(--font-mono);font-size:16px}.workspace-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(260px,.65fr);gap:10px}.task-panel,.audit-panel{padding:14px}.section-head h2{margin:4px 0 0;font-size:16px}.section-head small{color:var(--muted);font-size:10px}.task-panel textarea{display:block;box-sizing:border-box;width:100%;min-height:104px;margin-top:13px;padding:10px;border:1px solid var(--line);border-radius:8px;resize:vertical;background:var(--panel-soft);color:var(--ink);font:13px/1.65 var(--font-sans)}.task-actions{display:flex;align-items:center;justify-content:space-between;margin-top:9px;color:var(--muted);font-size:10px}.task-messages{display:grid;gap:5px;margin-top:12px;padding-top:10px;border-top:1px solid var(--line)}.task-messages p{margin:0;padding:7px 8px;border-radius:7px;background:var(--panel-soft);color:var(--muted);font-size:11px;line-height:1.55}.task-messages p.assistant{background:#f0f5f2;color:var(--ink)}.task-messages b{margin-right:7px;font-size:10px}.audit-panel ul{display:grid;gap:8px;margin:14px 0;padding:0;list-style:none}.audit-panel li{display:flex;gap:7px;color:var(--ink);font-size:11px;line-height:1.5}.audit-panel li i,.proposal-meta i{width:5px;height:5px;margin-top:6px;border-radius:50%;background:#55977b;flex:0 0 auto}.audit-note{margin:12px 0 0;padding-top:10px;border-top:1px solid var(--line);color:var(--muted);font-size:10px;line-height:1.6}.proposal-section{padding:14px;border:1px solid var(--line);border-radius:11px;background:var(--paper)}.proposal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:12px}.proposal-card{overflow:hidden}.proposal-card header{display:flex;justify-content:space-between;gap:8px;padding:12px;border-bottom:1px solid var(--line)}.proposal-card header span,.proposal-card header p{color:var(--muted);font-size:10px}.proposal-card h3{margin:4px 0;font-size:14px}.proposal-card header p{margin:0}.proposal-card header b{font-family:var(--font-mono);font-size:15px;white-space:nowrap}.proposal-meta{display:flex;flex-wrap:wrap;gap:5px;padding:9px 11px}.proposal-meta span{display:inline-flex;align-items:center;gap:4px;padding:3px 5px;border-radius:999px;background:var(--panel-soft);color:var(--muted);font-size:9px}.proposal-meta .VERIFY_REQUIRED i{background:#c78b4a}.proposal-meta .PENDING i{background:#9a6b42}.proposal-reason{min-height:32px;margin:0;padding:0 11px 11px;color:var(--muted);font-size:11px;line-height:1.55}.proposal-card footer{display:flex;justify-content:flex-end;gap:7px;padding:9px 11px;border-top:1px solid var(--line)}.empty-state{padding:30px;color:var(--muted);font-size:12px;text-align:center}@media(max-width:820px){.fact-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.workspace-grid,.proposal-grid{grid-template-columns:1fr}.page-head{align-items:start}.page-head h1{font-size:22px}}
</style>

<style scoped>
.execution-record{display:grid;gap:7px;margin-top:11px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--panel-soft)}
.execution-record>span{color:var(--muted);font-size:9px;letter-spacing:.08em}
.execution-main{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.execution-main b{font-family:var(--font-mono);font-size:11px}
.execution-main em{padding:2px 5px;border-radius:4px;background:var(--paper);font-family:var(--font-mono);font-size:9px;font-style:normal}
.execution-main small,.execution-record p{margin:0;color:var(--muted);font-size:10px;line-height:1.55}
.execution-tools{display:flex;flex-wrap:wrap;gap:4px}
.execution-tools span{padding:3px 5px;border:1px solid var(--line);border-radius:999px;background:var(--paper);color:var(--muted);font-size:9px}
.execution-tools b{color:var(--ink);font-weight:600}
</style>
