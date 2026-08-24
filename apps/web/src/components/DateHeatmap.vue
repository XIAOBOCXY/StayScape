<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  items: unknown[]
  modelValue?: string
  dateKey?: string
  quantityKey?: string
  label?: string
}>(), { dateKey: 'available_date', quantityKey: 'available_count', label: '按日期查看' })

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const days = computed(() => {
  const grouped = new Map<string, number>()
  props.items.forEach((raw) => {
    const item = raw as Record<string, unknown>
    const date = String(item[props.dateKey] || '')
    if (!date) return
    grouped.set(date, (grouped.get(date) || 0) + Number(item[props.quantityKey] || 0))
  })
  return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right)).slice(0, 21).map(([date, quantity]) => ({ date, quantity }))
})

function labelFor(date: string) {
  const parsed = new Date(`${date}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? date : `${parsed.getMonth() + 1}/${parsed.getDate()}`
}

function level(quantity: number) {
  const max = Math.max(...days.value.map((item) => item.quantity), 1)
  return Math.min(4, Math.max(0, Math.ceil((quantity / max) * 4)))
}
</script>

<template>
  <section v-if="days.length" class="date-heatmap" :aria-label="label">
    <div class="date-heatmap__label"><span>{{ label }}</span><button :class="{ active: !modelValue }" type="button" @click="emit('update:modelValue', '')">全部</button></div>
    <div class="date-heatmap__days">
      <button v-for="day in days" :key="day.date" type="button" :class="['date-cell', `level-${level(day.quantity)}`, { active: modelValue === day.date }]" @click="emit('update:modelValue', day.date)">
        <small>{{ labelFor(day.date) }}</small><strong>{{ day.quantity }}</strong>
      </button>
    </div>
  </section>
</template>

<style scoped>
.date-heatmap{display:flex;align-items:center;gap:18px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--panel-soft)}.date-heatmap__label{display:grid;gap:6px;min-width:62px;color:var(--muted);font-size:11px}.date-heatmap__label button{padding:0;border:0;background:transparent;color:var(--muted);font-size:11px;text-align:left;cursor:pointer}.date-heatmap__label button.active{color:var(--ink);font-weight:650}.date-heatmap__days{display:flex;min-width:0;gap:5px;overflow:auto;padding-bottom:1px}.date-cell{display:grid;min-width:42px;gap:3px;padding:7px 5px;border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--muted);cursor:pointer}.date-cell small{font-size:9px}.date-cell strong{font-family:var(--font-mono);font-size:12px}.date-cell.level-1{background:#f1f3f2}.date-cell.level-2{background:#e4ece9}.date-cell.level-3{background:#ceded8}.date-cell.level-4{background:#b4ccc3;color:#18332d}.date-cell.active{border-color:#687a75;box-shadow:inset 0 0 0 1px #687a75;color:var(--ink)}@media(max-width:700px){.date-heatmap{align-items:flex-start;flex-direction:column;gap:9px}.date-heatmap__label{display:flex;gap:12px}.date-cell{min-width:38px}}
</style>
