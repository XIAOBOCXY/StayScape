<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ProductMediaAsset } from '../utils/productMedia'

const props = withDefaults(defineProps<{ media: ProductMediaAsset; aspect?: 'hero' | 'card' | 'gallery' | 'poster' }>(), { aspect: 'card' })
const failed = ref(false)
watch(() => props.media.url, () => { failed.value = false })
</script>

<template>
  <div :class="['media-image', `media-image--${aspect}`, { 'is-failed': failed }]">
    <img v-if="!failed" :src="media.url" :alt="media.alt" loading="lazy" decoding="async" @error="failed = true" />
    <div v-else class="media-fallback" role="img" :aria-label="`${media.alt}（图片暂不可用）`">
      <span class="media-fallback__mark">S</span>
      <strong>{{ media.kind === 'culture' ? 'A CULTURAL MOMENT' : 'A HANGZHOU MOMENT' }}</strong>
      <small>StayScape demo scene</small>
    </div>
    <a class="media-source" :href="media.source_url" target="_blank" rel="noreferrer" @click.stop>{{ media.source }} · Demo image</a>
  </div>
</template>
