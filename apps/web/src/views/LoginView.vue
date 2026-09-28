<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { errorMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
// Preset accounts shipped with the demo dataset; the hotel and the partner
// merchant share one password so the reviewer can switch roles quickly.
// Partner resources are maintained inside the hotel workbench (资源池页面),
// so the standalone merchant console is no longer exposed for sign-in.
const presetAccounts = [
  { label: '酒店经营端', username: 'hotel_demo', password: 'StayScape123!' },
]

async function useAccount(account: { username: string; password: string }) {
  form.username = account.username
  form.password = account.password
  // One click signs in with the preset account: browsers may clear a
  // programmatically assigned password field, so the submit uses the state.
  await submit()
}

async function submit() {
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/hotel/dashboard'
    router.push(redirect)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <span class="brand-mark" aria-label="杭州旅居"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></span>
        <div><strong>StayScape</strong><small>余宿成景 · 文旅产品智能运营</small></div>
      </div>
      <h1>经营者登录</h1>
      <p>进入库存驱动的主题住宿产品工作台</p>
      <el-form @submit.prevent="submit">
        <el-form-item label="账号"><el-input v-model="form.username" size="large" placeholder="请输入经营者账号" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" size="large" show-password type="password" placeholder="请输入密码" @keyup.enter="submit" /></el-form-item>
        <el-button type="primary" size="large" style="width:100%" :loading="loading" @click="submit">登录工作台</el-button>
      </el-form>
      <div class="preset-accounts">
        <span class="preset-accounts__title">预设账号（点击可直接登录）</span>
        <button v-for="account in presetAccounts" :key="account.username" type="button" @click="useAccount(account)">
          <b>{{ account.label }}</b>
          <span>{{ account.username }}</span>
          <em>{{ account.password }}</em>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.preset-accounts { display: grid; gap: 7px; margin-top: 18px; padding-top: 15px; border-top: 1px dashed var(--line); }
.preset-accounts__title { color: var(--muted); font-size: 10px; letter-spacing: .08em; }
.preset-accounts button { display: grid; grid-template-columns: auto 1fr auto; gap: 10px; align-items: center; padding: 9px 12px; border: 1px solid var(--line); border-radius: 9px; background: var(--panel-soft); color: var(--ink); font-size: 12px; text-align: left; cursor: pointer; }
.preset-accounts button:hover { border-color: #7bb8a8; background: #f2f9f5; }
.preset-accounts b { font-size: 11px; }
.preset-accounts span { color: var(--muted); font-family: var(--font-mono); font-size: 11px; }
.preset-accounts em { color: var(--teal-dark); font-family: var(--font-mono); font-size: 11px; font-style: normal; }
</style>
