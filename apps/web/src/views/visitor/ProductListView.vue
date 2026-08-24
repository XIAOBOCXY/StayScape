<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { TravelProduct } from '../../types'

const items = ref<TravelProduct[]>([])
const loading = ref(false)
const error = ref('')
const form = reactive({ target_date: '', budget: '', interest: '', weather: '' })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await visitorApi.products({ target_date: form.target_date || undefined, budget: form.budget || undefined, interest: form.interest || undefined, weather: form.weather || undefined })
    items.value = response.data
  } catch (e) { error.value = errorMessage(e) }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page-head visitor-list-head"><div><div class="eyebrow">LIVE HANGZHOU STAYS</div><h1>今天，住进一段杭州</h1><p>住一晚，也把一段想去的杭州装进周末。博物馆、乐园、看展、运动与城市夜晚，都可以成为这趟小旅行的开场。</p></div><div class="editorial-page-mark">SCROLL<br /><span>↓</span></div></div>
  <div class="experience-filter"><div class="filter-intro"><span class="eyebrow">FIND YOUR MOMENT</span><strong>筛选今晚的心情</strong></div><el-date-picker v-model="form.target_date" value-format="YYYY-MM-DD" type="date" placeholder="入住日期" /><el-select v-model="form.weather" placeholder="天气偏好" clearable><el-option label="雨天室内" value="RAIN" /><el-option label="晴天漫游" value="SUNNY" /><el-option label="多云轻旅" value="CLOUDY" /></el-select><el-input v-model="form.budget" placeholder="预算上限 ¥700" /><el-input v-model="form.interest" placeholder="想玩什么？如博物馆、乐园、看展、运动" @keyup.enter="load" /><el-button type="primary" @click="load">寻找体验</el-button></div>
  <el-alert v-if="error" :title="error" type="error" show-icon />
  <div v-if="loading" class="home-loading"><span /> 正在挑选适合的杭州玩法…</div>
  <div v-else-if="items.length" class="product-grid product-grid--editorial product-grid--wide"><ProductCard v-for="product in items" :key="product.id" :product="product" public-view /></div>
  <div v-else class="home-empty"><div class="empty-mark">S</div><h3>还没有完全符合筛选条件的体验</h3><p>试试放宽日期或预算，也可以用自然语言告诉我们你想怎么度过今晚。</p><div><el-button type="primary" @click="$router.push('/visitor/recommend')">让旅居助手帮你找</el-button><el-button plain @click="form.target_date=''; form.budget=''; form.interest=''; form.weather=''; load()">清除筛选</el-button></div></div>
</template>
