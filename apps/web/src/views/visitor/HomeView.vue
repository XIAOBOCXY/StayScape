<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import MediaImage from '../../components/MediaImage.vue'
import type { TravelProduct } from '../../types'
import { heroMedia } from '../../utils/productMedia'

const products = ref<TravelProduct[]>([])
const loading = ref(true)
const error = ref('')
const hero = computed(() => heroMedia(products.value[0]))
const todayLabel = computed(() => new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date()))
const weatherMood = computed(() => ({ RAIN: '雨天也值得出发', SUNNY: '杭州晴日正好', CLOUDY: '多云，适合灵活组合' }[products.value[0]?.weather || 'RAIN'] || '杭州，今晚见'))

async function load() {
  loading.value = true
  error.value = ''
  try { products.value = (await visitorApi.products()).data }
  catch (e) { error.value = errorMessage(e) }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="visitor-home">
    <section class="home-hero">
      <MediaImage :media="hero" aspect="hero" />
      <div class="home-hero__veil" />
      <div class="home-hero__content">
        <div class="eyebrow home-eyebrow">STAYSCAPE · HANGZHOU / {{ todayLabel }}</div>
        <h1>把一间未被预订的房，<br /><em>变成今晚值得发生的杭州故事。</em></h1>
        <p>住下来，吃一顿早餐，走进一段城市文化。每套体验都根据今天的天气、时间和真实余量重新组合。</p>
        <div class="visitor-hero-actions">
          <van-button type="primary" size="large" @click="$router.push('/visitor/products')">探索今晚 <span>→</span></van-button>
          <el-button size="large" plain @click="$router.push('/visitor/recommend')">告诉我想怎么玩</el-button>
        </div>
      </div>
      <div class="home-hero__aside"><span>01</span><i /><span>STAY<br />SCAPE</span></div>
    </section>

    <section class="tonight-strip">
      <div class="tonight-title"><div class="eyebrow">HANGZHOU THIS WEEKEND</div><h2>今天想去哪里？</h2><p>不赶景点，先挑一段适合此刻的杭州时光。</p></div>
      <div class="tonight-fact"><span class="fact-icon">✦</span><div><small>WEEKEND MOOD</small><strong>把时间留给喜欢的地方</strong></div></div>
      <div class="tonight-fact"><span class="fact-icon">⌂</span><div><small>HANGZHOU IDEAS</small><strong>多种玩法，慢慢挑</strong></div></div>
      <div class="tonight-audiences"><span>FAMILY</span><span>COUPLE</span><span>LOCAL WEEKEND</span></div>
    </section>

    <section class="home-section">
      <div class="editorial-heading"><div><div class="eyebrow">CURATED FOR THIS MOMENT</div><h2>今晚住哪一段杭州？</h2></div><router-link to="/visitor/products">查看全部 <span>↗</span></router-link></div>
      <div v-if="loading" class="home-loading"><span /> 正在寻找今天想去的杭州体验…</div>
      <el-alert v-else-if="error" :title="error" type="error" show-icon />
      <div v-else-if="products.length" class="product-grid product-grid--editorial"><ProductCard v-for="product in products.slice(0, 12)" :key="product.id" :product="product" public-view /></div>
      <div v-else class="home-empty"><div class="empty-mark">S</div><h3>新的杭州玩法正在准备</h3><p>准备好后会出现在这里。你也可以先告诉我们想怎么玩。</p><el-button type="primary" plain @click="$router.push('/visitor/recommend')">先获取个性化推荐</el-button></div>
    </section>

    <section class="story-band">
      <div><div class="eyebrow">THE STAYSCAPE IDEA</div><h2>不把雨天当作<br /><em>行程的暂停键。</em></h2></div>
      <p>从西湖晨走到良渚看展，从亲子乐园到城市夜游。挑一段想去的杭州时光，慢慢安排在周末。</p>
    </section>

    <section class="home-section home-section--small">
      <div class="editorial-heading"><div><div class="eyebrow">HOW IT FEELS</div><h2>一晚，三个瞬间</h2></div></div>
      <div class="moment-row"><div><span>01</span><strong>入住</strong><p>先把行李放下，让节奏慢下来。</p></div><div><span>02</span><strong>出发</strong><p>看展、逛乐园，或沿江边骑一段路。</p></div><div><span>03</span><strong>回到房间</strong><p>带着一件自己完成的东西入睡。</p></div></div>
    </section>
  </div>
</template>
