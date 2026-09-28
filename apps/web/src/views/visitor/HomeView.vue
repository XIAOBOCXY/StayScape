<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { TravelProduct } from '../../types'

const products = ref<TravelProduct[]>([])
const loading = ref(true)
const error = ref('')
const quickText = ref('')
const router = useRouter()
const dateHint = computed(() => products.value.length ? `${products.value.length} 组在售套餐` : '杭州精选旅居')
const experienceCount = computed(() => products.value.reduce((total, product) => total + product.resources.filter((item) => item.resource_type !== 'ROOM').length, 0))
const locationCount = computed(() => new Set(products.value.flatMap((product) => product.resources.map((item) => item.address).filter(Boolean))).size)
const dateRange = computed(() => {
  const dates = products.value.map((product) => product.target_date).filter(Boolean).sort()
  if (!dates.length) return '9月下旬'
  const format = (value: string) => {
    const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
    return match ? `${Number(match[2])}月${Number(match[3])}日` : value
  }
  return dates[0] === dates[dates.length - 1] ? format(dates[0]) : `${format(dates[0])}—${format(dates[dates.length - 1])}`
})
const topics = ['博物馆', '亲子', '夜游', '美食', '旅拍', '运动']
// 同一套餐有多个出行日期时，首页只保留最近的一天，避免重复商品刷屏。
const visibleProducts = computed(() => {
  const byTheme = new Map<string, TravelProduct>()
  const today = new Date().toISOString().slice(0, 10)
  for (const item of products.value) {
    const key = item.theme || item.product_name
    const current = byTheme.get(key)
    const score = (value: TravelProduct) => (value.target_date >= today ? `0${value.target_date}` : `1${value.target_date}`)
    if (!current || score(item) < score(current)) byTheme.set(key, item)
  }
  return [...byTheme.values()].sort((a, b) => String(a.target_date).localeCompare(String(b.target_date))).slice(0, 12)
})

async function load() {
  loading.value = true
  error.value = ''
  try { products.value = (await visitorApi.products({ compact: true })).data }
  catch (e) { error.value = errorMessage(e) }
  finally { loading.value = false }
}
function startPlan() {
  router.push({ path: '/visitor/products', query: quickText.value.trim() ? { interest: quickText.value.trim() } : undefined })
}

onMounted(load)
</script>

<template>
  <main class="visitor-home storefront-home">
    <section class="home-top">
      <div class="home-top__ticker"><span /> {{ dateHint }}<i>·</i><b>{{ dateRange }}</b><em>价格与余量按团期更新</em></div>
      <div class="home-top__title">
        <div><small class="home-top__eyebrow">STAYSCAPE · HANGZHOU</small><h1>杭州住宿 + 在地体验</h1><p>{{ dateRange }}可订 · 全部商品含住宿</p></div>
        <router-link to="/visitor/products">全部商品 <span>→</span></router-link>
      </div>
      <div class="quick-plan"><span class="quick-plan__mark">⌕</span><input v-model="quickText" placeholder="搜索博物馆、亲子、夜游或具体地点" @keyup.enter="startPlan" /><button @click="startPlan">查找</button></div>
      <div class="home-topics"><span>主题</span><button v-for="topic in topics" :key="topic" @click="quickText = topic; startPlan()">{{ topic }}</button></div>
    </section>

    <section class="home-overview" aria-label="商品概览"><div><strong>{{ products.length }}</strong><span>在售套餐</span></div><div><strong>{{ experienceCount }}</strong><span>项在地体验</span></div><div><strong>{{ locationCount || '—' }}</strong><span>个体验地点</span></div><div><strong>{{ dateRange }}</strong><span>可选团期</span></div></section>

    <section class="home-products"><div class="home-products__head"><div><small>精选商品</small><h2>在售套餐</h2></div><router-link to="/visitor/products">筛选全部 <span>→</span></router-link></div><div v-if="loading" class="home-loading"><span /> 正在加载商品…</div><el-alert v-else-if="error" :title="error" type="error" show-icon /><div v-else-if="products.length" class="product-grid product-grid--editorial home-product-grid"><ProductCard v-for="product in visibleProducts" :key="product.id" :product="product" public-view /></div><div v-else class="home-empty"><h3>暂时没有符合条件的套餐</h3><p>换一个日期或主题再试。</p><button @click="$router.push('/visitor/products')">查看商品</button></div><router-link v-if="products.length > visibleProducts.length" class="home-more" to="/visitor/products">查看全部 {{ products.length }} 组商品 →</router-link></section>
  </main>
