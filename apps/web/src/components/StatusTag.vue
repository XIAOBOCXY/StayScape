<script setup lang="ts">
defineProps<{ status: string }>()
const labelMap: Record<string, string> = {
  AVAILABLE: '可用', ON_SALE: '在售', LOW_STOCK: '库存紧张', SOLD_OUT: '已售罄', PAUSED: '已暂停', OFF_SHELF: '已下架', DRAFT: '草稿',
  DISABLED: '已停用', UNAVAILABLE: '不可用', SUSPENDED: '已暂停', ACTIVE: '合作中', TERMINATED: '已终止', EXPIRED: '已过期', NEW: '待联系'
}
const typeMap: Record<string, string> = { ON_SALE: 'success', AVAILABLE: 'success', ACTIVE: 'success', LOW_STOCK: 'warning', SOLD_OUT: 'danger', PAUSED: 'danger', OFF_SHELF: 'info', DISABLED: 'info', UNAVAILABLE: 'danger', SUSPENDED: 'warning', DRAFT: 'info', NEW: 'warning' }
</script>

<template>
  <el-tag :type="(typeMap[status] || 'info') as any" effect="light" round>{{ labelMap[status] || status }}</el-tag>
</template>

