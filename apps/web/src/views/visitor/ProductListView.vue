<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { TravelProduct } from '../../types'

const items = ref<TravelProduct[]>([])
const loading = ref(false)
const error = ref('')
const form = reactive({ target_date: '', budget: '', interest: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await visitorApi.products({ target_date: form.target_date || undefined, budget: form.budget || undefined, interest: form.interest || undefined })
    items.value = response.data
  } catch (e) { error.value = errorMessage(e) }
  finally { loading.value = false }
}
function clear() { form.target_date = ''; form.budget = ''; form.interest = ''; load() }

onMounted(load)
</script>

<template>
  <main class="product-list">
    <header class="product-list__head"><div><span>杭州产品</span><h1>挑一组直接出发，或自己改一份。</h1></div><router-link to="/visitor/recommend">说说想怎么玩</router-link></header>
    <section class="product-filter"><el-date-picker v-model="form.target_date" value-format="YYYY-MM-DD" type="date" placeholder="出发日期" /><el-input v-model="form.interest" placeholder="想玩什么：博物馆、乐园、看展、运动" clearable @keyup.enter="load" /><el-input v-model="form.budget" placeholder="预算上限" inputmode="numeric" /><el-button type="primary" @click="load">筛选</el-button></section>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <div v-if="loading" class="home-loading"><span /> 正在查看可预约产品…</div>
    <div v-else-if="items.length" class="product-grid product-grid--editorial product-grid--wide"><ProductCard v-for="product in items" :key="product.id" :product="product" public-view /></div>
    <div v-else class="list-empty"><h2>没有完全一样的现成产品</h2><p>可以放宽筛选，或把具体日期和想法写进自定义行程。</p><div><el-button type="primary" @click="$router.push('/visitor/recommend')">定制行程</el-button><el-button plain @click="clear">清除筛选</el-button></div></div>
  </main>
</template>

<style scoped>
.product-list{max-width:1180px;margin:0 auto;padding:8px 0 44px}.product-list__head{display:flex;align-items:end;justify-content:space-between;gap:18px;margin:8px 0 16px}.product-list__head span{color:var(--muted);font-size:10px;letter-spacing:.1em}.product-list__head h1{margin:5px 0 0;font-size:clamp(22px,3vw,31px);letter-spacing:-.8px}.product-list__head a{padding:9px 12px;border:1px solid var(--line);border-radius:9px;color:var(--ink);font-size:12px;text-decoration:none;white-space:nowrap}.product-filter{display:grid;grid-template-columns:150px minmax(180px,1fr) 120px auto;gap:8px;padding:10px;border:1px solid var(--line);border-radius:12px;background:var(--panel-soft);margin-bottom:16px}.list-empty{padding:48px 18px;border:1px dashed var(--line);border-radius:12px;text-align:center}.list-empty h2{margin:0;font-size:18px}.list-empty p{color:var(--muted);font-size:12px}.list-empty .el-button{margin:4px}@media(max-width:700px){.product-list{padding-top:0}.product-list__head{align-items:start}.product-list__head a{margin-top:8px}.product-filter{grid-template-columns:1fr 1fr}.product-filter :deep(.el-date-editor),.product-filter :deep(.el-input){width:100%}.product-filter .el-button{grid-column:1/-1}.product-grid--wide{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
</style>
