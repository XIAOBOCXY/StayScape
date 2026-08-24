<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { MEDIA_LIBRARY, type ProductMediaAsset } from '../utils/productMedia'

const props = withDefaults(defineProps<{ media: ProductMediaAsset; aspect?: 'hero' | 'card' | 'gallery' | 'poster' }>(), { aspect: 'card' })
const failed = ref(false)
const replacementIndex = ref(-1)

const replacementCandidates = computed(() => {
  const all = Object.values(MEDIA_LIBRARY).filter((item) => item.url !== props.media.url)
  const sameKind = all.filter((item) => item.kind === props.media.kind)
  // Prefer a different publisher so one blocked image host does not turn the
  // whole experience into a placeholder.  The public source link remains
  // visible for every image.
  return [...sameKind, ...all.filter((item) => item.kind !== props.media.kind)]
    .filter((item, index, list) => list.findIndex((candidate) => candidate.url === item.url) === index)
})
const currentMedia = computed(() => replacementIndex.value < 0 ? props.media : replacementCandidates.value[replacementIndex.value] || props.media)

function reset() { failed.value = false; replacementIndex.value = -1 }
function useNextImage() {
  if (replacementIndex.value + 1 < replacementCandidates.value.length) replacementIndex.value += 1
  else failed.value = true
}
watch(() => props.media.url, reset)
</script>

<template>
  <div :class="['media-image', `media-image--${aspect}`, { 'is-failed': failed }]">
    <img v-if="!failed" :src="currentMedia.url" :alt="currentMedia.alt" loading="lazy" decoding="async" @error="useNextImage" />
    <div v-else class="media-fallback" role="img" :aria-label="`${media.alt}（图片暂不可用）`">
      <span class="media-fallback__mark">S</span>
      <strong>{{ media.kind === 'culture' ? 'A CULTURAL MOMENT' : 'A HANGZHOU MOMENT' }}</strong>
      <small>StayScape demo scene</small>
    </div>
    <a class="media-source" :href="currentMedia.source_url" target="_blank" rel="noreferrer" @click.stop>{{ currentMedia.source }}</a>
  </div>
</template>
