<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'

type IntentRecord = Record<string, any>
const items = ref<IntentRecord[]>([])
const presetIntents: IntentRecord[] = [{id:'demo-1',product_name:'西湖茶席与宋韵下午茶',product_code:'HZ-TEA-01',product_id:1,target_date:'2026-09-27',adult_count:2,child_count:0,budget:699,interests:['茶文化','慢游'],contact_name:'林女士',contact_phone:'138****2266',remaining_quantity:4,intent_status:'NEW',reservation_status:'HELD',other_requirements:'希望安排靠窗座位'}, {id:'demo-2',product_name:'双人陶艺夜',product_code:'HZ-CRAFT-02',product_id:2,target_date:'2026-09-28',adult_count:2,child_count:0,budget:799,interests:['手作','夜游'],contact_name:'周先生',contact_phone:'139****5188',remaining_quantity:2,intent_status:'NEW',reservation_status:'HELD',other_requirements:'晚餐后到店'}, {id:'demo-3',product_name:'运河夜游与江南小食',product_code:'HZ-CANAL-03',product_id:3,target_date:'2026-09-29',adult_count:3,child_count:1,budget:999,interests:['夜游','美食'],contact_name:'陈女士',contact_phone:'137****9041',remaining_quantity:6,intent_status:'FOLLOWING',reservation_status:'HELD',other_requirements:'儿童8岁'}]
const loading = ref(false)
const selected = ref<IntentRecord | null>(null)
const drawerVisible = ref(false)
const actionLoading = ref(false)
const newCount = computed(() => items.value.filter((item) => item.intent_status === 'NEW').length)
const totalReserved = computed(() => items.value.reduce((sum, item) => sum + 1, 0))

async function load() {
  loading.value = true
  try { items.value = (await hotelApi.intents()).data
    if (!items.value.length) items.value = presetIntents }
  catch (e) { ElMessage.error(errorMessage(e)) }
  finally { loading.value = false }
}
function statusText(row: IntentRecord) {
  if (row.reservation_status === 'CONFIRMED') return '已成交'
  if (row.reservation_status === 'CANCELLED') return '已取消'
  if (row.intent_status === 'NEW') return '待跟进'
  if (row.intent_status === 'FOLLOWING') return '跟进中'
  return '已处理'
}
function statusType(row: IntentRecord) {
  if (row.reservation_status === 'CONFIRMED') return 'success'
  if (row.reservation_status === 'CANCELLED') return 'info'
  return row.intent_status === 'NEW' ? 'warning' : 'primary'
}
function open(item: IntentRecord) { selected.value = item; drawerVisible.value = true }
function timeText(value?: string) { return value ? String(value).slice(0, 5) : '未填写' }
function dateText(value?: string) { return value ? String(value).replace('T', ' ').slice(0, 16) : '—' }
function listText(value?: unknown[], fallback = '未填写') { return Array.isArray(value) && value.length ? value.join('、') : fallback }
async function updateIntent(status: 'CONFIRMED' | 'CANCELLED') {
  if (!selected.value) return
  actionLoading.value = true
  try { await hotelApi.updateIntent(Number(selected.value.id), status); ElMessage.success(status === 'CONFIRMED' ? '订单已确认，资源继续占用' : '订单已取消，库存已释放'); drawerVisible.value = false; await load() }
  catch (e) { ElMessage.error(errorMessage(e)) }
  finally { actionLoading.value = false }
}
onMounted(load)
</script>

