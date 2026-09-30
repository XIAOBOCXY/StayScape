<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import VisitorAssistant from '../../components/VisitorAssistant.vue'

const route = useRoute()
const productId = computed(() => {
  const value = Number(route.query.product)
  return Number.isFinite(value) && value > 0 ? value : null
})
</script>

<template>
  <main class="assistant-page">
    <header class="assistant-page__head">
      <h1>旅居助手</h1>
    </header>
    <section class="assistant-page__body">
      <VisitorAssistant :product-id="productId" />
    </section>
  </main>
</template>

<style scoped>
/* 独立聊天页：不套卡片边框，输入框固定在视口最下方。 */
.assistant-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  /* 宽度只用「百分比 + 上限」表达，绝不按内容撑开：
     没有消息、正在查询、回答完成三种状态宽度完全一致。 */
  width: 100%;
  max-width: 960px;
  margin-inline: auto;
}
.assistant-page__head { flex: 0 0 auto; display: flex; align-items: baseline; gap: 10px; width: 100%; margin: 4px 0 10px; }
.assistant-page__head h1 { margin: 0; color: #222; font-size: 22px; font-weight: 700; }
.assistant-page__head small { color: var(--muted); font-size: 12px; }
.assistant-page__body { flex: 1 1 auto; width: 100%; min-height: 0; display: flex; }
.assistant-page__body > * { flex: 1 1 100%; width: 100%; min-width: 0; }
.assistant-page__body,
.assistant-page__body > * { min-width: 0; max-width: 100%; }
@media (max-width: 700px) {
  .assistant-page { width: 100%; padding: 0 2px; }
  .assistant-page__head { margin: 2px 0 8px; }
  .assistant-page__head h1 { font-size: 18px; }
  .assistant-page__head small { display: none; }
}
</style>
