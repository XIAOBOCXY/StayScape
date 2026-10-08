<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { hotelApi } from '../api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const currentProductTitle = ref('')
let productTitleRequest = 0
const isMerchant = computed(() => auth.role === 'MERCHANT')
const hotelMenu = [
  { path: '/hotel/dashboard', label: '经营总览', icon: '◈' }, { path: '/hotel/rooms', label: '临期客房', icon: '▦' }, { path: '/hotel/services', label: '酒店服务', icon: '⌁' },
  { path: '/hotel/resources', label: '合作资源池', icon: '◇' }, { path: '/hotel/products', label: '当前产品池', icon: '▤' }, { path: '/hotel/knowledge', label: '文旅知识库', icon: '◍' }, { path: '/hotel/operations', label: '动态运营', icon: '↻' },
  { path: '/hotel/intents', label: '游客订单', icon: '♡' }, { path: '/hotel/skill-logs', label: '调用日志', icon: '⌘' }, { path: '/hotel/settings', label: 'API 设置', icon: '⚙' }, { path: '/hotel/agent-access', label: 'Agent 接入', icon: '⇄' }
]
const merchantMenu = [{ path: '/merchant/dashboard', label: '商户工作台', icon: '◈' }, { path: '/merchant/resources', label: '我的资源', icon: '◇' }]
const menu = computed(() => isMerchant.value ? merchantMenu : hotelMenu)
const pageTitle = computed(() => {
  const path = route.path.replace(/\/$/, '') || '/'
  if (path === '/hotel/products/generate') return '产品生成'
  if (/^\/hotel\/products\/[^/]+$/.test(path)) return currentProductTitle.value || '产品详情'
  return [...hotelMenu, ...merchantMenu].find((item) => item.path === path)?.label || '工作台'
})
watch(() => route.params.id, async (id) => {
  const requestId = ++productTitleRequest
  currentProductTitle.value = ''
  if (!/^\/hotel\/products\/[^/]+$/.test(route.path) || !id || !/^\d+$/.test(String(id))) return
  try {
    const response = await hotelApi.product(Number(id))
    if (requestId === productTitleRequest) currentProductTitle.value = response.data.product_name
  } catch {
    // Keep the neutral route title when the detail request fails.
  }
}, { immediate: true })
function logout() { auth.logout(); router.push('/visitor') }
</script>

<template>
  <div class="admin-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark" aria-label="余宿成景"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></div><div class="brand-name"><strong>余宿成景</strong><small>StayScape</small></div></div>
      <div v-if="isMerchant" class="sidebar-role"><span class="dot" />合作商户端</div>
      <nav class="sidebar-nav"><router-link v-for="item in menu" :key="item.path" :to="item.path" :class="{ active: route.path === item.path, 'nav-primary': item.path === '/hotel/products/generate' }"><span class="nav-icon">{{ item.icon }}</span>{{ item.label }}</router-link></nav>
        <router-link v-if="!isMerchant" to="/hotel/products/generate" :class="['generate-cta', { active: route.path === '/hotel/products/generate' }]"><span class="generate-cta__icon">✦</span><span class="generate-cta__label">生成产品</span></router-link>
      <div class="sidebar-bottom"><router-link to="/visitor"><span class="nav-icon">↗</span>游客端预览</router-link><button @click="logout"><span class="nav-icon">⇥</span>退出登录</button></div>
    </aside>
    <main class="admin-main">
      <header class="topbar">
        <strong class="topbar-title">{{ pageTitle }}</strong>
        <div class="topbar-right">
          <div id="page-toolbar" class="topbar-actions" />
          <div class="topbar-user"><span class="avatar">{{ auth.user?.username?.slice(0, 1).toUpperCase() }}</span><span>{{ auth.user?.username }}</span><span class="role-badge">{{ isMerchant ? '商户' : '酒店' }}</span></div>
        </div>
      </header>
      <section class="page-container"><router-view /></section>
    </main>
  </div>
</template>

<style scoped>
.brand{display:flex;align-items:center;gap:10px;padding:0 14px}.brand-name{display:grid;gap:2px;min-width:0}.brand-name strong{color:#24322e;font-size:14px;letter-spacing:.04em;white-space:nowrap}.brand-name small{color:#8b9691;font-size:9px;letter-spacing:.12em}
/* 「生成产品」是工作台的核心动作：放在菜单最上方做成独立按钮，而不是普通菜单项。 */
.generate-cta{display:flex;align-items:center;justify-content:center;gap:8px;margin:14px 14px 6px;padding:12px 14px;border-radius:10px;background:linear-gradient(135deg,#ff7a2f,#ff6a00);color:#fff;font-size:14px;font-weight:750;letter-spacing:.02em;text-decoration:none;box-shadow:0 10px 22px rgba(255,106,0,.28)}
.generate-cta:hover{background:linear-gradient(135deg,#ff8b45,#ff7d1f);color:#fff}
.generate-cta__icon{font-size:16px;line-height:1}
.generate-cta.active{background:linear-gradient(135deg,#ff8b45,#ff6a00);box-shadow:inset 0 0 0 2px rgba(255,255,255,.55), 0 10px 22px rgba(255,106,0,.32)}
@media(max-width:700px){
  .brand{justify-content:flex-start;padding-inline:8px}.brand-name{display:grid}
  .generate-cta{margin:10px 8px 4px;padding:10px 6px;font-size:12px}
  .generate-cta__label{display:inline}
}
</style>
