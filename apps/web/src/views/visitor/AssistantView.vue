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
    <section class="assistant-page__body">
      <VisitorAssistant :product-id="productId" page-layout />
    </section>
  </main>
</template>

<style scoped>
/* 独立聊天页：内容区直接承接站点导航，输入框固定在视口最下方。 */
.assistant-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  /* 宽度只用「百分比 + 上限」表达，绝不按内容撑开：
     没有消息、正在查询、回答完成三种状态宽度完全一致。 */
  width: 100%;
  max-width: 1200px;
  min-width: 0;
  align-self: stretch;
  margin-inline: auto;
  padding-inline: 24px;
  box-sizing: border-box;
}
.assistant-page__body { flex: 1 1 auto; width: min(100%, 1000px); min-height: 0; display: flex; margin-inline: auto; padding-top: 0; }
.assistant-page__body > * { flex: 1 1 100%; width: 100%; min-width: 0; }
.assistant-page__body,
.assistant-page__body > * { min-width: 0; max-width: 100%; }
@media (max-width: 700px) {
  .assistant-page { width: 100%; padding: 0 16px; }
  .assistant-page__body { padding-top: 0; }
}
</style>
