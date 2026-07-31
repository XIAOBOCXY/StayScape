<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import StatusTag from '../../components/StatusTag.vue'
import type { TravelProduct } from '../../types'

const route = useRoute(); const product = ref<TravelProduct | null>(null); const loading = ref(true); const question = ref(''); const chats = ref<Array<{ user?: string; answer?: string; suggestions?: TravelProduct[]; follow_up_questions?: string[] }>>([]); const consultLoading = ref(false); const intentDialog = ref(false); const intentLoading = ref(false)
const form = reactive({ natural_language: '', contact_name: '', contact_phone: '' })
async function load() { try { product.value = (await visitorApi.product(Number(route.params.id))).data } catch (e) { showToast(errorMessage(e)) } finally { loading.value = false } }
async function consult() { if (!question.value.trim()) return; const text = question.value; question.value = ''; chats.value.push({ user: text }); consultLoading.value = true; try { const response = await visitorApi.consult({ product_id: product.value?.id, question: text, weather: product.value?.weather || 'RAIN' }); chats.value.push({ answer: String(response.data.answer || ''), suggestions: (response.data.suggestions as TravelProduct[]) || [], follow_up_questions: (response.data.follow_up_questions as string[]) || [] }) } catch (e) { showToast(errorMessage(e)) } finally { consultLoading.value = false } }
async function submitIntent() {
  if (!product.value || !form.contact_name.trim() || !form.contact_phone.trim() || !form.natural_language.trim()) { showToast('请填写同行与注意事项、联系人和联系电话'); return }
  intentLoading.value = true
  try { await visitorApi.intent({ product_id: product.value.id, natural_language: form.natural_language, adult_count: 2, child_count: 0, child_ages: [], budget: product.value.suggested_price, contact_name: form.contact_name, contact_phone: form.contact_phone }); showToast('预约意向已提交，酒店会按需求联系确认'); intentDialog.value = false } catch (e) { showToast(errorMessage(e)) } finally { intentLoading.value = false }
}
onMounted(load)
</script>

