<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { TravelProduct } from '../../types'

const products = ref<TravelProduct[]>([])
const loading = ref(true)
const error = ref('')
const quickText = ref('')
const dateHint = computed(() => products.value.length ? `${products.value.length} 组可预约安排正在更新` : '正在查看可预约安排')

async function load() {
  loading.value = true
  error.value = ''
  try { products.value = (await visitorApi.products()).data }
  catch (e) { error.value = errorMessage(e) }
  finally { loading.value = false }
}
function startPlan() {
  const query = quickText.value.trim() ? { q: quickText.value.trim() } : undefined
  window.location.href = `/visitor/recommend${query ? `?${new URLSearchParams(query).toString()}` : ''}`
}

onMounted(load)
</script>

<template>
  <main class="visitor-home">
    <section class="home-top">
      <div class="home-top__ticker"><span /> {{ dateHint }}<i>·</i> 房型、体验和价格以当前日期为准</div>
      <div class="home-top__title"><div><h1>杭州，怎么安排都可以。</h1><p>选一组已上架的产品，或把第一天、第二天想做的事直接说出来。</p></div><router-link to="/visitor/products">查看全部</router-link></div>
      <div class="quick-plan"><input v-model="quickText" placeholder="说说想怎么玩，例如：周六两个人看展吃饭，第二天去博物馆" @keyup.enter="startPlan" /><button @click="startPlan">开始定制</button></div>
    </section>

    <section class="home-products"><div class="home-products__head"><h2>可预约产品</h2><span>按日期、同行人和玩法筛选</span></div><div v-if="loading" class="home-loading"><span /> 正在读取杭州的可预约安排…</div><el-alert v-else-if="error" :title="error" type="error" show-icon /><div v-else-if="products.length" class="product-grid product-grid--editorial home-product-grid"><ProductCard v-for="product in products.slice(0, 10)" :key="product.id" :product="product" public-view /></div><div v-else class="home-empty"><h3>暂时没有上架产品</h3><p>可以先直接写下日期和玩法，我们会按当前可用资源帮你组合。</p><button @click="startPlan">去定制行程</button></div></section>
  </main>
</template>

<style scoped>
.visitor-home{max-width:1180px;margin:0 auto;padding:8px 0 48px}.home-top{padding:14px 0 20px;border-bottom:1px solid var(--line)}.home-top__ticker{display:flex;align-items:center;gap:7px;color:var(--muted);font-family:var(--font-mono);font-size:10px}.home-top__ticker span{width:6px;height:6px;border-radius:50%;background:#4e8f72;box-shadow:0 0 0 4px #e0f0e7}.home-top__ticker i{font-style:normal;color:#c0c8c5}.home-top__title{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:17px 0 14px}.home-top__title h1{margin:0;font-size:clamp(24px,3vw,34px);letter-spacing:-1px}.home-top__title p{margin:7px 0 0;color:var(--muted);font-size:13px}.home-top__title a{flex:0 0 auto;color:var(--ink);font-size:12px;text-decoration:none}.quick-plan{display:flex;overflow:hidden;border:1px solid #cbd3cf;border-radius:11px;background:#fff;box-shadow:0 8px 22px rgba(29,38,33,.05)}.quick-plan input{flex:1;min-width:0;padding:13px 14px;border:0;outline:0;background:transparent;color:var(--ink);font:13px var(--font-sans)}.quick-plan button,.home-empty button{border:0;background:#1e2925;color:#fff;padding:0 18px;font-size:12px;font-weight:650;cursor:pointer}.home-products{margin-top:20px}.home-products__head{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}.home-products__head h2{margin:0;font-size:17px}.home-products__head span{color:var(--muted);font-size:11px}.home-product-grid{grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}.home-loading{padding:36px;color:var(--muted);font-size:12px;text-align:center}.home-loading span{display:inline-block;width:8px;height:8px;margin-right:7px;border-radius:50%;background:#5d8877;animation:pulse 1.2s infinite}.home-empty{padding:36px;text-align:center;border:1px dashed var(--line);border-radius:12px}.home-empty h3{margin:0;font-size:17px}.home-empty p{color:var(--muted);font-size:12px}.home-empty button{height:34px;border-radius:8px}@media(max-width:700px){.visitor-home{padding-top:0}.home-top__title{align-items:start}.home-top__title p{line-height:1.6}.home-top__title a{padding-top:7px;white-space:nowrap}.quick-plan button{padding:0 13px}.home-product-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}@keyframes pulse{50%{transform:scale(.65);opacity:.4}}
</style>
