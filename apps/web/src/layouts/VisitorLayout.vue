<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="visitor-shell">
    <header class="visitor-header visitor-header--editorial">
      <router-link to="/visitor" class="visitor-brand">
        <span class="brand-mark">S</span>
        <span><strong>StayScape</strong><small>余宿成景 · HANGZHOU</small></span>
      </router-link>
      <nav class="visitor-nav">
        <router-link to="/visitor/products" :class="{ active: route.path === '/visitor/products' }">探索套餐 <small>EXPLORE</small></router-link>
        <router-link to="/visitor/recommend" :class="{ active: route.path.includes('/recommend') }">告诉我想怎么玩 <small>CONCIERGE</small></router-link>
        <router-link to="/login" class="visitor-business-link">经营入口</router-link>
      </nav>
      <div class="visitor-live"><i /> 今晚杭州 · LIVE</div>
    </header>
    <main class="visitor-main visitor-main--editorial"><router-view /></main>
    <footer class="visitor-footer"><span>STAYSCAPE</span> · 把一间余房，变成一段值得发生的杭州故事</footer>
  </div>
</template>
