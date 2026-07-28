<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { TravelProduct } from '../../types'
const items = ref<TravelProduct[]>([]); const loading = ref(false); const error = ref(''); const form = reactive({ target_date: '', budget: '', interest: '', weather: 'RAIN' })
async function load() { loading.value = true; error.value = ''; try { const response = await visitorApi.products({ target_date: form.target_date || undefined, budget: form.budget || undefined, interest: form.interest || undefined, weather: form.weather }); items.value = response.data } catch (e) { error.value = errorMessage(e) } finally { loading.value = false } }
onMounted(load)
</script>
<template><div class="page-head"><div><div class="eyebrow">AVAILABLE EXPERIENCES</div><h1>当前可售套餐</h1><p>价格和余量来自酒店端确定性规则计算，库存紧张时会显示提醒。</p></div></div><div class="panel" style="margin-bottom:20px"><div class="form-grid"><el-form-item label="入住日期"><el-date-picker v-model="form.target_date" value-format="YYYY-MM-DD" type="date" placeholder="不限日期" style="width:100%" /></el-form-item><el-form-item label="天气偏好"><el-select v-model="form.weather" style="width:100%"><el-option label="雨天可用" value="RAIN" /><el-option label="晴天可用" value="SUNNY" /><el-option label="多云可用" value="CLOUDY" /></el-select></el-form-item><el-form-item label="预算上限"><el-input v-model="form.budget" placeholder="例如 700" /></el-form-item><el-form-item label="兴趣关键词"><el-input v-model="form.interest" placeholder="亲子 / 手工 / 茶文化" @keyup.enter="load" /></el-form-item></div><div class="form-actions"><el-button type="primary" @click="load">筛选套餐</el-button></div></div><el-alert v-if="error" :title="error" type="error" show-icon /><div v-if="loading" class="panel empty-state">正在匹配可售套餐…</div><div v-else-if="items.length" class="product-grid"><ProductCard v-for="product in items" :key="product.id" :product="product" public-view /></div><div v-else class="panel empty-state">没有符合条件的可售套餐，试试提高预算或放宽日期。</div></template>

