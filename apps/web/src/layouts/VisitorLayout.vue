<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
// 旅居助手是整屏对话页：页面本身不滚动，只滚动对话内容。
const isChat = computed(() => route.path.startsWith('/visitor/assistant'))
</script>

<template>
  <div :class="['visitor-shell', { 'visitor-shell--chat': isChat }]">
    <header class="visitor-header visitor-header--editorial">
      <router-link to="/visitor" class="visitor-brand">
        <span class="brand-mark" aria-label="杭州旅居"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></span>
        <span><strong>杭州旅居</strong><small>城市周末灵感</small></span>
      </router-link>
      <nav class="visitor-nav">
        <router-link to="/visitor/products" :class="{ active: route.path.startsWith('/visitor/products') }">旅居商品</router-link>
        <router-link to="/visitor/assistant" :class="{ active: route.path === '/visitor/assistant' }">旅居助手</router-link>
        <router-link to="/login" class="visitor-business-link">经营入口</router-link>
      </nav>
      <div class="visitor-live"><i /> 杭州周末</div>
    </header>
    <main class="visitor-main visitor-main--editorial"><router-view /></main>
    <footer class="visitor-footer"><span>杭州旅居</span> · 把一间余房，变成一段值得出发的杭州故事</footer>
  </div>
</template>

<style scoped>
/* 对话页：整屏高度、页面不滚动，只有内部对话区滚动。 */
.visitor-shell--chat {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  max-height: 100dvh;
  overflow: hidden;
}
.visitor-shell--chat .visitor-main,
.visitor-shell--chat .visitor-main--editorial {
  flex: 1 1 auto;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 10px 14px 14px;
  overflow: hidden;
}
.visitor-shell--chat .visitor-footer { display: none; }
@media (max-width: 700px) {
  .visitor-shell--chat .visitor-main,
  .visitor-shell--chat .visitor-main--editorial { padding: 8px 12px 10px; }
}
</style>
