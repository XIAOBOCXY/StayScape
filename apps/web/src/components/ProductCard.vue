<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import StatusTag from './StatusTag.vue'
import MediaImage from './MediaImage.vue'
import type { TravelProduct } from '../types'
import { experienceLabel, mediaForProduct, primaryProductMedia } from '../utils/productMedia'
import { useCountdown } from '../utils/countdown'
import { visitorApi } from '../api'

const props = withDefaults(defineProps<{ product: TravelProduct; publicView?: boolean; compact?: boolean; horizontal?: boolean; recommendation?: string; recommendationNote?: string; recommendationTags?: string[]; recommendationTitle?: string }>(), { recommendationTags: () => [], recommendationTitle: '为什么适合你' })
const router = useRouter()
const countdown = useCountdown(() => props.product.target_date)
const includedResources = computed(() => props.product.resources || [])
const heroList = computed(() => {
  const primary = primaryProductMedia(props.product)
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
  heroIndex.value = (heroIndex.value + (dx < 0 ? 1 : -1) + heroList.value.length) % heroList.value.length
}
const partySize = computed(() => Number(props.product.party_size || ({ FAMILY: 3, COUPLE: 2, FRIENDS: 4, SOLO: 1 }[props.product.target_crowd] || 2)))
const unavailable = computed(() => Number(props.product.sale_quantity || 0) <= 0)
const partyLabel = computed(() => {
  const size = partySize.value
  if (props.product.target_crowd === 'FAMILY' && size >= 3) {
    const children = Math.max(1, Math.floor((size - 1) / 2))
    return `${size - children}大${children}小`
  }
  return `${size} 人`
})
const soldOutLabel = computed(() => dateLabel.value ? dateLabel.value.replace(/入住$/, '已售罄') : '该日期已售罄')
const hasOtherAvailableDate = ref(false)
watch(
  () => [props.publicView, props.product.id, unavailable.value] as const,
  async ([isPublic, productId, soldOut]) => {
    hasOtherAvailableDate.value = false
    if (!isPublic || props.compact || !soldOut) return
    try {
      const response = await visitorApi.productDates(Number(productId))
      if (Number(productId) !== Number(props.product.id)) return
      hasOtherAvailableDate.value = response.data.dates.some((item) => Number(item.id) !== Number(productId) && Number(item.sale_quantity) > 0)
    } catch {
      hasOtherAvailableDate.value = false
    }
  },
  { immediate: true },
)
const crowdLabel = computed(() => ({ FAMILY: '亲子出行', COUPLE: '双人同游', FRIENDS: '好友结伴', SOLO: '一个人慢游' } as Record<string, string>)[String(props.product.target_crowd || '')] || '城市旅行')
const packageLabels = computed(() => {
  const room = includedResources.value.find((resource) => resource.resource_type === 'ROOM')
  const labels = includedResources.value.filter((resource) => resource.resource_type !== 'ROOM').map((resource) => {
    const quantity = Number(resource.quantity_per_package || 1)
    return quantity > 1 ? `${resource.resource_name} ×${quantity}` : resource.resource_name
  })
  return [...(room ? [`${room.resource_name} ${props.product.stay?.nights || 1}晚`] : []), ...new Set(labels)]
})
const marketingLine = computed(() => String(props.product.marketing_title || '').trim() || `${crowdLabel.value} · ${props.product.theme || '杭州周末体验'}`)
const dateLabel = computed(() => {
  const value = String(props.product.target_date || '')
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${Number(match[2])}月${Number(match[3])}日入住` : ''
})
const stayLabel = computed(() => props.product.stay?.label || '2天1晚')
const checkOutLabel = computed(() => {
  const value = String(props.product.stay?.check_out || '')
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${Number(match[2])}月${Number(match[3])}日退房` : ''
})
const visibleResources = computed(() => includedResources.value.slice(0, 3))
function open() {
  if (Date.now() - swipeGuard.value < 350) return
  router.push(props.publicView ? `/visitor/products/${props.product.id}` : `/hotel/products/${props.product.id}`)
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open() }
}
</script>

