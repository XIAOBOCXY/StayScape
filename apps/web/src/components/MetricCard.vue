<script setup lang="ts">
defineProps<{ label: string; value: string | number; hint?: string; accent?: string }>()
</script>

<template>
  <div class="metric-card" :style="{ '--metric-accent': accent || '#0f766e' }">
    <div class="metric-label">{{ label }}</div>
    <div class="metric-value">{{ value }}</div>
    <div v-if="hint" class="metric-hint">{{ hint }}</div>
  </div>
</template>

