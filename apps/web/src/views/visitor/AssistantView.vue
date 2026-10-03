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
      <router-link to="/visitor/products">浏览可订套餐 <b aria-hidden="true">→</b></router-link>
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
  min-width: 0;
  align-self: stretch;
  margin-inline: auto;
}
.assistant-page__head { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 36px; margin: 0 0 8px; border-bottom: 1px solid #e4e7e3; }
.assistant-page__head h1 { margin: 0; color: #263c33; font-size: 18px; font-weight: 600; letter-spacing: -.2px; }
.assistant-page__head a { color: #557465; font-size: 10.5px; white-space: nowrap; }
.assistant-page__head a b { margin-left: 4px; color: #c18a4b; font-size: 14px; }
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
