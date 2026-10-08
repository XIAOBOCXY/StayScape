<script setup lang="ts">
// 工作台「AI 执行摘要」：一行一条结论 + 可核查依据。抽成独立组件后，
// 工作台只需要传 rows，样式与结构都收在这里。
export type ExecSummaryRow = {
  key?: string
  label: string
  done?: boolean
  headline?: string
  basis?: string
}

// rows 由工作台计算后传入（结构见 ExecSummaryRow），这里保持宽松类型，
// 避免工作台内部的 AnyRecord 计算属性与组件 props 之间来回断言。
defineProps<{ rows: Array<Record<string, any>> }>()
</script>

<template>
  <details class="exec-summary">
    <summary>AI 执行摘要 · 这一轮读了什么、校验了什么（{{ rows.length }} 项）</summary>
    <ul>
      <li v-for="row in rows" :key="row.key || row.label" :class="{ 'is-pending': !row.done }">
        <span class="exec-summary__mark">{{ row.done ? '✓' : '·' }}</span>
        <b>{{ row.label }}</b>
        <span class="exec-summary__detail">{{ row.headline }}</span>
        <small>{{ row.basis }}</small>
      </li>
    </ul>
  </details>
</template>

<style scoped>
.exec-summary { display: grid; gap: 8px; padding: 11px 13px; border: 1px solid var(--line); border-radius: 11px; background: var(--paper); }
.exec-summary > summary { cursor: pointer; color: var(--teal-dark); font-size: 12px; font-weight: 650; }
.exec-summary ul { display: grid; gap: 6px; margin: 10px 0 0; padding: 0; list-style: none; }
.exec-summary li { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px; min-width: 0; padding: 7px 9px; border-top: 1px solid #eef3f0; font-size: 12.5px; line-height: 1.7; }
.exec-summary li:first-child { border-top: 0; }
.exec-summary__mark { color: #2f6f60; font-weight: 700; }
.exec-summary li b { color: var(--ink); }
.exec-summary__detail { color: #45524c; }
.exec-summary li small { color: var(--muted); font-size: 11.5px; }
.exec-summary li.is-pending .exec-summary__mark { color: var(--muted); }
.exec-summary li.is-pending b, .exec-summary li.is-pending .exec-summary__detail { color: #6b7a74; }
</style>