<template>
  <article :class="['product-card', 'product-card--editorial', { 'product-card--compact': compact, 'product-card--horizontal': horizontal, 'product-card--storefront': publicView && !compact, 'product-card--unavailable': publicView && !compact && unavailable, 'product-card--recommendation': Boolean(recommendation) }]" tabindex="0" role="link" :aria-label="`查看${product.product_name}${unavailable ? '，' + soldOutLabel : ''}`" @click.stop="open" @keydown="onKeydown">
    <div class="product-card__media" @touchstart.passive="onCardTouchStart" @touchend.passive="onCardTouchEnd">
      <MediaImage :media="media" aspect="card" />
      <template v-if="heroList.length > 1 && !compact">
        <button type="button" class="card-hero-nav card-hero-nav--prev" aria-label="上一张图片" @click.stop="moveHero(-1, $event)">‹</button>
        <button type="button" class="card-hero-nav card-hero-nav--next" aria-label="下一张图片" @click.stop="moveHero(1, $event)">›</button>
        <span class="card-hero-dots"><i v-for="(_, index) in heroList" :key="index" :class="{ active: heroIndex === index }" @click.stop="heroIndex = index" /></span>
      </template>
    </div>

    <div class="product-card__body">
      <div v-if="!publicView" class="product-card__top"><StatusTag :status="product.status" /></div>
      <h3>{{ product.product_name }}</h3>
      <div v-if="compact && recommendation" class="product-card__recommendation-meta">
        <span v-if="dateLabel">{{ dateLabel.replace('入住', '') }}</span><span>{{ stayLabel }}</span><span>{{ partyLabel }}同行</span>
      </div>

      <template v-if="publicView">
        <p v-if="!compact" class="product-card__hook">{{ marketingLine }}</p>
        <div v-if="!compact" class="product-card__audience">{{ crowdLabel }} · {{ partyLabel }}同行 · {{ stayLabel }}<template v-if="dateLabel"> · {{ dateLabel }}</template></div>
        <div class="product-card__inclusions" aria-label="套餐权益">
          <span v-for="label in packageLabels" :key="label">{{ label }}</span>
        </div>
        <div class="product-card__bottom">
          <div><strong>¥{{ product.suggested_price }}</strong><span class="muted"> / 套</span></div>
          <div class="product-card__sale"><span v-if="!unavailable" class="product-card__stock">剩 {{ product.sale_quantity }} 套</span><span v-else class="product-card__availability">{{ soldOutLabel }}</span><button v-if="unavailable && hasOtherAvailableDate" type="button" class="product-card__other-dates" @click.stop="open">查看其他日期</button></div>
        </div>
      </template>

      <template v-else>
        <div class="product-card__facts"><span>{{ stayLabel }}</span><span>{{ dateLabel || '日期以购买确认' }}</span><span v-if="checkOutLabel">{{ checkOutLabel }}</span></div>
        <div class="product-card__resources"><span v-for="resource in visibleResources" :key="resource.id"><b>{{ experienceLabel(resource.resource_type) }}</b> · {{ resource.resource_name }}</span></div>
        <div class="product-card__bottom">
          <div><strong>¥{{ product.suggested_price }}</strong><span class="muted"> 起 / {{ partyLabel }}</span></div>
          <div class="product-card__sale">
            <span class="product-card__stock">余 {{ product.sale_quantity }} 席</span>
            <span v-if="countdown.remaining()" class="product-card__countdown" :class="{ expired: countdown.expired() }">{{ countdown.expired() ? '销售已截止' : `距结束 ${countdown.remaining()}` }}</span>
          </div>
        </div>
      </template>
    </div>
    <section v-if="recommendation" class="product-card__recommendation" @click.stop>
      <strong>{{ recommendationTitle }}</strong>
      <p>{{ recommendation }}</p>
      <p v-if="recommendationNote" class="product-card__recommendation-note"><b>需要注意</b><span>{{ recommendationNote }}</span></p>
      <div v-if="recommendationTags.length" class="product-card__recommendation-tags">
        <span v-for="tag in recommendationTags" :key="tag">{{ tag }}</span>
      </div>
    </section>
  </article>
</template>
