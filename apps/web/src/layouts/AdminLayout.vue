<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const isMerchant = computed(() => auth.role === 'MERCHANT')
const hotelMenu = [
  { path: '/hotel/dashboard', label: '经营总览', icon: '◈' }, { path: '/hotel/rooms', label: '临期客房', icon: '▦' }, { path: '/hotel/services', label: '酒店服务', icon: '⌁' },
  { path: '/hotel/resources', label: '合作资源池', icon: '◇' }, { path: '/hotel/products', label: '当前产品池', icon: '▤' }, { path: '/hotel/products/generate', label: '生成产品', icon: '✦' }, { path: '/hotel/operations', label: '动态运营', icon: '↻' },
  { path: '/hotel/intents', label: '游客意向', icon: '♡' }, { path: '/hotel/skill-logs', label: '调用日志', icon: '⌘' }
]
const merchantMenu = [{ path: '/merchant/dashboard', label: '商户工作台', icon: '◈' }, { path: '/merchant/resources', label: '我的资源', icon: '◇' }]
const menu = computed(() => isMerchant.value ? merchantMenu : hotelMenu)
function logout() { auth.logout(); router.push('/visitor') }
</script>

<template>
  <div class="admin-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark" aria-label="杭州旅居"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></div><div><strong>杭州旅居</strong><small>城市周末产品工作台</small></div></div>
      <div class="sidebar-role"><span class="dot" />{{ isMerchant ? '合作商户端' : '酒店经营端' }}</div>
      <nav class="sidebar-nav"><router-link v-for="item in menu" :key="item.path" :to="item.path" :class="{ active: route.path === item.path }"><span class="nav-icon">{{ item.icon }}</span>{{ item.label }}</router-link></nav>
      <div class="sidebar-bottom"><router-link to="/visitor"><span class="nav-icon">↗</span>游客端预览</router-link><button @click="logout"><span class="nav-icon">⇥</span>退出登录</button></div>
    </aside>
    <main class="admin-main"><header class="topbar"><div><span class="breadcrumb">杭州旅居 /</span><strong>{{ isMerchant ? '合作资源工作台' : '酒店产品工作台' }}</strong></div><div class="topbar-user"><span class="avatar">{{ auth.user?.username?.slice(0, 1).toUpperCase() }}</span><span>{{ auth.user?.username }}</span><span class="role-badge">{{ isMerchant ? '商户' : '酒店' }}</span></div></header><section class="page-container"><router-view /></section></main>
  </div>
</template>
