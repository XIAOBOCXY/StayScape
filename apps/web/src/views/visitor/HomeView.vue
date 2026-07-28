<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { TravelProduct } from '../../types'
const products = ref<TravelProduct[]>([]); const loading = ref(true); const error = ref('')
onMounted(async () => { try { products.value = (await visitorApi.products()).data.slice(0, 3) } catch (e) { error.value = errorMessage(e) } finally { loading.value = false } })
</script>
<template><section class="visitor-hero"><div><div class="eyebrow">STAYSCAPE · HANGZHOU</div><h1>把一间余房，变成一段杭州体验</h1><p>不只是清库存。我们把临期客房、酒店服务和城市文化，重新组合成一套会随天气与名额变化而自我调整的主题住宿产品。</p><div class="visitor-hero-actions"><van-button type="primary" size="large" @click="$router.push('/visitor/recommend')">获取个性化推荐</van-button><el-button size="large" plain @click="$router.push('/visitor/products')">浏览全部套餐</el-button></div></div></section><div class="section-title"><h2>此刻值得住</h2><span>真实库存 · 实时毛利校验</span></div><div v-if="loading" class="panel empty-state">正在读取当前可售套餐…</div><el-alert v-else-if="error" :title="error" type="error" /><div v-else-if="products.length" class="product-grid"><ProductCard v-for="product in products" :key="product.id" :product="product" public-view /></div><div v-else class="panel empty-state">当前暂无可售套餐，稍后再来看看。</div><div class="section-title"><h2>StayScape怎么工作</h2></div><div class="metric-grid"><div class="panel"><div class="eyebrow">01 · INVENTORY</div><h3>从一间临期客房开始</h3><p class="muted">酒店维护真实房量、服务和最低毛利率。</p></div><div class="panel"><div class="eyebrow">02 · EXPERIENCE</div><h3>加入一段杭州文化</h3><p class="muted">合作商户提供日期、场次和实时可用名额。</p></div><div class="panel"><div class="eyebrow">03 · DYNAMIC</div><h3>资源变化自动重算</h3><p class="muted">名额从12变4，产品就从4套变1套。</p></div><div class="panel"><div class="eyebrow">04 · INTENT</div><h3>先提交预约意向</h3><p class="muted">比赛版本不支付，给酒店一个真实可跟进的线索。</p></div></div></template>
