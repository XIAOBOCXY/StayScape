<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { TravelProduct } from '../../types'

const route = useRoute()
const items = ref<TravelProduct[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const hasMore = ref(false)
const error = ref('')
const pageSize = 12
const form = reactive({ target_date: '', interest: '' })
const budgetBand = ref('all')
const topics = ['博物馆', '亲子', '夜游', '美食', '旅拍', '运动', '西湖', '钱江新城', '陶艺', '甜品']
const hasFilters = () => Boolean(form.target_date || form.interest || budgetBand.value !== 'all')

function budgetParams() {
  if (budgetBand.value === 'under500') return { budget: 500 }
  if (budgetBand.value === '500to800') return { budget_min: 500, budget: 800 }
  if (budgetBand.value === 'over800') return { budget_min: 800 }
  return {}
}

async function load(reset = true) {
  if (reset) { loading.value = true; error.value = '' }
  else loadingMore.value = true
  try {
    const response = await visitorApi.products({
      target_date: form.target_date || undefined,
      interest: form.interest || undefined,
      ...budgetParams(),
      compact: true,
      limit: pageSize,
      offset: reset ? 0 : items.value.length,
    })
    items.value = reset ? response.data : [...items.value, ...response.data]
    hasMore.value = response.data.length === pageSize
  } catch (e) { error.value = errorMessage(e) }
  finally { if (reset) loading.value = false; else loadingMore.value = false }
}

function selectTopic(topic: string) {
  form.interest = form.interest === topic ? '' : topic
}
function clear() { form.target_date = ''; form.interest = ''; budgetBand.value = 'all'; void load() }

onMounted(() => {
  const interest = route.query.interest
  if (typeof interest === 'string') form.interest = interest
  void load()
})
</script>

<template>
  <main class="product-list storefront-list">
    <section class="product-filter" aria-label="查找旅居套餐">
      <el-date-picker
        v-model="form.target_date"
        class="filter-date"
        value-format="YYYY-MM-DD"
        type="date"
        placeholder="入住日期"
        aria-label="入住日期"
      />
      <div class="topic-picker" role="group" aria-label="主题或地点">
        <button type="button" :class="{ active: !form.interest }" :aria-pressed="!form.interest" @click="selectTopic('')">全部</button>
        <button v-for="topic in topics" :key="topic" type="button" :class="{ active: form.interest === topic }" :aria-pressed="form.interest === topic" @click="selectTopic(topic)">{{ topic }}</button>
      </div>
      <el-select v-model="budgetBand" class="filter-budget" aria-label="预算范围">
        <el-option label="预算不限" value="all" />
        <el-option label="500 元以内" value="under500" />
        <el-option label="500–800 元" value="500to800" />
        <el-option label="800 元以上" value="over800" />
      </el-select>
      <div class="filter-actions">
        <button v-if="hasFilters()" class="filter-reset" type="button" @click="clear">清除筛选</button>
        <el-button type="primary" @click="load()">查找套餐</el-button>
      </div>
    </section>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <div v-if="loading" class="home-loading"><span /> 正在加载套餐…</div>
    <div v-else-if="items.length" class="product-grid product-grid--editorial product-grid--wide"><ProductCard v-for="product in items" :key="product.id" :product="product" public-view /></div>
    <div v-if="hasMore && !loading && items.length" class="catalog-load-more"><el-button plain :loading="loadingMore" @click="load(false)">继续加载</el-button></div>
    <div v-if="!loading && !items.length" class="list-empty"><h2>暂时没有匹配的套餐</h2><p>换一个日期、主题或预算范围再试。</p><div><el-button plain @click="clear">清除筛选</el-button></div></div>
  </main>
</template>

<style scoped>
.storefront-list { width: 100%; max-width: 1200px; box-sizing: border-box; margin: 0 auto; padding: 0 0 54px; color: #252a27; }
.product-filter { display: grid; grid-template-columns: 168px minmax(0, 1fr) 148px auto; align-items: center; gap: 12px; margin: 0 0 8px; padding: 0 0 10px; border: 0; background: transparent; }
.product-filter :deep(.filter-date), .product-filter :deep(.filter-budget) { width: 100%; min-width: 0; }
.product-filter :deep(.el-input__wrapper), .product-filter :deep(.el-date-editor.el-input__wrapper), .product-filter :deep(.el-select__wrapper) { min-height: 38px; border-radius: 9px; background: #fff; box-shadow: 0 0 0 1px #e4e7e3 inset; }
.topic-picker { display: flex; align-items: center; gap: 6px; min-width: 0; min-height: 38px; overflow-x: auto; padding: 0 0 1px; scrollbar-width: none; white-space: nowrap; }
.topic-picker::-webkit-scrollbar { display: none; }
.topic-picker button { flex: 0 0 auto; height: 31px; padding: 0 10px; border: 1px solid #e4e8e3; border-radius: 999px; background: #fff; color: #5f6b62; font-size: 12px; cursor: pointer; transition: background-color .16s ease, border-color .16s ease, color .16s ease; }
.topic-picker button:hover, .topic-picker button.active { border-color: #b9d2c2; background: #eff6f1; color: #32644a; }
.filter-actions { display: flex; align-items: center; justify-content: flex-end; gap: 7px; min-height: 38px; white-space: nowrap; }
.product-filter :deep(.el-button) { height: 38px; min-height: 38px; padding: 0 15px; border-radius: 9px; }
.filter-reset { height: 38px; padding: 0 13px; border: 1px solid #d9e0da; border-radius: 9px; background: #fff; color: #52635a; font-size: 13px; cursor: pointer; transition: border-color .16s ease, background-color .16s ease; }
.filter-reset:hover { border-color: #a8c5b3; background: #f8fbf8; color: #365f4a; }
.storefront-list > .product-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; margin: 14px 0 20px; }
.catalog-load-more { display: flex; justify-content: center; padding: 8px 20px 26px; }
.list-empty { margin: 18px 0; padding: 52px 18px; border: 0; border-radius: 0; background: transparent; text-align: center; }
.list-empty h2 { margin: 0; font-size: 18px; }
.list-empty p { color: #7f8982; font-size: 13px; }
@media (max-width: 1050px) { .storefront-list > .product-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; } .product-filter { grid-template-columns: 152px minmax(0, 1fr) 140px auto; gap: 9px; } }
@media (max-width: 780px) {
  .storefront-list > .product-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .product-filter { grid-template-columns: minmax(130px, .78fr) minmax(0, 1.45fr); gap: 9px 12px; padding-bottom: 12px; }
  .filter-date { grid-column: 1; grid-row: 1; }
  .topic-picker { grid-column: 2; grid-row: 1; }
  .filter-budget { grid-column: 1; grid-row: 2; }
  .filter-actions { grid-column: 2; grid-row: 2; }
}
@media (max-width: 520px) {
  .storefront-list > .product-grid { grid-template-columns: 1fr; gap: 12px; margin: 12px 0 18px; }
  .product-filter { grid-template-columns: minmax(118px, .78fr) minmax(0, 1.4fr); gap: 8px 9px; }
  .topic-picker { gap: 5px; }
  .topic-picker button { height: 29px; padding: 0 8px; font-size: 11.5px; }
  .filter-actions { gap: 5px; }
  .product-filter :deep(.el-button) { height: 36px; min-height: 36px; padding: 0 10px; font-size: 12px; }
}
</style>
