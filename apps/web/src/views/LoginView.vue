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
const form = reactive({ username: 'hotel_demo', password: 'StayScape123!' })
async function submit() {
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : auth.role === 'MERCHANT' ? '/merchant/dashboard' : '/hotel/dashboard'
    router.push(redirect)
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { loading.value = false }
}
</script>

<template>
  <div class="login-page"><div class="login-card"><div class="brand"><div class="brand-mark">S</div><div><strong>StayScape</strong><small>余宿成景 · 文旅产品智能运营</small></div></div><h1>经营者登录</h1><p>进入库存驱动的主题住宿产品工作台</p><el-form @submit.prevent="submit"><el-form-item label="账号"><el-input v-model="form.username" size="large" placeholder="hotel_demo" /></el-form-item><el-form-item label="密码"><el-input v-model="form.password" size="large" show-password type="password" @keyup.enter="submit" /></el-form-item><el-button type="primary" size="large" style="width:100%" :loading="loading" @click="submit">登录工作台</el-button></el-form><div class="login-hints">演示账号：hotel_demo / StayScape123!<br>商户账号：merchant_craft / StayScape123!</div></div></div>
</template>