<template>
  <div class="intent-page">
    <div class="page-head"><div><h1>游客订单</h1></div><div class="header-actions"><span class="live-pill"><i /> {{ newCount }} 条待跟进</span><el-button plain @click="load">刷新</el-button></div></div>
    <div class="intent-summary"><div><span>待跟进</span><strong>{{ newCount }}</strong><small>需要电话联系</small></div><div><span>暂占套餐</span><strong>{{ totalReserved }}</strong><small>订单暂占用的套餐</small></div><div><span>待核对</span><strong>待核对</strong><small>场次与同行人数需确认</small></div></div>
    <div class="panel table-wrap intent-table-panel"><el-table v-loading="loading" :data="items" row-class-name="intent-row" @row-click="open"><el-table-column label="产品" min-width="230"><template #default="{row}"><div class="intent-product"><span class="intent-product__mark"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></span><div><strong>{{ row.product_name }}</strong><small>{{ row.product_code || `产品 #${row.product_id}` }} · {{ row.target_date }}</small></div></div></template></el-table-column><el-table-column label="同行需求" min-width="180"><template #default="{row}"><strong>{{ row.adult_count }} 成人 · {{ row.child_count }} 儿童</strong><small class="table-subline">{{ row.child_ages?.length ? `儿童 ${row.child_ages.join('、')} 岁` : '未提供儿童年龄' }}</small></template></el-table-column><el-table-column label="预算 / 体验" min-width="170"><template #default="{row}"><strong>¥{{ row.budget }}</strong><small class="table-subline">{{ listText(row.interests, '杭州文化体验') }}</small></template></el-table-column><el-table-column label="联系人" min-width="150"><template #default="{row}"><strong>{{ row.contact_name }}</strong><small class="table-subline">{{ row.contact_phone }}</small></template></el-table-column><el-table-column label="库存" width="100"><template #default="{row}"><span :class="row.remaining_quantity <= 2 ? 'warning-text' : 'success-text'">余 {{ row.remaining_quantity }} 套</span></template></el-table-column><el-table-column label="状态" width="100"><template #default="{row}"><el-tag :type="statusType(row)" effect="light">{{ statusText(row) }}</el-tag></template></el-table-column><el-table-column label="提交时间" width="150"><template #default="{row}">{{ dateText(row.created_at) }}</template></el-table-column><el-table-column label="操作" width="110"><template #default="{row}"><el-button link type="primary" @click.stop="open(row)">查看详情</el-button></template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">游客提交订单后，会在这里形成可跟进的真实线索。</div></div>

    <el-drawer v-model="drawerVisible" title="订单详情" size="520px"><div v-if="selected" class="intent-drawer"><div class="intent-drawer__product"><span class="intent-product__mark"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M8 32c6-9 11-14 16-14s10 5 16 14" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M12 35h24" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="33" cy="15" r="4" fill="currentColor"/></svg></span><div><div class="eyebrow">{{ selected.product_code || `产品 #${selected.product_id}` }}</div><h2>{{ selected.product_name }}</h2><p>{{ selected.target_date }} · 当前余 {{ selected.remaining_quantity }} 套 · ¥{{ selected.submitted_price || selected.budget }}</p></div></div><div class="drawer-section"><div class="drawer-label">同行信息</div><div class="drawer-grid"><div><span>成人</span><strong>{{ selected.adult_count }} 位</strong></div><div><span>儿童</span><strong>{{ selected.child_count }} 位</strong></div><div><span>儿童年龄</span><strong>{{ listText(selected.child_ages) }}</strong></div><div><span>预算</span><strong>¥{{ selected.budget }}</strong></div></div></div><div class="drawer-section"><div class="drawer-label">偏好与注意事项</div><div class="drawer-tags"><span v-for="item in [...(selected.interests || []), ...(selected.dietary_restrictions || [])]" :key="item">{{ item }}</span><span v-if="!selected.interests?.length && !selected.dietary_restrictions?.length && !selected.allergy_information">未填写特殊偏好</span></div><p v-if="selected.preferred_experience_time" class="drawer-note">希望体验时间：{{ timeText(selected.preferred_experience_time) }}</p></div><div class="drawer-section"><div class="drawer-label">联系方式</div><div class="contact-card"><strong>{{ selected.contact_name }}</strong><span>{{ selected.contact_phone }}</span><small>提交于 {{ dateText(selected.created_at) }}</small></div></div><div class="drawer-actions"><div class="follow-up-note"><span class="follow-up-note__dot"></span><div><strong>{{ statusText(selected) }}</strong><small>确认前请核对场次与同行人数；暂留至 {{ dateText(selected.reserved_until) }}。</small></div></div><div v-if="selected.reservation_status === 'HELD'" class="intent-action-row"><el-button type="primary" :loading="actionLoading" @click="updateIntent('CONFIRMED')">确认订单</el-button><el-button plain :loading="actionLoading" @click="updateIntent('CANCELLED')">退款</el-button></div></div></div></el-drawer>
  </div>
