<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'

type Settings = Record<string, any>

const loading = ref(false)
const saving = ref(false)
const exporting = ref(false)
const current = ref<Settings>({})
const form = reactive({
  openclaw_base_url: '',
  primary_model: '',
  deepseek_api_key: '',
  vision_provider: '',
  vision_api_key: '',
  image_model: '',
  image_api_key: '',
  image_workspace_id: '',
})

const PRESET = {
  openclaw_base_url: 'http://openclaw:18789',
  primary_model: 'deepseek/deepseek-v4-flash',
  vision_provider: 'qwen',
  image_model: 'wan2.7-image',
  image_workspace_id: 'ws-jwh57rs47du2vowq',
}

async function load() {
  loading.value = true
  try {
    const response = await hotelApi.integrationSettings()
    current.value = response.data
    form.openclaw_base_url = String(response.data.openclaw_base_url || '')
    form.primary_model = String(response.data.primary_model || '')
    form.vision_provider = String(response.data.vision_provider || '')
    form.image_model = String(response.data.image_model || '')
    form.image_workspace_id = String(response.data.image_workspace_id || '')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { loading.value = false }
}

// 「填入当前预设」以服务器【当前生效】的配置为准，而不是前端写死的常量：
// 网关地址、模型名、生图 workspace 都从 integrationSettings 的当前值回填，
// 前端常量只作为接口异常时的兜底。
function fillPreset() {
  Object.assign(form, {
    openclaw_base_url: current.value.openclaw_base_url || PRESET.openclaw_base_url,
    primary_model: current.value.primary_model || PRESET.primary_model,
    vision_provider: current.value.vision_provider || PRESET.vision_provider,
    image_model: current.value.image_model || PRESET.image_model,
    image_workspace_id: current.value.image_workspace_id || PRESET.image_workspace_id,
  })
  ElMessage.success('已填入当前生效的配置，可在此基础上替换成你自己的 Key')
}

async function save() {
  saving.value = true
  try {
    const payload: Record<string, unknown> = { ...form }
    Object.keys(payload).forEach((key) => { if (!payload[key]) delete payload[key] })
    current.value = (await hotelApi.updateIntegrationSettings(payload)).data
    ElMessage.success('配置已保存，后续调用会使用新的设置')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { saving.value = false }
}

async function exportData() {
  exporting.value = true
  try {
    const response = await hotelApi.exportData()
    const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `stayscape-export-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(link.href)
    ElMessage.success('已导出房态、资源、产品、订单与知识库数据')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { exporting.value = false }
}

onMounted(load)
</script>

<template>
  <div class="settings-page" v-loading="loading">
    <div class="page-head">
      <div><h1>API 设置</h1></div>
      <div class="header-actions">
        <el-button plain @click="fillPreset">填入当前预设</el-button>
        <el-button plain :loading="exporting" @click="exportData">导出数据</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </div>
    </div>

    <section class="panel current-panel">
      <div class="section-title"><h2>当前生效</h2><span>部署默认值，保存后会以你的设置为准</span></div>
      <div class="current-grid">
        <div><span>语言模型</span><b>{{ current.primary_model || '—' }}</b><em>当前 Key：{{ current.reasoning_key_preview }}</em></div>
        <div><span>推理服务</span><b>{{ current.reasoning_provider || '—' }}</b><em>{{ current.configured?.reasoning ? '已配置密钥' : '未配置密钥' }}</em></div>
        <div><span>生图模型</span><b>{{ current.image_model || '—' }}</b><em>{{ current.image_enabled ? '已启用' : '未启用' }} · 当前 Key：{{ current.image_key_preview }}</em></div>
        <div><span>视觉服务</span><b>{{ current.vision_provider || '—' }}</b><em>当前 Key：{{ current.vision_key_preview }}</em></div>
        <div><span>网关地址</span><b>{{ current.openclaw_base_url || '—' }}</b><em>{{ current.agent_provider }}</em></div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title"><h2>修改配置</h2><span>密钥只写入服务器本地配置文件，不会回显明文</span></div>
      <el-form label-position="top" class="settings-form">
        <el-form-item label="网关地址"><el-input v-model="form.openclaw_base_url" placeholder="http://openclaw:18789" /></el-form-item>
        <el-form-item label="语言模型"><el-input v-model="form.primary_model" placeholder="deepseek/deepseek-v4-flash" /></el-form-item>
        <el-form-item label="DeepSeek API Key"><el-input v-model="form.deepseek_api_key" type="password" show-password placeholder="留空表示不修改" /></el-form-item>
        <el-form-item label="生图模型"><el-input v-model="form.image_model" placeholder="wan2.7-image" /></el-form-item>
        <el-form-item label="生图 API Key"><el-input v-model="form.image_api_key" type="password" show-password placeholder="留空表示不修改" /></el-form-item>
        <el-form-item label="生图工作空间"><el-input v-model="form.image_workspace_id" placeholder="ws-xxxx" /></el-form-item>
        <el-form-item label="视觉模型服务"><el-input v-model="form.vision_provider" placeholder="qwen" /></el-form-item>
        <el-form-item label="视觉服务 API Key"><el-input v-model="form.vision_api_key" type="password" show-password placeholder="留空表示不修改" /></el-form-item>
      </el-form>
    </section>

    <section class="panel">
      <div class="section-title"><h2>在别的 Claw 中使用这个 Skill 时</h2></div>
      <ul class="settings-notes">
        <li>ClawHive 接入请进入左侧「Agent 接入」生成专用 Token；它可以查询公开产品并生成待确认候选，但不能发布或改库存。不要把数据库密码、JWT 或 OpenClaw Gateway Token 填入 ClawHive。</li>
        <li>支持本地部署：在服务器上执行 <code>bash scripts/deploy.sh demo</code> 起离线演示，<code>bash scripts/deploy.sh live</code> 起正式链路；两种模式都通过本页读取当前配置。</li>
        <li>API Key 由服务器环境变量管理，页面不会把新输入的 Key 持久化到运行期文件；修改后请更新服务器 .env 并重启对应服务。</li>
        <li>只上传 Skill 包不会带数据库：数据始终来自这里配置的服务地址；点「导出数据」可把房态、资源、产品、订单与知识库导出为 JSON 备份。</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.settings-page { display: grid; gap: 14px; }
.header-actions { display: flex; gap: 8px; }
.current-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.current-grid > div { padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel-soft); }
.current-grid span { display: block; color: var(--muted); font-size: 10px; }
.current-grid b { display: block; margin-top: 5px; font-size: 13px; word-break: break-all; }
.current-grid em { display: block; margin-top: 4px; color: var(--muted); font-size: 10px; font-style: normal; }
.settings-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; margin-top: 12px; }
.settings-notes { display: grid; gap: 7px; margin: 12px 0 0; padding-left: 18px; color: var(--muted); font-size: 12px; line-height: 1.7; }
@media (max-width: 900px) { .current-grid, .settings-form { grid-template-columns: 1fr; } }
</style>
