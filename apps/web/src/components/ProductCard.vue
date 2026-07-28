<script setup lang="ts">
import { useRouter } from 'vue-router'
import StatusTag from './StatusTag.vue'
import type { TravelProduct } from '../types'

const props = defineProps<{ product: TravelProduct; publicView?: boolean }>()
const router = useRouter()
function open() {
  router.push(props.publicView ? `/visitor/products/${props.product.id}` : `/hotel/products/${props.product.id}`)
}
</script>

<template>
  <article class="product-card" @click="open">
    <div class="product-card__top"><span class="eyebrow">{{ product.theme }}</span><StatusTag :status="product.status" /></div>
    <h3>{{ product.product_name }}</h3>
    <p class="muted line-clamp">{{ product.marketing_content }}</p>
    <div class="product-card__resources"><span v-for="resource in product.resources" :key="resource.id">{{ resource.resource_name }}</span></div>
    <div class="product-card__bottom"><div><strong>¥{{ product.suggested_price }}</strong><span class="muted"> /套</span></div><span :class="product.sale_quantity <= 2 ? 'warning-text' : 'muted'">余 {{ product.sale_quantity }} 套</span></div>
  </article>
</template>

