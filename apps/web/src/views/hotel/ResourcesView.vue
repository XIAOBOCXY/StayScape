<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { PartnerResource } from '../../types'

const route = useRoute()
const items = ref<PartnerResource[]>([])
const loading = ref(false)
const switchingId = ref<number | null>(null)
const selected = ref<PartnerResource | null>(null)
const drawerVisible = ref(false)

function openDetails(row: PartnerResource) {
  selected.value = row
  drawerVisible.value = true
}

async function load() {
  loading.value = true
  try {
    items.value = (await hotelApi.resources()).data
    const focusId = Number(route.query.focus)
    const focused = items.value.find(item => item.id === focusId)
    if (focused) openDetails(focused)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

async function toggle(row: PartnerResource, enabled: boolean) {
  const previous = row.package_enabled
  row.package_enabled = enabled
  switchingId.value = row.id
  try {
    const response = await hotelApi.toggleResourcePackage(row.id, enabled)
    row.package_enabled = response.data.package_enabled
    ElMessage.success(row.package_enabled ? '已允许酒店组包' : '已暂停酒店组包')
  } catch (error) {
    row.package_enabled = previous
    ElMessage.error(errorMessage(error))
  } finally {
    switchingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="page-head">
    <div>
      <div class="eyebrow">PARTNER RESOURCE POOL</div>
      <h1>合作资源池</h1>
      <p>酒店管理组包许可，商户维护名额、日期、场次与结算价；点击任意资源可查看完整内容。</p>
    </div>
    <el-button plain @click="load">刷新</el-button>
  </div>

  <div class="panel table-wrap">
    <el-table v-loading="loading" :data="items" style="width: 100%" @row-click="openDetails">
      <el-table-column prop="resource_name" label="资源名称" min-width="190">
        <template #default="{ row }">
          <strong>{{ row.resource_name }}</strong>
          <div class="muted">{{ row.merchant_name }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="类别" width="115" />
      <el-table-column prop="available_date" label="日期" width="120" />
      <el-table-column label="实时名额" width="110">
        <template #default="{ row }"><strong :class="row.remaining_capacity <= 5 ? 'warning-text' : ''">{{ row.remaining_capacity }}</strong></template>
      </el-table-column>
      <el-table-column label="结算价" width="100">
        <template #default="{ row }">¥{{ row.settlement_price }}</template>
      </el-table-column>
      <el-table-column label="资源状态" width="110"><template #default="{ row }"><StatusTag :status="row.status" /></template></el-table-column>
      <el-table-column label="组包许可" width="150">
        <template #default="{ row }">
          <div class="switch-cell">
            <el-switch :model-value="row.package_enabled" :loading="switchingId === row.id" @click.stop @change="toggle(row, Boolean($event))" />
            <span :class="row.package_enabled ? 'enabled-text' : 'muted'">{{ row.package_enabled ? '允许组包' : '未允许' }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="引用产品" width="100"><template #default="{ row }">{{ row.referenced_product_count }} 款</template></el-table-column>
      <el-table-column label="详情" width="90"><template #default="{ row }"><el-button link type="primary" @click.stop="openDetails(row)">查看</el-button></template></el-table-column>
    </el-table>
    <div v-if="!loading && !items.length" class="empty-state">暂无合作资源</div>
  </div>

  <el-drawer v-model="drawerVisible" :title="selected?.resource_name || 'RESOURCE DETAIL'" size="480px">
    <div v-if="selected" class="resource-detail">
      <div class="resource-detail__hero">
        <div class="eyebrow">PARTNER EXPERIENCE RESOURCE</div>
        <h2>{{ selected.resource_name }}</h2>
        <p>{{ selected.description || '当前资源由合作商户维护，酒店仅管理组包许可。' }}</p>
      </div>
      <div class="resource-detail__metrics">
        <div><span>REMAINING</span><strong>{{ selected.remaining_capacity }}</strong><small>实时剩余名额</small></div>
        <div><span>SETTLEMENT</span><strong>¥{{ selected.settlement_price }}</strong><small>酒店结算价</small></div>
        <div><span>REFERENCED</span><strong>{{ selected.referenced_product_count }}</strong><small>被产品引用</small></div>
      </div>
      <div class="resource-detail__rows">
        <div><span>MERCHANT</span><strong>{{ selected.merchant_name || '—' }}</strong></div>
        <div><span>DATE</span><strong>{{ selected.available_date }}</strong></div>
        <div><span>SESSION</span><strong>{{ selected.start_time?.slice(0, 5) || '—' }} – {{ selected.end_time?.slice(0, 5) || '—' }}</strong></div>
        <div><span>SUITABLE FOR</span><strong>{{ selected.suitable_crowds || 'ALL' }}</strong></div>
        <div><span>WEATHER</span><strong>{{ selected.weather_tags || '—' }}</strong></div>
        <div><span>PACKAGE PERMISSION</span><strong :class="selected.package_enabled ? 'enabled-text' : 'muted'">{{ selected.package_enabled ? '允许组包' : '未允许组包' }}</strong></div>
      </div>
      <div class="resource-detail__note">活动日期、场次、名额和结算价格由合作商户维护；酒店可以在列表中即时切换组包许可，变更会触发受影响产品重算。</div>
    </div>
  </el-drawer>
</template>

<style scoped>
.switch-cell{display:flex;align-items:center;gap:8px}.enabled-text{color:var(--teal);font-size:12px;font-weight:600}.resource-detail{padding:4px 0 24px}.resource-detail__hero{padding:4px 0 22px;border-bottom:1px solid var(--line)}.resource-detail__hero h2{margin:9px 0 8px;font:28px Georgia,'Songti SC',serif;color:var(--teal-dark)}.resource-detail__hero p{margin:0;color:var(--muted);font-size:13px;line-height:1.75}.resource-detail__metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:20px 0;border-bottom:1px solid var(--line)}.resource-detail__metrics div{padding:13px 12px;background:#f5faf7;border-radius:12px}.resource-detail__metrics span,.resource-detail__metrics small,.resource-detail__rows span{display:block;color:var(--muted);font-size:10px;letter-spacing:.08em}.resource-detail__metrics strong{display:block;margin:7px 0 4px;color:var(--teal-dark);font:24px Georgia,serif}.resource-detail__metrics small{letter-spacing:0;font-size:11px}.resource-detail__rows{display:grid;gap:0}.resource-detail__rows div{display:flex;justify-content:space-between;gap:16px;padding:14px 0;border-bottom:1px solid var(--line)}.resource-detail__rows strong{text-align:right;font-size:13px}.resource-detail__note{margin-top:18px;padding:13px 14px;border-radius:12px;background:#fbf3e5;color:#85683e;font-size:11px;line-height:1.7}@media(max-width:500px){.resource-detail__metrics{grid-template-columns:1fr}.resource-detail__rows div{display:block}.resource-detail__rows strong{display:block;text-align:left;margin-top:5px}}
</style>
