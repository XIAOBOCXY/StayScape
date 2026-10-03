<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import StatusTag from './StatusTag.vue'
import MediaImage from './MediaImage.vue'
import type { TravelProduct } from '../types'
import { experienceLabel, heroMedia, mediaForProduct, mediaForResource } from '../utils/productMedia'
import { useCountdown } from '../utils/countdown'

const props = defineProps<{ product: TravelProduct; publicView?: boolean; compact?: boolean; horizontal?: boolean }>()
const router = useRouter()
const countdown = useCountdown(() => props.product.target_date)
// The card shows the same image carousel as the detail page: the primary
// experience first, then the rest of the product's own photos.
const heroList = computed(() => {
  const focus = props.product.resources.find((item) => item.resource_type === 'PARTNER_RESOURCE') || props.product.resources[0]
  const primary = focus ? mediaForResource(props.product, focus) : heroMedia(props.product)
  const rest = mediaForProduct(props.product)
  return [primary, ...rest.filter((item) => item.id !== primary.id)].slice(0, 5)
})
const heroIndex = ref(0)
const media = computed(() => heroList.value[heroIndex.value] || heroList.value[0])
function moveHero(delta: number, event?: Event) {
  event?.stopPropagation()
  const total = heroList.value.length || 1
  heroIndex.value = (heroIndex.value + delta + total) % total
}
// 卡片主图支持触摸左右滑动；滑动后短时间内忽略点击，避免误进详情。
let cardTouchX = 0
let cardTouchY = 0
const swipeGuard = ref(0)
function onCardTouchStart(event: TouchEvent) {
  const point = event.changedTouches[0]
  cardTouchX = point.clientX
  cardTouchY = point.clientY
}
function onCardTouchEnd(event: TouchEvent) {
  if (heroList.value.length < 2) return
  const point = event.changedTouches[0]
  const dx = point.clientX - cardTouchX
  const dy = point.clientY - cardTouchY
  if (Math.abs(dx) < 36 || Math.abs(dx) < Math.abs(dy)) return
  swipeGuard.value = Date.now()
  const total = heroList.value.length
  heroIndex.value = (heroIndex.value + (dx < 0 ? 1 : -1) + total) % total
}
// Families read "2大1小" instead of "3 人套餐"; other crowds keep 人数.
const partySize = computed(() => Number(props.product.party_size || ({ FAMILY: 3, COUPLE: 2, FRIENDS: 4, SOLO: 1 }[props.product.target_crowd] || 2)))
const partyLabel = computed(() => {
  const size = partySize.value
  if (props.product.target_crowd === 'FAMILY' && size >= 3) {
    const children = Math.max(1, Math.floor((size - 1) / 2))
    const adults = Math.max(1, size - children)
    return `${adults}大${children}小`
  }
  return `${size} 人套餐`
})
const visibleResources = computed(() => props.product.resources.slice(0, 3))
const experienceResources = computed(() => props.product.resources.filter((item) => item.resource_type !== 'ROOM'))
// Every included experience is listed so a 上午+下午 package is visible on the card.
const cardExperiences = computed(() => experienceResources.value.slice(0, 3))
function slotLabel(resource: TravelProduct['resources'][number]) {
  const start = String(resource.start_time || '')
  const match = start.match(/^(\d{1,2}):(\d{2})/)
  if (!match) return experienceLabel(resource.resource_type)
  const minutes = Number(match[1]) * 60 + Number(match[2])
  if (minutes < 12 * 60) return '上午'
  if (minutes < 18 * 60) return '下午'
  return '晚上'
}
const locationLabel = computed(() => experienceResources.value.find((item) => item.address)?.address || '酒店内服务')
const dateLabel = computed(() => {
  const value = String(props.product.target_date || '')
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${Number(match[2])}月${Number(match[3])}日` : '日期以购买确认'
})
// Every package is anchored to hotel room nights, so the card states the
// length of stay instead of implying a single-day visit.
const stayLabel = computed(() => props.product.stay?.label || '2天1晚')
const checkOutLabel = computed(() => {
  const value = String(props.product.stay?.check_out || '')
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${Number(match[2])}月${Number(match[3])}日退房` : ''
})
function open() {
  if (Date.now() - swipeGuard.value < 350) return
  router.push(props.publicView ? `/visitor/products/${props.product.id}` : `/hotel/products/${props.product.id}`)
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open() }
}
</script>

<template>
  <article :class="['product-card', 'product-card--editorial', { 'product-card--compact': compact, 'product-card--horizontal': horizontal }]" tabindex="0" role="link" :aria-label="`查看${product.product_name}`" @click.stop="open" @keydown="onKeydown">
    <div class="product-card__media" @touchstart.passive="onCardTouchStart" @touchend.passive="onCardTouchEnd">
      <MediaImage :media="media" aspect="card" />
      <template v-if="heroList.length > 1 && !compact">
        <button type="button" class="card-hero-nav card-hero-nav--prev" aria-label="上一张图片" @click.stop="moveHero(-1, $event)">‹</button>
        <button type="button" class="card-hero-nav card-hero-nav--next" aria-label="下一张图片" @click.stop="moveHero(1, $event)">›</button>
        <span class="card-hero-dots"><i v-for="(_, index) in heroList" :key="index" :class="{ active: heroIndex === index }" @click.stop="heroIndex = index" /></span>
      </template>
    </div>
    <div class="product-card__body">
      <div v-if="!publicView" class="product-card__top">
        <StatusTag :status="product.status" />
      </div>
      <h3>{{ product.product_name }}</h3>
      <div class="product-card__facts">
        <span>{{ stayLabel }}</span><span>{{ dateLabel }}入住</span><span v-if="checkOutLabel">{{ checkOutLabel }}</span><span>{{ locationLabel }}</span>
      </div>
      <ul v-if="cardExperiences.length" class="product-card__experiences">
        <li v-for="resource in cardExperiences" :key="resource.id">
          <b>{{ slotLabel(resource) }}</b>
          <span>{{ resource.resource_name }}</span>
          <small v-if="resource.start_time">{{ String(resource.start_time).slice(0, 5) }}</small>
        </li>
      </ul>
      <div v-if="!cardExperiences.length" class="product-card__resources">
        <span v-for="resource in visibleResources" :key="resource.id"><b>{{ experienceLabel(resource.resource_type) }}</b> · {{ resource.resource_name }}</span>
      </div>
      <div class="product-card__bottom">
        <div><strong>¥{{ product.suggested_price }}</strong><span class="muted"> 起 / {{ partyLabel }}</span></div>
        <div class="product-card__sale">
          <span class="product-card__stock">余 {{ product.sale_quantity }} 席</span>
          <span v-if="countdown.remaining()" class="product-card__countdown" :class="{ expired: countdown.expired() }">
            {{ countdown.expired() ? '销售已截止' : `距结束 ${countdown.remaining()}` }}
          </span>
        </div>
      </div>
    </div>
  </article>
</template>