<template>
  <div v-if="loading" class="panel empty-state">正在读取套餐详情…</div>
  <div v-else-if="product">
    <div class="detail-hero"><div class="eyebrow">{{ product.theme }} · {{ product.target_date }} · {{ product.weather }}</div><h1>{{ product.product_name }}</h1><h3>{{ product.marketing_title }}</h3><p class="muted">{{ product.marketing_content }}</p><div class="detail-hero__bottom"><div><span class="price-large">¥{{ product.suggested_price }}</span><span class="muted"> /套 · 含房间、酒店服务与文化体验</span></div><div><StatusTag :status="product.status" /><span :class="product.sale_quantity <= 2 ? 'warning-text' : 'muted'" style="margin-left:10px">仅余 {{ product.sale_quantity }} 套</span></div></div></div>
    <div class="detail-grid"><div>
      <div class="panel"><div class="section-title" style="margin-top:0"><h2>套餐包含</h2><span>真实资源与实时场次</span></div><div v-for="item in product.resources" :key="item.id" class="visitor-resource-row"><div><strong>{{ item.resource_name }}</strong><div class="muted">{{ item.resource_type }} · {{ item.available_date || product.target_date }} · {{ item.address || '酒店内或商户场地' }}</div></div><span>× {{ item.quantity_per_package }}</span></div></div>
      <div class="panel" style="margin-top:18px"><div class="section-title" style="margin-top:0"><h2>时间安排</h2><span>场次以实时确认结果为准</span></div><div class="chat-list"><div class="chat-bubble"><strong>15:00 · 办理入住</strong><br><span class="muted">入住后领取文化体验时间卡</span></div><div v-for="item in product.resources" :key="`time-${item.id}`" class="chat-bubble"><strong>{{ item.start_time?.slice(0,5) || '待确认' }} · {{ item.resource_name }}</strong><br><span class="muted">{{ item.start_time && item.end_time ? `${item.start_time.slice(0,5)}-${item.end_time.slice(0,5)}` : '商户实时确认场次' }} · 每套使用 {{ item.quantity_per_package }} 份</span></div></div></div>
      <div v-if="product.marketing_assets?.length" class="panel marketing-preview" style="margin-top:18px"><div class="section-title" style="margin-top:0"><h2>杭州旅行灵感</h2><span>智能生成营销素材</span></div><div v-for="asset in product.marketing_assets.filter(item => item.asset_type !== 'POSTER')" :key="asset.asset_type" class="inspiration"><strong>{{ asset.title }}</strong><p class="muted">{{ asset.content }}</p></div></div>
      <div class="panel" style="margin-top:18px"><div class="section-title" style="margin-top:0"><h2>智能咨询</h2><span>可以继续追问“还有什么推荐的？”</span></div><div class="chat-list"><div v-for="(chat,index) in chats" :key="index" :class="['chat-bubble', chat.user ? 'user' : '']">{{ chat.user || chat.answer }}<div v-if="chat.suggestions?.length" class="chat-suggestions"><button v-for="suggestion in chat.suggestions" :key="suggestion.id" @click="$router.push(`/visitor/products/${suggestion.id}`)">{{ suggestion.product_name }} · ¥{{ suggestion.suggested_price }}</button></div><div v-if="chat.follow_up_questions?.length" class="chat-followups"><button v-for="item in chat.follow_up_questions" :key="item" @click="question = item">{{ item }}</button></div></div><div v-if="consultLoading" class="chat-bubble">正在根据当前套餐约束回答…</div></div><div style="display:flex;gap:8px"><el-input v-model="question" placeholder="例如：还有什么适合雨天的？" @keyup.enter="consult" /><el-button type="primary" @click="consult">发送</el-button></div></div>
    </div><div><div class="panel sticky-panel"><div class="section-title" style="margin-top:0"><h2>预约意向</h2></div><p class="muted" style="line-height:1.7">比赛版本不收款。提交后酒店会根据房量、名额和过敏信息联系确认。</p><el-button type="primary" size="large" style="width:100%" @click="intentDialog=true">提交预约意向</el-button><div class="panel" style="box-shadow:none;background:#fff8eb;margin-top:16px"><strong>风险提示</strong><p class="danger-text" style="font-size:12px;line-height:1.7">{{ product.risk_message }}</p></div></div></div></div>
    <el-dialog v-model="intentDialog" title="用一句话提交预约需求" width="520px"><el-form label-position="top"><el-form-item label="同行与注意事项" required><el-input v-model="form.natural_language" type="textarea" :rows="6" maxlength="800" show-word-limit placeholder="例如：两位大人带一个6岁孩子，预算700元，下午四点体验，孩子花生过敏，不吃辣，希望安排轻松一些。" /><div class="form-tip">儿童人数、年龄、过敏和饮食禁忌会从这句话里整理出来，酒店与商户确认时还会再次核对。</div></el-form-item><div class="form-grid"><el-form-item label="联系人" required><el-input v-model="form.contact_name" placeholder="怎么称呼" /></el-form-item><el-form-item label="联系电话" required><el-input v-model="form.contact_phone" placeholder="便于酒店联系确认" /></el-form-item></div></el-form><template #footer><el-button @click="intentDialog=false">取消</el-button><el-button type="primary" :loading="intentLoading" @click="submitIntent">提交预约意向</el-button></template></el-dialog>
  </div>
  <div v-else class="panel empty-state">套餐不存在或已下架</div>
</template>

<style scoped>
.detail-hero__bottom{display:flex;align-items:end;justify-content:space-between;margin-top:24px;gap:12px}.visitor-resource-row{display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-top:1px solid var(--line)}.marketing-preview{background:linear-gradient(135deg,#f6fbf8,#fffaf0)}.inspiration{padding:10px 0;border-top:1px solid var(--line)}.inspiration p{line-height:1.7;margin:6px 0}.chat-suggestions,.chat-followups{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.chat-suggestions button,.chat-followups button{border:1px solid #cfe6dc;background:#fff;color:var(--teal);border-radius:999px;padding:6px 9px;font-size:11px}.form-tip{margin-top:7px;color:var(--muted);font-size:12px;line-height:1.6}@media(max-width:600px){.detail-hero__bottom{display:block}.detail-hero__bottom>div:last-child{margin-top:15px}}
</style>
