<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
const items = ref<Array<Record<string, any>>>([]); const loading = ref(false)
async function load() { loading.value = true; try { items.value = (await hotelApi.changes()).data } catch (e) { errorMessage(e) } finally { loading.value = false } }
onMounted(load)
</script>

<template>
  <div class="page-head"><div><div class="eyebrow">DYNAMIC OPERATIONS</div><h1>动态运营中心</h1><p>一条资源变化事件，会记录影响范围、调整前后数量以及最终处理动作。</p></div><el-button plain @click="load">刷新</el-button></div>
  <div class="panel"><div v-if="loading" class="empty-state">正在读取调整事件…</div><div v-else-if="!items.length" class="empty-state">暂无资源变化事件</div><div v-for="item in items" :key="item.id" class="timeline-item"><div class="timeline-dot" /><div class="timeline-content"><div class="product-card__top"><strong>{{ item.event_type }}</strong><span class="muted">{{ String(item.created_at).replace('T',' ').slice(0,16) }}</span></div><p class="muted">{{ item.reason }}</p><div v-if="item.processing_result?.affectedProducts?.length" class="adjustment-grid"><div v-for="adjustment in item.processing_result.affectedProducts" :key="adjustment.product_id" class="panel" style="box-shadow:none;background:#f8fbf9"><strong>{{ adjustment.product_name }}</strong><div style="margin-top:8px"><span class="old-number">{{ adjustment.old_quantity }}</span><span class="arrow">→</span><span class="new-number">{{ adjustment.new_quantity }}</span> 套 <StatusTag :status="adjustment.status" /></div><p class="muted">{{ adjustment.reason }}</p></div></div><pre v-else class="json-preview">{{ JSON.stringify(item.new_value, null, 2) }}</pre></div></div></div>
</template>

<style scoped>.timeline-item{display:flex;gap:16px;padding:0 0 24px;position:relative}.timeline-item:not(:last-child)::before{content:'';position:absolute;left:5px;top:13px;bottom:0;width:1px;background:#d9e9e1}.timeline-dot{width:11px;height:11px;border-radius:50%;background:#0f766e;border:3px solid #d8eee5;flex:0 0 11px;margin-top:3px}.timeline-content{flex:1}.adjustment-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.old-number{color:#9caeaa;font-size:22px;font-weight:700}.new-number{color:#0f766e;font-size:22px;font-weight:700}.arrow{margin:0 8px;color:#9caeaa}.json-preview{font-size:11px;white-space:pre-wrap;color:#5f736d;background:#f7faf8;padding:12px;border-radius:8px}@media(max-width:700px){.adjustment-grid{grid-template-columns:1fr}}</style>

