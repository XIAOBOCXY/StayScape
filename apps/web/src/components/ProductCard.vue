<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import StatusTag from './StatusTag.vue'
import MediaImage from './MediaImage.vue'
import type { TravelProduct } from '../types'
import { experienceLabel, heroMedia, mediaForResource } from '../utils/productMedia'
import { publicTravelCopy } from '../utils/publicTravelCopy'

const props = defineProps<{ product: TravelProduct; publicView?: boolean; compact?: boolean }>()
const router = useRouter()
const media = computed(() => {
  const focus = props.product.resources.find((item) => item.resource_type === 'PARTNER_RESOURCE') || props.product.resources[0]
  return focus ? mediaForResource(props.product, focus) : heroMedia(props.product)
})
const crowdLabel = computed(() => ({ FAMILY: '亲子', COUPLE: '两人', FRIENDS: '朋友', SOLO: '独自', LOCAL_WEEKEND: '本地周末' }[props.product.target_crowd] || '杭州周末'))
const visibleResources = computed(() => props.product.resources.slice(0, 3))
const hook = computed(() => publicTravelCopy(props.product.marketing_title || props.product.marketing_content, '把这段杭州时光留给周末。'))
function open() {
  router.push(props.publicView ? `/visitor/products/${props.product.id}` : `/hotel/products/${props.product.id}`)
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open() }
}
</script>

<template>
  <article :class="['product-card', 'product-card--editorial', { 'product-card--compact': compact }]" tabindex="0" @click="open" @keydown="onKeydown">
    <MediaImage :media="media" aspect="card" />
    <div class="product-card__body">
      <div class="product-card__top">
        <span class="product-card__eyebrow">{{ product.theme }} · {{ crowdLabel }}</span>
        <StatusTag v-if="!publicView" :status="product.status" />
        <span v-else class="live-pill"><i /> 可预约</span>
      </div>
      <h3>{{ product.product_name }}</h3>
      <p class="product-card__hook">{{ hook }}</p>
      <div class="product-card__resources">
        <span v-for="resource in visibleResources" :key="resource.id"><b>{{ experienceLabel(resource.resource_type) }}</b> · {{ resource.resource_name }}</span>
      </div>
      <div class="product-card__bottom">
        <div><strong>¥{{ product.suggested_price }}</strong><span class="muted"> / {{ crowdLabel }}</span></div>
        <span v-if="product.sale_quantity <= 2" class="warning-text">即将售罄</span>
      </div>
    </div>
  </article>
</template>
