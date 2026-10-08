<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import MediaImage from './MediaImage.vue'
import type { TravelProduct } from '../types'
import { primaryProductMedia } from '../utils/productMedia'

const props = defineProps<{ product: TravelProduct }>()
const router = useRouter()
const media = computed(() => primaryProductMedia(props.product))
const quantity = computed(() => Math.max(0, Number(props.product.sale_quantity || 0)))
const paused = computed(() => ['PAUSED', 'SUSPENDED'].includes(String(props.product.status || '').toUpperCase()))
const sellable = computed(() => ['ON_SALE', 'LOW_STOCK', 'AVAILABLE'].includes(String(props.product.status || '').toUpperCase()) && quantity.value > 0)
const lowStock = computed(() => sellable.value && (String(props.product.status || '').toUpperCase() === 'LOW_STOCK' || quantity.value <= 2))
const statusText = computed(() => paused.value ? '已暂停' : sellable.value ? (lowStock.value ? '库存紧张' : '在售') : '已下架')
const statusClass = computed(() => paused.value ? 'is-paused' : sellable.value ? (lowStock.value ? 'is-low' : 'is-on-sale') : 'is-off-shelf')
const dateText = computed(() => {
  const match = String(props.product.target_date || '').match(/^\d{4}-(\d{2})-(\d{2})$/)
  return match ? `${Number(match[1])}月${Number(match[2])}日` : '日期待定'
})
const stayText = computed(() => props.product.stay?.label || '套餐行程')
const partyText = computed(() => {
  const size = Math.max(1, Number(props.product.party_size || 2))
  if (props.product.target_crowd === 'FAMILY' && size >= 3) {
    const children = Math.max(1, Math.floor((size - 1) / 2))
    return `${size - children}大${children}小`
  }
  return `${size}人`
})
const remainingDays = computed(() => {
  const target = String(props.product.target_date || '').match(/^\d{4}-\d{2}-\d{2}$/)?.[0]
  if (!target) return 0
  const end = new Date(`${target}T23:59:59`).getTime()
  return Math.max(0, Math.ceil((end - Date.now()) / 86400000))
})
const saleText = computed(() => sellable.value ? `余${quantity.value}套 · 距结束${remainingDays.value}天` : '')
const benefitLabels = computed(() => {
  const nights = Math.max(1, Number(props.product.stay?.nights || 1))
  return [...new Set((props.product.resources || []).map((resource) => {
    const count = Math.max(1, Number(resource.quantity_per_package || 1))
    if (resource.resource_type === 'ROOM') return `${resource.resource_name} ${nights}晚`
    return count > 1 ? `${resource.resource_name} ×${count}` : resource.resource_name
  }).filter(Boolean))]
})
function open() { void router.push(`/hotel/products/${props.product.id}`) }
</script>