</template>

<style scoped>
.intent-page{max-width:100%}.header-actions{display:flex;align-items:center;gap:10px}.intent-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0}.intent-summary>div{padding:18px 20px;background:#fff;border:1px solid var(--line);border-radius:14px}.intent-summary span{display:block;color:#789087;font-size:10px;letter-spacing:.12em}.intent-summary strong{display:block;font:28px Georgia,serif;color:var(--teal-dark);margin:9px 0 4px}.intent-summary small{color:var(--muted);font-size:11px}.intent-table-panel{padding:8px 18px 18px}.intent-table-panel :deep(.el-table__row){cursor:pointer}.intent-product{display:flex;align-items:center;gap:10px}.intent-product__mark{width:30px;height:30px;display:grid;place-items:center;border-radius:10px;background:#e6f3ed;color:var(--teal);font:19px Georgia,serif}.intent-product strong,.intent-product small,.table-subline{display:block}.intent-product small,.table-subline{color:var(--muted);font-size:11px;margin-top:5px}.success-text{color:#438765;font-size:12px;font-weight:600}.intent-drawer{padding:0 4px 20px}.intent-drawer__product{display:flex;gap:13px;padding-bottom:23px;border-bottom:1px solid var(--line)}.intent-drawer__product h2{font:25px Georgia,serif;margin:7px 0}.intent-drawer__product p{color:var(--muted);font-size:12px;margin:0}.drawer-section{padding:23px 0;border-bottom:1px solid var(--line)}.drawer-label{color:var(--teal);font-size:10px;font-weight:700;letter-spacing:.14em;margin-bottom:14px}.drawer-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.drawer-grid span,.contact-card span,.contact-card small{display:block;color:var(--muted);font-size:11px}.drawer-grid strong{display:block;margin-top:5px;font-size:14px}.drawer-tags{display:flex;gap:7px;flex-wrap:wrap}.drawer-tags span{padding:7px 10px;border-radius:999px;background:#eef7f1;color:var(--teal-dark);font-size:12px}.drawer-tags .safety-tag{background:#fff4df;color:#a26e2b}.drawer-note{color:var(--muted);font-size:12px;margin:14px 0 0}.drawer-quote{background:#f6faf7;margin:0 -4px;padding:20px 16px}.drawer-quote p{font:17px/1.8 Georgia,'Songti SC',serif;color:var(--ink);margin:0}.contact-card{display:grid;gap:5px;padding:13px;background:#fbf3e5;border-radius:12px}.contact-card strong{font-size:16px}.drawer-actions{padding-top:20px}.drawer-actions>small{display:block;text-align:center;color:var(--muted);font-size:10px;margin-top:9px}.follow-up-note{display:flex;gap:10px;align-items:flex-start;padding:13px 14px;border:1px solid #dcece3;background:#f4faf6;border-radius:12px}.follow-up-note__dot{width:8px;height:8px;border-radius:50%;background:#d59f4d;box-shadow:0 0 0 4px #f7ead4;margin:5px 2px 0 3px;flex:none}.follow-up-note strong,.follow-up-note small{display:block}.follow-up-note strong{font-size:13px;color:var(--teal-dark)}.follow-up-note small{margin-top:4px;color:var(--muted);font-size:11px;line-height:1.6}.intent-action-row{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}@media(max-width:800px){.intent-summary{grid-template-columns:1fr}.header-actions{margin-top:12px}.page-head{display:block}}
</style>
