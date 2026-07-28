<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <div class="visitor-shell">
    <header class="visitor-header"><router-link to="/visitor" class="visitor-brand"><span class="brand-mark">S</span><span><strong>StayScape</strong><small>余宿成景</small></span></router-link><nav><router-link to="/visitor/products" :class="{ active: route.path.includes('/products') }">全部套餐</router-link><router-link to="/visitor/recommend" :class="{ active: route.path.includes('/recommend') }">为我推荐</router-link><router-link to="/login">经营入口</router-link></nav></header><main class="visitor-main"><router-view /></main><footer class="visitor-footer">StayScape · 把一间余房，变成一段杭州体验</footer>
  </div>
</template>

