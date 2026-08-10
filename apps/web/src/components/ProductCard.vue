<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import StatusTag from './StatusTag.vue'
import MediaImage from './MediaImage.vue'
import type { TravelProduct } from '../types'
import { experienceLabel, heroMedia, weatherLabel } from '../utils/productMedia'

const props = defineProps<{ product: TravelProduct; publicView?: boolean }>()
const router = useRouter()
const media = computed(() => heroMedia(props.product))
const weather = computed(() => weatherLabel(props.product.weather))
const crowdLabel = computed(() => ({ FAMILY: 'family', COUPLE: 'couple', FRIENDS: 'friends', SOLO: 'solo', LOCAL_WEEKEND: 'local weekend' }[props.product.target_crowd] || 'stay'))
const visibleResources = computed(() => props.product.resources.slice(0, 3))
function open() {
  router.push(props.publicView ? `/visitor/products/${props.product.id}` : `/hotel/products/${props.product.id}`)
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open() }
}
</script>

<template>
  <article class="product-card product-card--editorial" tabindex="0" @click="open" @keydown="onKeydown">
    <MediaImage :media="media" aspect="card" />
    <div class="product-card__body">
      <div class="product-card__top">
        <span class="product-card__eyebrow">{{ product.target_crowd }} · {{ weather }}</span>
        <StatusTag v-if="!publicView" :status="product.status" />
        <span v-else class="live-pill"><i /> LIVE</span>
      </div>
      <h3>{{ product.product_name }}</h3>
      <p class="product-card__hook">{{ product.marketing_title || product.marketing_content }}</p>
      <div class="product-card__resources">
        <span v-for="resource in visibleResources" :key="resource.id"><b>{{ experienceLabel(resource.resource_type) }}</b> · {{ resource.resource_name }}</span>
      </div>
      <div class="product-card__bottom">
        <div><strong>¥{{ product.suggested_price }}</strong><span class="muted"> / {{ crowdLabel }}</span></div>
        <span :class="product.sale_quantity <= 2 ? 'warning-text' : 'muted'">仅剩 {{ product.sale_quantity }} 套</span>
      </div>
    </div>
  </article>
</template>
