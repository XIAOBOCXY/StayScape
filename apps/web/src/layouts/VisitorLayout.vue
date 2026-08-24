<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="visitor-shell">
    <header class="visitor-header visitor-header--editorial">
      <router-link to="/visitor" class="visitor-brand">
        <span class="brand-mark" aria-label="杭州旅居"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></span>
        <span><strong>杭州旅居</strong><small>城市周末灵感</small></span>
      </router-link>
      <nav class="visitor-nav">
        <router-link to="/visitor/products" :class="{ active: route.path === '/visitor/products' }">探索套餐</router-link>
        <router-link to="/visitor/recommend" :class="{ active: route.path.includes('/recommend') }">说说想怎么玩</router-link>
        <router-link to="/login" class="visitor-business-link">经营入口</router-link>
      </nav>
      <div class="visitor-live"><i /> 杭州周末</div>
    </header>
    <main class="visitor-main visitor-main--editorial"><router-view /></main>
    <footer class="visitor-footer"><span>杭州旅居</span> · 把一间余房，变成一段值得出发的杭州故事</footer>
  </div>
</template>
