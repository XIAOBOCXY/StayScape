<script setup lang="ts">
// 经营端商品预览复用游客端详情实现（visitor/ProductDetailView.vue）：
// 组件内部通过路由前缀识别 /hotel/products/:id，改用经营端接口取数并显示内部预览横幅。
// 这样详情页只有一份实现，不会再出现两份 1700 行页面各自漂移的问题。
import VisitorProductDetail from '../visitor/ProductDetailView.vue'
</script>

<template>
  <VisitorProductDetail />
</template>
