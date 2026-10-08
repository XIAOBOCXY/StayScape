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
    <section class="panel intro">
      <div class="intro__mark">⌘</div><div class="intro__copy"><strong>安全连接 StayScape</strong><span>此接入仅开放产品查询与待确认候选生成。发布产品、调整库存、改价和处理订单仍在工作台完成。</span></div>
      <div class="permission-tags"><el-tag type="success" effect="light">读取已发布产品</el-tag><el-tag type="success" effect="light">生成待确认候选</el-tag><el-tag type="info" effect="light">不能直接发布或改库存</el-tag></div>
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
    <section class="panel howto"><div class="section-title"><div><span class="section-kicker">CLAWHIVE</span><h2>连接步骤</h2></div><span>连接后读取实时库存与资源；离线时按你提供的日期和资源规划，不虚构库存。</span></div><div class="agent-steps"><article><i>1</i><div><b>安装 Skill</b><p>在 ClawHive 中安装 <code>stayscape-clawhive-chat</code>。</p></div></article><article><i>2</i><div><b>填写连接信息</b><p>配置本页生成的 Agent API Token 与 StayScape Server URL。Token 只在创建时显示一次。</p></div></article><article><i>3</i><div><b>验证后开始使用</b><p>先调用 <code>GET /api/v1/agent-tools/me</code> 确认连接，再查询在售产品或生成待人工确认候选。</p></div></article></div><p class="agent-offline-note">尚未配置连接时，Skill 仍可依据用户提供的日期、人数和可用资源整理产品草案；库存、价格、营业时间等未提供的信息会标注为待确认。</p></section>
  </div>
</template>

<style scoped>
.agent-page{display:grid;gap:12px;min-width:0}.intro{display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:13px;padding:16px 18px;background:#f4f8f5;border-color:#dfe9e2}.intro__mark{display:grid;width:38px;height:38px;place-items:center;border-radius:10px;background:#e2eee6;color:#386149;font-size:19px}.intro__copy{display:grid;gap:4px;min-width:0}.intro__copy strong{color:#30483a;font-size:14px}.intro__copy span{color:#627269;font-size:12px;line-height:1.6}.permission-tags{display:flex;justify-content:flex-end;gap:6px;flex-wrap:wrap}.permission-tags :deep(.el-tag){height:25px;border-radius:7px}.create-panel,.howto{padding:16px 18px}.create-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;margin-top:12px}.create-row :deep(.el-input__wrapper){min-height:38px;border-radius:8px}.secret-box{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;padding:12px 14px;border:1px solid #cde0d0;border-radius:9px;background:#f1f8f1}.secret-box>div{display:grid;gap:6px;min-width:0}.secret-box code{overflow-wrap:anywhere;color:#285b3a}.agent-page :deep(.el-table){border:1px solid #e5ebe6;border-radius:9px;overflow:hidden}.agent-page :deep(.el-table th.el-table__cell){background:#f4f7f5;color:#53675a}.agent-page :deep(.el-table td.el-table__cell){padding-block:9px}.howto .section-title{align-items:flex-end;margin-bottom:14px}.howto .section-title h2{margin:4px 0 0;color:#30483a;font-size:16px}.howto .section-title>span{max-width:480px;color:#738078;font-size:11px;line-height:1.55;text-align:right}.agent-steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.agent-steps article{display:flex;gap:10px;min-width:0;padding:13px;border:1px solid #e5ebe6;border-radius:9px;background:#fff}.agent-steps i{display:grid;flex:0 0 24px;width:24px;height:24px;place-items:center;border-radius:7px;background:#e9f2eb;color:#355a43;font-size:12px;font-style:normal;font-weight:700}.agent-steps b{color:#344a3c;font-size:12px}.agent-steps p{margin:5px 0 0;color:#65736a;font-size:11px;line-height:1.65}.agent-steps code{padding:2px 4px;border-radius:4px;background:#f2f5f2;color:#365b46;font-size:10px;overflow-wrap:anywhere}.agent-offline-note{margin:11px 0 0;padding:9px 11px;border-radius:7px;background:#f7f8f6;color:#68756c;font-size:11px;line-height:1.6}@media(max-width:820px){.intro{grid-template-columns:38px minmax(0,1fr)}.permission-tags{grid-column:2;justify-content:flex-start}.agent-steps{grid-template-columns:1fr}.howto .section-title{align-items:flex-start;flex-direction:column}.howto .section-title>span{text-align:left}}@media(max-width:520px){.create-row{grid-template-columns:1fr}.secret-box{align-items:flex-start;flex-direction:column}.intro,.create-panel,.howto{padding:13px}}
</style>