<template>
  <article class="dashboard-product-card" tabindex="0" role="link" :aria-label="`查看${product.product_name}，${statusText}`" @click="open" @keydown.enter.prevent="open" @keydown.space.prevent="open">
    <div class="dashboard-product-card__image"><MediaImage :media="media" aspect="card" /></div>
    <div class="dashboard-product-card__body">
      <span class="dashboard-product-card__status" :class="statusClass">{{ statusText }}</span>
      <h3 :title="product.product_name">{{ product.product_name }}</h3>
      <p class="dashboard-product-card__meta">{{ dateText }} · {{ stayText }} · {{ partyText }}</p>
      <div class="dashboard-product-card__benefits" aria-label="套餐权益">
        <span v-for="benefit in benefitLabels.slice(0, 2)" :key="benefit">{{ benefit }}</span>
        <span v-if="benefitLabels.length > 2" class="dashboard-product-card__more">+{{ benefitLabels.length - 2 }}</span>
      </div>
      <div class="dashboard-product-card__bottom">
        <div class="dashboard-product-card__price"><strong>¥{{ product.suggested_price }}</strong><small>/ 套</small></div>
        <span v-if="saleText" class="dashboard-product-card__sale">{{ saleText }}</span>
        <span v-else aria-hidden="true" class="dashboard-product-card__sale-placeholder"></span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.dashboard-product-card { display: grid; min-width: 0; min-height: 156px; grid-template-columns: 126px minmax(0, 1fr); overflow: hidden; border: 1px solid #e4e9e5; border-radius: 11px; background: #fff; color: #202120; cursor: pointer; transition: box-shadow .18s ease, border-color .18s ease, transform .18s ease; }
.dashboard-product-card:hover { transform: translateY(-2px); border-color: #b9c9c0; box-shadow: 0 10px 24px rgba(25, 48, 38, .08); }
.dashboard-product-card:focus-visible { outline: 2px solid #698278; outline-offset: 3px; }
.dashboard-product-card__image { width: 126px; min-height: 156px; overflow: hidden; background: #eceeeb; }
.dashboard-product-card__image :deep(.media-image) { width: 100%; height: 100%; min-height: 156px; aspect-ratio: auto; border-radius: 0; }
.dashboard-product-card__image :deep(img) { width: 100%; height: 100%; object-fit: cover; }
.dashboard-product-card__body { display: flex; min-width: 0; min-height: 0; flex-direction: column; gap: 4px; padding: 10px 13px 9px; }
.dashboard-product-card__status { display: inline-flex; width: fit-content; min-height: 19px; align-items: center; padding: 1px 7px; border-radius: 6px; font-size: 11px; line-height: 1.3; }
.dashboard-product-card__status.is-on-sale { background: #edf4ee; color: #52775d; }
.dashboard-product-card__status.is-low { background: #f7f1e6; color: #a2753b; }
.dashboard-product-card__status.is-paused { background: #f0f1ef; color: #747873; }
.dashboard-product-card__status.is-off-shelf { background: #f1efee; color: #8a7772; }
.dashboard-product-card h3 { display: -webkit-box; margin: 0; overflow: hidden; color: #262725; font-size: 15px; font-weight: 650; line-height: 1.4; text-overflow: ellipsis; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.dashboard-product-card__meta { display: block; margin: 0; overflow: visible; color: #777b77; font-size: 11.5px; line-height: 1.45; overflow-wrap: anywhere; white-space: normal; }
.dashboard-product-card__benefits { display: flex; min-height: 21px; flex-wrap: wrap; gap: 5px; overflow: hidden; }
.dashboard-product-card__benefits span { max-width: 48%; overflow: hidden; padding: 3px 7px; border-radius: 999px; background: #f0f2ef; color: #5f6862; font-size: 11px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.dashboard-product-card__benefits .dashboard-product-card__more { max-width: unset; background: transparent; color: #838781; }
.dashboard-product-card__bottom { display: flex; min-width: 0; min-height: 34px; flex-direction: row; align-items: baseline; justify-content: space-between; gap: 10px; margin-top: auto; padding-top: 6px; border-top: 1px solid #edf0ed; }
.dashboard-product-card__price { display: flex; align-items: baseline; gap: 4px; white-space: nowrap; }
.dashboard-product-card__price strong { color: #34413d; font-size: 18px; font-weight: 680; line-height: 1.25; }
.dashboard-product-card__price small { color: #747973; font-size: 12px; }
.dashboard-product-card__sale { margin-left: auto; color: #747973; font-size: 11.5px; line-height: 1.4; text-align: right; white-space: nowrap; }
.dashboard-product-card__sale-placeholder { display: none; }
@media (max-width: 760px) { .dashboard-product-card { grid-template-columns: 104px minmax(0, 1fr); min-height: 146px; }.dashboard-product-card__image,.dashboard-product-card__image :deep(.media-image){min-height:146px}.dashboard-product-card__body{padding:9px}.dashboard-product-card__bottom{gap:6px}.dashboard-product-card__sale{font-size:10.5px} }
@media (max-width: 420px) { .dashboard-product-card { grid-template-columns: 88px minmax(0, 1fr); min-height: 136px; }.dashboard-product-card__image,.dashboard-product-card__image :deep(.media-image){min-height:136px}.dashboard-product-card__benefits span{font-size:10px;padding:2px 5px}.dashboard-product-card__price strong{font-size:16px} }
</style>
