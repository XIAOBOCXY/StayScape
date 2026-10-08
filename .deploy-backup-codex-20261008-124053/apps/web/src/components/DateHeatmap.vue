<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  items: unknown[]
  modelValue?: string
  dateKey?: string
  quantityKey?: string
  bookingKey?: string
  label?: string
}>(), { dateKey: 'available_date', quantityKey: 'available_count', bookingKey: '', label: '按日期查看' })

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

type DaySummary = { date: string; quantity: number; bookings: number }

function asDate(value: string) {
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}
function dateKeyOf(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
function monthStart(value: Date) { return new Date(value.getFullYear(), value.getMonth(), 1) }
function shiftMonth(value: Date, step: number) { return new Date(value.getFullYear(), value.getMonth() + step, 1) }

const summaries = computed<DaySummary[]>(() => {
  const grouped = new Map<string, DaySummary>()
  props.items.forEach((raw) => {
    const item = raw as Record<string, unknown>
    const date = String(item[props.dateKey] || '')
    if (!asDate(date)) return
    const current = grouped.get(date) || { date, quantity: 0, bookings: 0 }
    current.quantity += Math.max(0, Number(item[props.quantityKey] || 0))
    if (props.bookingKey) current.bookings += Math.max(0, Number(item[props.bookingKey] || 0))
    grouped.set(date, current)
  })
  return [...grouped.values()].sort((left, right) => left.date.localeCompare(right.date))
})

const dateMap = computed(() => new Map(summaries.value.map((item) => [item.date, item])))
const firstMonth = computed(() => summaries.value[0] ? monthStart(asDate(summaries.value[0].date)!) : monthStart(new Date()))
const lastMonth = computed(() => summaries.value.length ? monthStart(asDate(summaries.value.at(-1)!.date)!) : firstMonth.value)
const activeMonth = ref(monthStart(new Date()))

watch(firstMonth, (value) => {
  if (activeMonth.value < value || activeMonth.value > lastMonth.value) activeMonth.value = value
}, { immediate: true })
watch(() => props.modelValue, (value) => {
  const selected = value ? asDate(value) : null
  if (selected) activeMonth.value = monthStart(selected)
})

const maxQuantity = computed(() => Math.max(...summaries.value.map((item) => item.quantity), 1))
const maxBookings = computed(() => Math.max(...summaries.value.map((item) => item.bookings), 1))
const monthLabel = computed(() => `${activeMonth.value.getFullYear()} 年 ${activeMonth.value.getMonth() + 1} 月`)
const canBack = computed(() => activeMonth.value > firstMonth.value)
const canForward = computed(() => activeMonth.value < lastMonth.value)
const cells = computed(() => {
  const first = monthStart(activeMonth.value)
  const leading = (first.getDay() + 6) % 7
  const lastDay = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
  const result: Array<{ date?: string; day?: number; summary?: DaySummary }> = []
  for (let index = 0; index < leading; index += 1) result.push({})
  for (let day = 1; day <= lastDay; day += 1) {
    const date = dateKeyOf(new Date(first.getFullYear(), first.getMonth(), day))
    result.push({ date, day, summary: dateMap.value.get(date) })
  }
  while (result.length % 7) result.push({})
  return result
})

function heat(summary?: DaySummary) {
  if (!summary) return 0
  if (summary.quantity <= 0) return -1
  // Keep one quantity scale across room, service, and partner calendars:
  // more remaining inventory gets a deeper green; no inventory is distinct.
  return Math.min(5, Math.max(1, Math.ceil((summary.quantity / maxQuantity.value) * 5)))
}
function detail(summary?: DaySummary) {
  if (!summary) return ''
  const booking = props.bookingKey ? ` · 已预约 ${summary.bookings}` : ''
  return `${summary.date} · 可用 ${summary.quantity}${booking}`
}
</script>

<template>
  <section v-if="summaries.length" class="date-heatmap" :aria-label="label">
    <div class="date-heatmap__head">
      <div><span class="date-heatmap__eyebrow">库存日历</span><strong>{{ label }}</strong></div>
      <button type="button" :class="{ active: !modelValue }" @click="emit('update:modelValue', '')">查看全部</button>
    </div>
    <div class="calendar-nav">
      <button type="button" :disabled="!canBack" aria-label="上个月" @click="activeMonth = shiftMonth(activeMonth, -1)">←</button>
      <strong>{{ monthLabel }}</strong>
      <button type="button" :disabled="!canForward" aria-label="下个月" @click="activeMonth = shiftMonth(activeMonth, 1)">→</button>
    </div>
    <div class="calendar-weekdays"><span v-for="day in ['一', '二', '三', '四', '五', '六', '日']" :key="day">周{{ day }}</span></div>
    <div class="calendar-grid">
      <template v-for="(cell, index) in cells" :key="cell.date || `blank-${index}`">
        <span v-if="!cell.date" class="calendar-empty" />
        <button
          v-else
          type="button"
          :title="detail(cell.summary)"
          :class="['calendar-day', `heat-${heat(cell.summary)}`, { active: modelValue === cell.date, unavailable: !cell.summary }]"
          :disabled="!cell.summary"
          @click="emit('update:modelValue', cell.date)"
        >
          <span>{{ cell.day }}</span>
          <small v-if="cell.summary">{{ cell.summary.quantity }}</small>
        </button>
      </template>
    </div>
    <div class="calendar-legend"><span><i class="low" />数量较少</span><span><i class="mid" />数量适中</span><span><i class="high" />数量较多</span><span><i class="none" />无余量</span></div>
  </section>
</template>

<style scoped>
.date-heatmap{min-width:250px;padding:12px;border:1px solid #e8ede9;border-radius:11px;background:#fff}
.date-heatmap__head,.calendar-nav{display:flex;align-items:center;justify-content:space-between;gap:10px}.date-heatmap__eyebrow{display:block;color:#89958e;font-size:10px;letter-spacing:.03em}.date-heatmap__head strong{display:block;margin-top:2px;font-size:12px}.date-heatmap__head button{border:0;background:transparent;color:var(--muted);font-size:11px;cursor:pointer}.date-heatmap__head button.active{color:var(--ink);font-weight:650}.calendar-nav{margin:12px 0 8px}.calendar-nav strong{font-family:var(--font-mono);font-size:11px}.calendar-nav button{display:grid;width:24px;height:24px;place-items:center;border:1px solid var(--line);border-radius:7px;background:var(--paper);color:var(--ink);cursor:pointer}.calendar-nav button:disabled{opacity:.35;cursor:default}.calendar-weekdays,.calendar-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}.calendar-weekdays{margin-bottom:4px}.calendar-weekdays span{color:#75827a;font-size:10px;text-align:center}.calendar-empty{min-height:31px}.calendar-day{display:grid;min-height:36px;place-items:center;align-content:center;gap:0;border:1px solid transparent;border-radius:7px;background:#edf5ef;color:#315346;cursor:pointer;transition:.16s ease}.calendar-day span{font-family:var(--font-mono);font-size:11px}.calendar-day small{font-family:var(--font-mono);font-size:9px;opacity:.8}.calendar-day.heat-1{background:#edf5ef}.calendar-day.heat-2{background:#d8eadc}.calendar-day.heat-3{background:#b9d8c1}.calendar-day.heat-4{background:#8fbe9d;color:#203f31}.calendar-day.heat-5{background:#4f946b;color:#fff}.calendar-day.heat--1{background:#f8e9e6;color:#9a5147}.calendar-day.active{border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}.calendar-day.unavailable{background:transparent;color:#bac4c0;cursor:default}.calendar-legend{display:flex;align-items:center;gap:10px;margin-top:10px;color:#718078;font-size:10px;flex-wrap:wrap}.calendar-legend span{display:flex;align-items:center;gap:4px}.calendar-legend i{width:7px;height:7px;border-radius:2px}.low{background:#edf5ef}.mid{background:#b9d8c1}.high{background:#4f946b}.none{background:#f8e9e6}@media(max-width:700px){.date-heatmap{width:100%}}
</style>