</template>

<style scoped>
.visitor-home{max-width:1180px;margin:0 auto;padding:8px 0 48px}.home-top{padding:14px 0 20px;border-bottom:1px solid var(--line)}.home-top__ticker{display:flex;align-items:center;gap:7px;color:var(--muted);font-family:var(--font-mono);font-size:10px}.home-top__ticker span{width:6px;height:6px;border-radius:50%;background:#4e8f72;box-shadow:0 0 0 4px #e0f0e7}.home-top__ticker i{font-style:normal;color:#c0c8c5}.home-top__title{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:17px 0 14px}.home-top__title h1{margin:0;font-size:clamp(24px,3vw,34px);letter-spacing:-1px}.home-top__title p{margin:7px 0 0;color:var(--muted);font-size:13px}.home-top__title a{flex:0 0 auto;color:var(--ink);font-size:12px;text-decoration:none}.quick-plan{display:flex;overflow:hidden;border:1px solid #cbd3cf;border-radius:11px;background:#fff;box-shadow:0 8px 22px rgba(29,38,33,.05)}.quick-plan input{flex:1;min-width:0;padding:13px 14px;border:0;outline:0;background:transparent;color:var(--ink);font:13px var(--font-sans)}.quick-plan button,.home-empty button{border:0;background:#1e2925;color:#fff;padding:0 18px;font-size:12px;font-weight:650;cursor:pointer}.home-products{margin-top:20px}.home-products__head{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}.home-products__head h2{margin:0;font-size:17px}.home-products__head span{color:var(--muted);font-size:11px}.home-product-grid{grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}.home-loading{padding:36px;color:var(--muted);font-size:12px;text-align:center}.home-loading span{display:inline-block;width:8px;height:8px;margin-right:7px;border-radius:50%;background:#5d8877;animation:pulse 1.2s infinite}.home-empty{padding:36px;text-align:center;border:1px dashed var(--line);border-radius:12px}.home-empty h3{margin:0;font-size:17px}.home-empty p{color:var(--muted);font-size:12px}.home-empty button{height:34px;border-radius:8px}@media(max-width:700px){.visitor-home{padding-top:0}.home-top__title{align-items:start}.home-top__title p{line-height:1.6}.home-top__title a{padding-top:7px;white-space:nowrap}.quick-plan button{padding:0 13px}.home-product-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}@keyframes pulse{50%{transform:scale(.65);opacity:.4}}
</style>


<style scoped>
/* Rich storefront home: show the facts a traveller needs before opening a product. */
.storefront-home { width: min(1280px, 100%); max-width: 1280px; margin: 0 auto; padding: 0 0 54px; background: #fff; color: #252525; }
.storefront-home .home-top { padding: 16px 20px 18px; border-bottom: 1px solid #eee9e4; background: #fff; }
.storefront-home .home-top__ticker { color: #999; font-size: 10px; }
.storefront-home .home-top__ticker b { color: #666; font-weight: 600; }
.storefront-home .home-top__ticker em { color: #aaa; font-style: normal; }
.storefront-home .home-top__title { align-items: flex-end; margin: 24px 0 20px; }
.storefront-home .home-top__eyebrow { color: #ff6a00; font-size: 10px; letter-spacing: .14em; }
.storefront-home .home-top__title h1 { margin: 8px 0 8px; color: #222; font-size: clamp(25px, 4vw, 36px); font-weight: 750; letter-spacing: -.8px; line-height: 1.2; }
.storefront-home .home-top__title p { max-width: 560px; margin: 0; color: #777; font-size: 13px; line-height: 1.65; }
.storefront-home .home-top__title a, .storefront-home .home-products__head > a { flex: 0 0 auto; color: #ff6a00; font-size: 12px; }
.storefront-home .home-top__title a span, .storefront-home .home-products__head a span { margin-left: 4px; font-size: 15px; }
.storefront-home .quick-plan { height: 44px; border: 1px solid #dcd6d0; border-radius: 4px; box-shadow: none; }
.storefront-home .quick-plan__mark { display: flex; align-items: center; justify-content: center; line-height: 1;  flex: 0 0 auto; padding-left: 13px; color: #ff6a00; font-size: 20px; line-height: 1; }
.storefront-home .quick-plan input { padding: 12px 10px; font-size: 12px; }
.storefront-home .quick-plan button { padding: 0 20px; background: #ff6a00; font-size: 12px; }
.storefront-home .home-topics { display: flex; align-items: center; gap: 17px; margin-top: 15px; overflow-x: auto; }
.storefront-home .home-topics > span { flex: 0 0 auto; color: #999; font-size: 11px; }
.storefront-home .home-topics button { flex: 0 0 auto; padding: 0 0 3px; border: 0; border-bottom: 1px solid transparent; background: none; color: #555; font-size: 11px; }
.storefront-home .home-topics button:hover { border-bottom-color: #ff6a00; color: #ff6a00; }
.storefront-home .home-overview { display: grid; grid-template-columns: repeat(4, 1fr); margin: 0; padding: 17px 20px; border-bottom: 8px solid #f5f5f5; background: #fff; }
.storefront-home .home-overview > div { min-width: 0; padding: 0 15px; border-right: 1px solid #eee9e4; }
.storefront-home .home-overview > div:first-child { padding-left: 0; }
.storefront-home .home-overview > div:last-child { padding-right: 0; border-right: 0; }
.storefront-home .home-overview strong { display: block; overflow: hidden; color: #ff6a00; font-family: var(--font-mono); font-size: 20px; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
.storefront-home .home-overview span { display: block; margin-top: 4px; color: #999; font-size: 10px; }
.storefront-home .home-products { margin: 0; padding: 24px 20px 0; }
.storefront-home .home-products__head { align-items: flex-end; margin: 0 0 15px; }
.storefront-home .home-products__head small { color: #ff6a00; font-size: 10px; letter-spacing: .12em; }
.storefront-home .home-products__head h2 { margin: 5px 0 4px; color: #222; font-size: 21px; }
.storefront-home .home-products__head p { margin: 0; color: #999; font-size: 11px; }
.storefront-home .home-product-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.storefront-home .home-more { display: block; width: max-content; margin: 25px auto 0; padding-bottom: 3px; border-bottom: 1px solid #ff6a00; color: #ff6a00; font-size: 12px; }
@media (max-width: 1000px) {
  .storefront-home .home-product-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 820px) {
  .storefront-home .home-product-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .storefront-home .home-top { padding: 13px 14px 16px; }
  .storefront-home .home-top__ticker em { display: none; }
  .storefront-home .home-top__title { margin: 20px 0 16px; }
  .storefront-home .home-top__title h1 { font-size: 26px; }
  .storefront-home .home-top__title p { font-size: 12px; }
  .storefront-home .home-top__title a { padding-bottom: 4px; font-size: 11px; }
  .storefront-home .home-overview { padding: 14px; }
  .storefront-home .home-overview > div { padding: 0 8px; }
  .storefront-home .home-overview > div:first-child { padding-left: 0; }
  .storefront-home .home-overview > div:last-child { padding-right: 0; }
  .storefront-home .home-overview strong { font-size: 15px; }
  .storefront-home .home-overview span { font-size: 9px; }
  .storefront-home .home-products { padding: 20px 14px 0; }
  .storefront-home .home-products__head h2 { font-size: 19px; }
  .storefront-home .home-products__head p { font-size: 10px; }
  .storefront-home .home-product-grid { grid-template-columns: 1fr; gap: 10px; }
}
</style>
