<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { hotelApi } from '../../api'
import { errorMessage } from '../../api/client'
const items = ref<Array<Record<string, any>>>([]); const loading = ref(false)
async function load() { loading.value = true; try { items.value = (await hotelApi.intents()).data } catch (e) { errorMessage(e) } finally { loading.value = false } }
onMounted(load)
</script>
<template><div class="page-head"><div><div class="eyebrow">VISITOR INTENTS</div><h1>游客预约意向</h1><p>比赛版本只保存预约意向，不执行支付与真实订单结算。</p></div><el-button plain @click="load">刷新</el-button></div><div class="panel table-wrap"><el-table v-loading="loading" :data="items"><el-table-column prop="product_id" label="产品" width="80" /><el-table-column label="同行" width="110"><template #default="{row}">{{ row.adult_count }}成人 / {{ row.child_count }}儿童</template></el-table-column><el-table-column label="预算" width="100"><template #default="{row}">¥{{ row.budget }}</template></el-table-column><el-table-column label="兴趣" min-width="140"><template #default="{row}">{{ (row.interests || []).join('、') || '未填写' }}</template></el-table-column><el-table-column label="过敏信息" min-width="150"><template #default="{row}"><span class="danger-text">{{ row.allergy_information || '无' }}</span></template></el-table-column><el-table-column prop="contact_name" label="联系人" width="100" /><el-table-column prop="contact_phone" label="联系电话" width="140" /><el-table-column label="状态" width="100"><template #default="{row}"><el-tag type="warning">{{ row.intent_status }}</el-tag></template></el-table-column></el-table><div v-if="!loading && !items.length" class="empty-state">游客提交预约意向后会显示在这里</div></div></template>

