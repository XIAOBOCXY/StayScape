<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { TravelProduct } from '../../types'
import { useRoute } from 'vue-router'

const route = useRoute()
const items = ref<TravelProduct[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const pageSize = 12
const hasMore = ref(false)
const error = ref('')
const form = reactive({ target_date: '', budget: '', interest: '' })
const topics = ['博物馆', '亲子', '夜游', '美食', '旅拍', '运动']
const resultLabel = computed(() => loading.value ? '正在查找' : items.value.length + (hasMore.value ? '+' : '') + ' 组商品')
const hasFilters = computed(() => Boolean(form.target_date || form.budget || form.interest))

async function load(reset = true) {
  if (reset) { loading.value = true; error.value = '' }
  else loadingMore.value = true
  try {
    const offset = reset ? 0 : items.value.length
    const response = await visitorApi.products({
      target_date: form.target_date || undefined,
      budget: form.budget || undefined,
      interest: form.interest || undefined,
      compact: true,
      limit: pageSize,
      offset,
    })
    items.value = reset ? response.data : [...items.value, ...response.data]
    hasMore.value = response.data.length === pageSize
  } catch (e) { error.value = errorMessage(e) }
  finally { if (reset) loading.value = false; else loadingMore.value = false }
}
function loadMore() { void load(false) }
function clear() { form.target_date = ''; form.budget = ''; form.interest = ''; load() }

onMounted(() => {
  const interest = route.query.interest
  if (typeof interest === 'string') form.interest = interest
  void load()
})
</script>

<template>
  <main class="product-list storefront-list">
    <header class="product-list__head"><div><h1>杭州旅居商品</h1></div><span class="list-count">{{ resultLabel }}</span></header>
<div class="list-topics"><span>快速筛选</span><button v-for="topic in topics" :key="topic" :class="{ active: form.interest === topic }" @click="form.interest = topic; load()">{{ topic }}</button><button v-if="hasFilters" class="topic-clear" type="button" @click="clear">清除筛选</button></div>
    <section class="product-filter"><label><span>日期</span><el-date-picker v-model="form.target_date" value-format="YYYY-MM-DD" type="date" placeholder="选择入住日期" /></label><label class="filter-interest"><span>主题或地点</span><el-input v-model="form.interest" placeholder="如：博物馆、运河、亲子" clearable @keyup.enter="load" /></label><label><span>预算</span><el-input v-model="form.budget" placeholder="最高 ¥" inputmode="numeric" /></label><el-button type="primary" @click="load">查找商品</el-button><el-button v-if="hasFilters" plain @click="clear">清除筛选</el-button></section>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <div v-if="loading" class="home-loading"><span /> 正在加载商品…</div>
    <div v-else-if="items.length" class="product-grid product-grid--editorial product-grid--wide"><ProductCard v-for="product in items" :key="product.id" :product="product" public-view /></div>
    <div v-if="hasMore && !loading && items.length" class="catalog-load-more"><el-button plain :loading="loadingMore" @click="loadMore">继续加载</el-button></div>
    <!-- 空状态只跟「有没有商品」有关，之前误挂在「继续加载」的 v-else 上，
         导致有商品时底部也会出现「暂时没有匹配的商品」。 -->
    <div v-if="!loading && !items.length" class="list-empty"><h2>暂时没有匹配的商品</h2><p>换一个日期、主题或预算再试。</p><div><el-button plain @click="clear">清除筛选</el-button></div></div>
  </main>
</template>

<style scoped>
.product-list{max-width:1180px;margin:0 auto;padding:8px 0 44px}.product-list__head{display:flex;align-items:end;justify-content:space-between;gap:18px;margin:8px 0 16px}.product-list__head span{color:var(--muted);font-size:10px;letter-spacing:.1em}.product-list__head h1{margin:5px 0 0;font-size:clamp(22px,3vw,31px);letter-spacing:-.8px}.product-list__head a{padding:9px 12px;border:1px solid var(--line);border-radius:9px;color:var(--ink);font-size:12px;text-decoration:none;white-space:nowrap}.product-filter{display:grid;grid-template-columns:150px minmax(180px,1fr) 120px auto;gap:8px;padding:10px;border:1px solid var(--line);border-radius:12px;background:var(--panel-soft);margin-bottom:16px}.list-empty{padding:48px 18px;border:1px dashed var(--line);border-radius:12px;text-align:center}.list-empty h2{margin:0;font-size:18px}.list-empty p{color:var(--muted);font-size:12px}.list-empty .el-button{margin:4px}@media(max-width:700px){.product-list{padding-top:0}.product-list__head{align-items:start}.product-list__head a{margin-top:8px}.product-filter{grid-template-columns:1fr 1fr}.product-filter :deep(.el-date-editor),.product-filter :deep(.el-input){width:100%}.product-filter .el-button{grid-column:1/-1}.product-grid--wide{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
</style>


<style scoped>
/* Product listing keeps the storefront tone: a quiet filter row and image-led cards. */
.product-list {
  width: min(1080px, 100%);
  max-width: 1080px;
  box-sizing: border-box;
  margin: 0 auto;
  padding: 0 0 44px;
}
.product-list__head { margin: 10px 0 18px; }
.product-list__head span { color: #999; letter-spacing: .02em; }
.product-list__head h1 { color: #222; font-size: 26px; font-weight: 700; }
.product-filter {
  display: grid;
  grid-template-columns: 150px minmax(220px, 1fr) 120px auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 18px;
  padding: 10px 0 14px;
  border: 0;
  border-bottom: 1px solid #eee9e4;
  border-radius: 0;
  background: #fff;
}
.product-filter :deep(.el-input__wrapper),
.product-filter :deep(.el-date-editor.el-input__wrapper) {
  border-radius: 6px;
  background: #fafafa;
  box-shadow: 0 0 0 1px #e8e3de inset;
}
.product-filter :deep(.el-button--primary) {
  border: 0;
  border-radius: 18px;
  background: #ff6a00;
  border-color: #ff6a00;
}
.list-empty {
  padding: 52px 18px;
  border: 0;
  border-top: 1px solid #eee9e4;
  border-radius: 0;
  background: #fff;
}
@media (max-width: 700px) {
  .product-list { padding: 0 0 34px; }
  .product-list__head h1 { font-size: 22px; }
  .product-filter { grid-template-columns: 1fr 1fr; padding-bottom: 12px; }
  .product-filter .el-button { grid-column: 1 / -1; }
}
</style>


<style scoped>
/* Storefront catalogue: filters read like a travel-commerce search bar. */
.catalog-load-more{display:flex;justify-content:center;padding:8px 20px 26px}.storefront-list { width: min(1280px, 100%); max-width: 1280px; margin: 0 auto; padding: 0 0 54px; background: #fff; color: #252525; }
.storefront-list .product-list__head { align-items: flex-end; margin: 0; padding: 20px 20px 18px; border-bottom: 1px solid #eee9e4; }
.storefront-list .product-list__head small { color: #ff6a00; font-size: 10px; letter-spacing: .12em; }
.storefront-list .product-list__head h1 { margin: 8px 0 6px; color: #222; font-size: clamp(23px, 4vw, 32px); font-weight: 750; letter-spacing: -.7px; }
.storefront-list .product-list__head p { margin: 0; color: #888; font-size: 12px; line-height: 1.65; }
.storefront-list .list-count { flex: 0 0 auto; color: #999; font-family: var(--font-mono); font-size: 11px; }
.storefront-list .list-topics { display: flex; align-items: center; gap: 16px; overflow-x: auto; padding: 14px 20px; border-bottom: 8px solid #f5f5f5; }
.storefront-list .list-topics > span { flex: 0 0 auto; color: #999; font-size: 11px; }
.storefront-list .list-topics button { flex: 0 0 auto; padding: 0 0 3px; border: 0; border-bottom: 1px solid transparent; background: none; color: #555; font-size: 11px; cursor: pointer; }
.storefront-list .list-topics button:hover, .storefront-list .list-topics button.active { border-bottom-color: #ff6a00; color: #ff6a00; }
.storefront-list .list-topics button.topic-clear { margin-left: auto; color: #999; }
.storefront-list .product-filter { grid-template-columns: 150px minmax(220px, 1fr) 120px auto; align-items: end; gap: 10px; margin: 0; padding: 18px 20px 20px; border: 0; border-bottom: 1px solid #eee9e4; border-radius: 0; background: #fff; }
.storefront-list .product-filter label { display: grid; gap: 5px; min-width: 0; }
.storefront-list .product-filter label > span { color: #999; font-size: 10px; }
.storefront-list .product-filter :deep(.el-date-editor), .storefront-list .product-filter :deep(.el-input) { width: 100%; }
.storefront-list .product-filter :deep(.el-input__wrapper), .storefront-list .product-filter :deep(.el-date-editor.el-input__wrapper) { min-height: 34px; border-radius: 4px; background: #fafafa; box-shadow: 0 0 0 1px #e5dfda inset; }
.storefront-list .product-filter :deep(.el-button--primary) { height: 34px; border: 0; border-radius: 4px; background: #ff6a00; }
.storefront-list > .el-alert { margin: 14px 20px 0; }
.storefront-list > .product-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin: 20px; }
.storefront-list .list-empty { margin: 20px; padding: 52px 18px; border: 0; border-top: 1px solid #eee9e4; border-radius: 0; background: #fff; }
@media (max-width: 1000px) {
  .storefront-list > .product-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 820px) {
  .storefront-list > .product-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .storefront-list .product-list__head { align-items: flex-start; padding: 16px 14px; }
  .storefront-list .product-list__head h1 { font-size: 24px; }
  .storefront-list .product-list__head p { font-size: 11px; }
  .storefront-list .list-count { padding-top: 4px; }
  .storefront-list .list-topics { padding: 12px 14px; gap: 14px; }
  .storefront-list .product-filter { grid-template-columns: 1fr 1fr; padding: 14px; }
  .storefront-list .product-filter .filter-interest { grid-column: 1 / -1; }
  .storefront-list .product-filter > .el-button { grid-column: 1 / -1; width: 100%; }
  .storefront-list .list-empty { margin: 14px; }
}
@media (max-width: 620px) {
  .storefront-list > .product-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 12px; gap: 8px; }
  .storefront-list > .product-grid .product-card--editorial h3 { margin: 6px 0 3px; font-size: 13px; }
  .storefront-list > .product-grid .product-card__hook { min-height: 0; font-size: 10px; line-height: 1.5; -webkit-line-clamp: 2; }
  .storefront-list > .product-grid .product-card__facts { gap: 3px 7px; margin-top: 7px; font-size: 9px; }
  .storefront-list > .product-grid .product-card__body { padding: 9px 10px 10px; }
  .storefront-list > .product-grid .product-card__bottom strong { font-size: 15px; }
}
@media (max-width: 420px) {
  .storefront-list > .product-grid { margin: 10px; gap: 7px; }
  .storefront-list > .product-grid .product-card--editorial h3 { font-size: 12px; }
  .storefront-list > .product-grid .product-card__hook { font-size: 9px; }
}
</style>
