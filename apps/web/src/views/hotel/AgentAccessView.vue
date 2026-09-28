<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'

type AgentToken = { id: number; name: string; is_active: boolean; created_at: string; last_used_at: string | null }
const loading = ref(false)
const creating = ref(false)
const name = ref('ClawHive 文旅接入')
const tokens = ref<AgentToken[]>([])
const newlyCreated = ref('')

async function load() {
  loading.value = true
  try { tokens.value = (await hotelApi.agentTokens()).data.items }
  catch (error) { ElMessage.error(errorMessage(error)) }
  finally { loading.value = false }
}

async function create() {
  creating.value = true
  newlyCreated.value = ''
  try {
    const response = await hotelApi.createAgentToken(name.value.trim() || 'ClawHive 文旅接入')
    newlyCreated.value = response.data.token
    tokens.value.unshift(response.data.item)
    ElMessage.success('Token 已生成；完整内容只显示这一次')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { creating.value = false }
}

async function copyToken() {
  if (!newlyCreated.value) return
  await navigator.clipboard.writeText(newlyCreated.value)
  ElMessage.success('Token 已复制')
}

async function revoke(row: AgentToken) {
  try {
    await ElMessageBox.confirm(`确定撤销「${row.name}」吗？撤销后 ClawHive 将无法读取产品或生成候选。`, '撤销 Agent Token', { type: 'warning' })
    await hotelApi.revokeAgentToken(row.id)
    row.is_active = false
    ElMessage.success('Token 已撤销')
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error))
  }
}

function format(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN') : '从未使用' }
onMounted(load)
</script>

<template>
  <div class="agent-page" v-loading="loading">
    <div class="page-head"><div><h1>Agent 接入</h1><p>为 ClawHive 或其他 Agent 生成产品查询与候选生成 Token。</p></div></div>
    <section class="panel intro">
      <strong>受控接入权限</strong>
      <span>Token 可以读取当前酒店已发布产品、生成待人工确认候选；不允许发布产品、修改库存、价格或订单。</span>
    </section>
    <section class="panel create-panel">
      <div class="section-title"><h2>生成 Token</h2><span>完整 Token 只在创建成功后显示一次</span></div>
      <div class="create-row"><el-input v-model="name" maxlength="120" placeholder="例如：ClawHive 游客咨询" /><el-button type="primary" :loading="creating" @click="create">创建 Token</el-button></div>
      <div v-if="newlyCreated" class="secret-box"><div><b>请立即复制并保存</b><code>{{ newlyCreated }}</code></div><el-button type="primary" @click="copyToken">复制 Token</el-button></div>
    </section>
    <section class="panel">
      <div class="section-title"><h2>已创建 Token</h2><span>撤销后立即失效</span></div>
      <el-table :data="tokens" empty-text="还没有 Agent Token">
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column label="创建时间" min-width="180"><template #default="{ row }">{{ format(row.created_at) }}</template></el-table-column>
        <el-table-column label="最后使用" min-width="180"><template #default="{ row }">{{ format(row.last_used_at) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '有效' : '已撤销' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button v-if="row.is_active" link type="danger" @click="revoke(row)">撤销</el-button></template></el-table-column>
      </el-table>
    </section>
    <section class="panel howto"><div class="section-title"><h2>ClawHive 使用方式</h2></div><ol><li>在 ClawHive 安装 <code>stayscape-clawhive-chat</code>。</li><li>填写当前 StayScape Server URL 和本页生成的 Agent API Token。</li><li>先调用 <code>GET /api/v1/agent-tools/me</code> 测试连接，再进行产品查询或生成待确认候选。</li></ol></section>
  </div>
</template>

<style scoped>
.agent-page{display:grid;gap:14px}.intro{display:flex;gap:12px;align-items:center;background:#fff8ec}.intro span{color:var(--muted);font-size:12px}.create-row{display:flex;gap:10px;margin-top:12px}.create-row .el-input{max-width:520px}.secret-box{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:14px;padding:12px 14px;border:1px solid #f0b35b;border-radius:10px;background:#fff8e8}.secret-box b{display:block;color:#9a5a00}.secret-box code{display:block;margin-top:6px;word-break:break-all;color:#4b3b20}.howto{color:var(--muted);font-size:12px;line-height:1.8}.howto ol{margin:10px 0 0;padding-left:20px}@media(max-width:700px){.create-row{flex-direction:column}.create-row .el-input{max-width:none}.secret-box{align-items:flex-start;flex-direction:column}}
</style>
