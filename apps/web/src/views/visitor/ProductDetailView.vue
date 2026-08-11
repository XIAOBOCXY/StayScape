<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import MediaImage from '../../components/MediaImage.vue'
import ProductCard from '../../components/ProductCard.vue'
import type { MarketingAsset, TravelProduct } from '../../types'
import { experienceLabel, experienceLabelZh, mediaForProduct, weatherLabel } from '../../utils/productMedia'
import { loadVisitorProfile, saveVisitorProfile, type VisitorProfile, visitorConversationId } from '../../utils/visitorProfile'

const route = useRoute()
const product = ref<TravelProduct | null>(null)
const loading = ref(true)
const question = ref('')
const chats = ref<Array<{ user?: string; answer?: string; suggestions?: TravelProduct[]; follow_up_questions?: string[] }>>([])
const consultLoading = ref(false)
const intentDialog = ref(false)
const intentLoading = ref(false)
const posterDialog = ref(false)
const form = reactive({ natural_language: '', contact_name: '', contact_phone: '' })
const intentParsed = ref(false)
const intentNeeds = reactive<VisitorProfile>({
  natural_language: '', target_date: null, weather: 'RAIN', target_crowd: 'FAMILY', adult_count: 2,
  child_count: 0, child_ages: [], budget: '700', interests: [], negative_interests: [], activity_level: 'MEDIUM',
  requested_places: [], dietary_restrictions: [], allergy_information: '', arrival_time: null,
  preferred_experience_time: null, other_requirements: ''
})

const gallery = computed(() => mediaForProduct(product.value).slice(1, 4))
const poster = computed(() => product.value?.marketing_assets?.find((asset) => asset.asset_type === 'POSTER'))
const social = computed(() => product.value?.marketing_assets?.find((asset) => asset.asset_type === 'SOCIAL_POST'))
const hero = computed(() => mediaForProduct(product.value)[0])
const story = computed(() => product.value?.marketing_content || product.value?.recommendation_reason || '')

async function load() {
  try { product.value = (await visitorApi.product(Number(route.params.id))).data }
  catch (e) { showToast(errorMessage(e)) }
  finally { loading.value = false }
}

async function consult() {
  if (!question.value.trim() || !product.value) return
  const text = question.value.trim(); question.value = ''; chats.value.push({ user: text }); consultLoading.value = true
  try {
    const response = await visitorApi.consult({ product_id: product.value.id, question: text, weather: product.value.weather, conversation_id: visitorConversationId() })
    chats.value.push({ answer: String(response.data.answer || ''), suggestions: (response.data.suggestions as TravelProduct[]) || [], follow_up_questions: (response.data.follow_up_questions as string[]) || [] })
  } catch (e) { showToast(errorMessage(e)) }
  finally { consultLoading.value = false }
}

async function copySocial() {
  if (!social.value?.content) return
  try { await navigator.clipboard.writeText(social.value.content); showToast('旅行灵感文案已复制') }
  catch { showToast('复制失败，请手动选择文案') }
}

function downloadPoster(asset?: MarketingAsset) {
  if (!asset?.poster_svg) return
  const url = URL.createObjectURL(new Blob([asset.poster_svg], { type: 'image/svg+xml;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = `${asset.title || product.value?.product_name || 'stayscape-poster'}.svg`; link.click(); URL.revokeObjectURL(url)
}

function syncIntentAges() {
  const count = Math.max(0, Number(intentNeeds.child_count) || 0)
  intentNeeds.child_ages = intentNeeds.child_ages.slice(0, count)
  while (intentNeeds.child_ages.length < count) intentNeeds.child_ages.push(6)
}

function applyIntentNeeds(data: Record<string, any>) {
  const arrayFields = ['interests', 'negative_interests', 'requested_places', 'dietary_restrictions']
  Object.keys(intentNeeds).forEach((key) => {
    if (key === 'natural_language' || data[key] === undefined) return
    ;(intentNeeds as any)[key] = arrayFields.includes(key) ? (Array.isArray(data[key]) ? data[key].map(String) : []) : data[key]
  })
  intentNeeds.target_date = product.value?.target_date || intentNeeds.target_date
  intentNeeds.weather = product.value?.weather || intentNeeds.weather
  intentNeeds.target_crowd = product.value?.target_crowd || intentNeeds.target_crowd
  syncIntentAges()
}

async function parseIntent() {
  if (!form.natural_language.trim()) { showToast('先写一句同行与注意事项，例如“一家四口，孩子6岁和9岁”'); return false }
  try {
    const response = await visitorApi.interpret({ natural_language: form.natural_language.trim() })
    applyIntentNeeds(response.data.interpreted_needs)
    intentNeeds.natural_language = form.natural_language.trim()
    intentParsed.value = true
    return true
  } catch (e) { showToast(errorMessage(e)); return false }
}

function openIntent() {
  const saved = loadVisitorProfile()
  if (saved) {
    Object.assign(intentNeeds, saved)
    form.natural_language = saved.natural_language || ''
  } else {
    intentNeeds.target_date = product.value?.target_date || null
    intentNeeds.weather = product.value?.weather || 'RAIN'
    intentNeeds.target_crowd = product.value?.target_crowd || 'FAMILY'
    intentNeeds.budget = product.value?.suggested_price || '700'
  }
  syncIntentAges()
  intentDialog.value = true
  if (form.natural_language.trim() && !intentParsed.value) void parseIntent()
}

async function submitIntent() {
  if (!product.value || !form.contact_name.trim() || !form.contact_phone.trim() || !form.natural_language.trim()) { showToast('请填写同行与注意事项、联系人和联系电话'); return }
  if (!intentParsed.value && !(await parseIntent())) return
  syncIntentAges()
  const profile: VisitorProfile = { ...intentNeeds, natural_language: form.natural_language.trim(), child_ages: [...intentNeeds.child_ages], interests: [...intentNeeds.interests], negative_interests: [...intentNeeds.negative_interests], requested_places: [...intentNeeds.requested_places], dietary_restrictions: [...intentNeeds.dietary_restrictions] }
  saveVisitorProfile(profile)
  intentLoading.value = true
  try {
    const response = await visitorApi.intent({ ...profile, product_id: product.value.id, structured_confirmed: true, contact_name: form.contact_name, contact_phone: form.contact_phone, conversation_id: visitorConversationId() })
    product.value.sale_quantity = Number(response.data.remaining_quantity ?? Math.max(product.value.sale_quantity - 1, 0))
    product.value.status = String(response.data.product_status || product.value.status)
    showToast(`预约意向已提交，当前还剩 ${product.value.sale_quantity} 套`); intentDialog.value = false
  } catch (e) { showToast(errorMessage(e)) }
  finally { intentLoading.value = false }
}

onMounted(load)
</script>

<template>
  <div v-if="loading" class="detail-loading"><span /> 正在打开这段杭州体验…</div>
  <div v-else-if="product" class="visitor-product-detail">
    <section class="product-detail-hero">
      <MediaImage :media="hero" aspect="hero" />
      <div class="product-detail-hero__veil" />
      <div class="product-detail-hero__content"><div class="eyebrow">{{ weatherLabel(product.weather) }} · {{ product.target_crowd }} · CULTURE STAY</div><h1>{{ product.product_name }}</h1><p>{{ product.marketing_title || product.marketing_content }}</p><div class="product-detail-hero__meta"><strong>¥{{ product.suggested_price }}</strong><span>/ family</span><i /><span>仅剩 {{ product.sale_quantity }} 套</span><span>{{ product.target_date }}</span></div></div>
      <router-link to="/visitor/products" class="back-to-list">← 返回体验列表</router-link>
    </section>

    <div class="detail-intro-line"><span>STAY · TASTE · EXPERIENCE</span><strong>{{ product.target_date }} / HANGZHOU</strong><span>{{ product.sale_quantity <= 2 ? 'LAST FEW MOMENTS' : 'AVAILABLE TONIGHT' }}</span></div>

    <section class="story-layout">
      <div class="story-copy"><div class="eyebrow">THE STORY OF THIS STAY</div><h2>{{ product.theme || '一场为今天准备的杭州体验' }}</h2><p class="story-lead">{{ story }}</p><p class="story-note">{{ product.recommendation_reason }}</p></div>
      <div class="story-fact"><span class="fact-number">{{ product.sale_quantity }}</span><span>套真实可用<br />的今晚提案</span><small>库存、场次和价格会实时更新</small></div>
    </section>

    <section class="experience-section"><div class="editorial-heading"><div><div class="eyebrow">WHAT'S INSIDE</div><h2>一晚，三个章节</h2></div><span class="section-caption">不是一张房券，是一段完整的杭州时光。</span></div><div class="experience-list"><div v-for="item in product.resources" :key="item.id" class="experience-row"><div class="experience-index">{{ experienceLabel(item.resource_type) }}</div><div class="experience-main"><h3>{{ item.resource_name }}</h3><p>{{ experienceLabelZh(item.resource_type) }} · {{ item.description || '根据当前套餐安排的旅居内容' }}</p><small>{{ item.address || '酒店内' }} · {{ item.start_time && item.end_time ? `${item.start_time.slice(0,5)} – ${item.end_time.slice(0,5)}` : '场次以确认结果为准' }}</small></div><strong>×{{ item.quantity_per_package }}</strong></div></div></section>

    <section class="moments-section"><div class="editorial-heading"><div><div class="eyebrow">MOMENTS</div><h2>体验瞬间</h2></div><span class="section-caption">Demo atmosphere images · 非酒店真实供图</span></div><div class="moments-grid"><MediaImage v-for="(item, index) in gallery" :key="item.id" :media="item" :aspect="index === 1 ? 'gallery' : 'card'" /></div></section>

    <section v-if="social" class="travel-note-section"><div class="travel-note-label"><span>TRAVEL NOTE</span><strong>旅行灵感</strong><button @click="copySocial">复制文案 ↗</button></div><div class="travel-note-copy"><p v-for="(line, index) in social.content.split('\n')" :key="index" :class="{ hashtag: line.startsWith('#'), first: index === 0 }">{{ line }}</p></div></section>

    <section v-if="poster" class="share-section"><div class="share-copy"><div class="eyebrow">SHARE THE EXPERIENCE</div><h2>把这段杭州体验<br /><em>分享给同行的人。</em></h2><p>现有产品海报已经为这套套餐准备好。可以放大查看、下载，或复制上面的旅行灵感。</p><div class="share-actions"><el-button type="primary" @click="posterDialog = true">查看海报</el-button><el-button plain @click="downloadPoster(poster)">下载 SVG 海报</el-button></div></div><button class="poster-preview" @click="posterDialog = true"><div v-html="poster.poster_svg" /><span>点击放大 ↗</span></button></section>

    <section class="concierge-section"><div class="concierge-header"><div class="eyebrow">ASK STAYSCAPE</div><h2>问问你的杭州旅居助手</h2><p>关于儿童年龄、雨天、过敏和场次，都可以继续问。</p></div><div class="concierge-quick"><button v-for="item in ['适合6岁小朋友吗？', '下雨还能体验吗？', '花生过敏需要注意什么？', '还有其他室内体验吗？']" :key="item" @click="question = item; consult()">{{ item }}</button></div><div class="concierge-chat"><div v-for="(chat, index) in chats" :key="index" :class="['concierge-bubble', chat.user ? 'is-user' : '']"><span>{{ chat.user || chat.answer }}</span><div v-if="chat.suggestions?.length" class="chat-suggestions"><ProductCard v-for="suggestion in chat.suggestions" :key="suggestion.id" :product="suggestion" public-view /></div><div v-if="chat.follow_up_questions?.length" class="chat-followups"><button v-for="item in chat.follow_up_questions" :key="item" @click="question = item">{{ item }}</button></div></div><div v-if="consultLoading" class="concierge-bubble">正在查看实时场次…</div></div><div class="concierge-input"><el-input v-model="question" placeholder="例如：还有什么适合雨天的？" @keyup.enter="consult" /><el-button type="primary" @click="consult">发送</el-button></div></section>

    <section class="booking-bar"><div><div class="eyebrow">A SOFT COMMITMENT</div><h2>想把今晚留给这段体验吗？</h2><p>比赛版本不收款。提交预约意向后，酒店会根据实时房量、场次和过敏信息联系确认。</p></div><div class="booking-bar__right"><div><strong>¥{{ product.suggested_price }}</strong><span>/ family · 剩余 {{ product.sale_quantity }} 套</span></div><el-button type="primary" size="large" :disabled="product.sale_quantity <= 0" @click="openIntent">提交预约意向 →</el-button></div></section>

    <el-dialog v-model="posterDialog" title="分享这段杭州体验" width="min(92vw, 560px)" class="poster-dialog"><div v-if="poster?.poster_svg" class="poster-dialog__image" v-html="poster.poster_svg" /><template #footer><el-button @click="posterDialog = false">关闭</el-button><el-button type="primary" @click="downloadPoster(poster)">下载海报</el-button></template></el-dialog>
    <el-dialog v-model="intentDialog" title="确认预约需求" width="min(94vw, 720px)"><el-form label-position="top"><el-form-item label="原始需求（保留给酒店）" required><el-input v-model="form.natural_language" type="textarea" :rows="4" maxlength="800" show-word-limit placeholder="例如：一家四口，孩子6岁和9岁，预算1000元，下午三点到，下雨，孩子喜欢玩，不想喝茶。" /><div class="form-tip"><el-button link type="primary" @click="parseIntent">重新解析这句话</el-button> 解析后仍可直接修改下方确认字段。</div></el-form-item><div class="intent-summary"><span>入住 {{ intentNeeds.target_date || product.target_date }}</span><span>{{ intentNeeds.adult_count }} 成人 + {{ intentNeeds.child_count }} 儿童</span><span>预算 ¥{{ intentNeeds.budget }}</span></div><div class="form-grid"><el-form-item label="成人数量"><el-input-number v-model="intentNeeds.adult_count" :min="1" :max="20" style="width:100%" /></el-form-item><el-form-item label="儿童数量"><el-input-number v-model="intentNeeds.child_count" :min="0" :max="20" style="width:100%" @change="syncIntentAges" /></el-form-item><el-form-item v-if="intentNeeds.child_count" class="full" label="每位儿童年龄"><div class="age-row"><el-input-number v-for="(_, index) in intentNeeds.child_ages" :key="index" v-model="intentNeeds.child_ages[index]" :min="0" :max="18" :controls="false" /></div></el-form-item><el-form-item label="预算上限"><el-input v-model="intentNeeds.budget"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="到店时间"><el-time-picker v-model="intentNeeds.arrival_time" value-format="HH:mm:ss" format="HH:mm" style="width:100%" /></el-form-item><el-form-item label="体验时间偏好"><el-time-picker v-model="intentNeeds.preferred_experience_time" value-format="HH:mm:ss" format="HH:mm" style="width:100%" /></el-form-item><el-form-item label="偏好体验"><el-select v-model="intentNeeds.interests" multiple filterable allow-create collapse-tags style="width:100%"><el-option label="主题乐园" value="THEME_PARK" /><el-option label="运动娱乐" value="SPORT" /><el-option label="夜游" value="NIGHTLIFE" /><el-option label="旅拍" value="PHOTO" /><el-option label="美食" value="FOOD" /><el-option label="自然" value="NATURE" /><el-option label="文化手作" value="CULTURE" /></el-select></el-form-item><el-form-item label="明确不喜欢"><el-select v-model="intentNeeds.negative_interests" multiple filterable allow-create collapse-tags style="width:100%"><el-option label="茶文化" value="TEA" /><el-option label="博物馆" value="CULTURE" /><el-option label="走很多路" value="CITY_WALK" /><el-option label="运动" value="SPORT" /></el-select></el-form-item><el-form-item label="饮食禁忌"><el-select v-model="intentNeeds.dietary_restrictions" multiple filterable allow-create collapse-tags style="width:100%"><el-option label="不吃辣" value="不吃辣" /><el-option label="素食" value="素食" /><el-option label="不吃海鲜" value="不吃海鲜" /></el-select></el-form-item><el-form-item label="过敏信息"><el-input v-model="intentNeeds.allergy_information" placeholder="没有可以留空，例如花生过敏" /></el-form-item><el-form-item class="full" label="联系人与电话"><div class="form-grid"><el-input v-model="form.contact_name" placeholder="怎么称呼" /><el-input v-model="form.contact_phone" placeholder="便于酒店联系确认" /></div></el-form-item></div></el-form><div class="safety-callout">预约将使用右侧确认后的成人数、儿童年龄、预算、时间、饮食和过敏信息，不会再次用原话覆盖。</div><template #footer><el-button @click="intentDialog = false">取消</el-button><el-button type="primary" :loading="intentLoading" @click="submitIntent">提交并暂留1套</el-button></template></el-dialog>
  </div>
  <div v-else class="home-empty"><div class="empty-mark">S</div><h3>这段体验暂时离开了</h3><p>它可能刚刚被预约或库存发生变化。</p><el-button type="primary" @click="$router.push('/visitor/products')">回到体验列表</el-button></div>
</template>

<style scoped>
.product-detail-hero{position:relative;min-height:610px;border-radius:26px;overflow:hidden;background:#18332f;color:#fff}.product-detail-hero>.media-image{position:absolute;inset:0}.product-detail-hero__veil{position:absolute;inset:0;background:linear-gradient(90deg,rgba(12,35,31,.8),rgba(12,35,31,.18) 70%),linear-gradient(0deg,rgba(12,35,31,.62),transparent 45%)}.product-detail-hero__content{position:absolute;left:7%;bottom:9%;max-width:700px}.product-detail-hero h1{font-size:clamp(36px,5vw,70px);line-height:1.05;letter-spacing:-2px;margin:18px 0 14px}.product-detail-hero p{font-size:18px;line-height:1.7;max-width:600px;color:rgba(255,255,255,.86);margin:0}.product-detail-hero__meta{display:flex;align-items:baseline;gap:10px;margin-top:30px;font-size:13px;color:rgba(255,255,255,.8)}.product-detail-hero__meta strong{font-size:38px;color:#fff}.product-detail-hero__meta i{height:18px;width:1px;background:rgba(255,255,255,.5);margin:0 5px}.back-to-list{position:absolute;top:24px;left:26px;color:#fff;font-size:12px;padding:8px 12px;border:1px solid rgba(255,255,255,.35);border-radius:999px;background:rgba(0,0,0,.16)}.detail-intro-line{display:flex;justify-content:space-between;gap:12px;padding:22px 4px;color:var(--muted);font-size:11px;letter-spacing:.12em;border-bottom:1px solid var(--line)}.story-layout{display:grid;grid-template-columns:1fr 300px;gap:15%;padding:105px 7% 85px;align-items:end}.story-copy h2{font-family:Georgia,'Songti SC',serif;font-size:clamp(34px,4vw,58px);font-weight:500;line-height:1.13;margin:16px 0 24px}.story-copy h2::first-letter{color:var(--gold)}.story-lead{font-size:20px;line-height:1.9;color:var(--ink);max-width:620px}.story-note{font-size:13px;line-height:1.8;color:var(--muted);max-width:560px}.story-fact{border-top:1px solid var(--ink);padding-top:18px;display:grid;grid-template-columns:1fr 1fr;gap:7px;align-items:end}.fact-number{font-size:80px;line-height:.8;font-weight:700;color:var(--teal)}.story-fact span:nth-child(2){font-size:14px;line-height:1.6}.story-fact small{grid-column:1/-1;color:var(--muted);font-size:11px;margin-top:14px}.experience-section,.moments-section,.concierge-section{padding:0 7% 90px}.editorial-heading{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:24px}.editorial-heading h2{font-family:Georgia,'Songti SC',serif;font-size:36px;font-weight:500;margin:10px 0 0}.section-caption{color:var(--muted);font-size:12px}.experience-list{border-top:1px solid var(--ink)}.experience-row{display:grid;grid-template-columns:150px 1fr 60px;gap:20px;align-items:start;padding:26px 0;border-bottom:1px solid var(--line)}.experience-index{color:var(--teal);letter-spacing:.15em;font-size:12px;font-weight:700;padding-top:3px}.experience-main h3{font-size:19px;margin:0 0 7px}.experience-main p{color:var(--ink);font-size:14px;margin:0 0 8px;line-height:1.6}.experience-main small{color:var(--muted);font-size:12px}.experience-row>strong{font-size:20px;text-align:right}.moments-grid{display:grid;grid-template-columns:1.1fr .8fr 1fr;gap:12px;align-items:start}.moments-grid .media-image:nth-child(2){margin-top:44px}.moments-grid .media-image:nth-child(3){margin-top:18px}.travel-note-section{display:grid;grid-template-columns:220px 1fr;gap:8%;background:#ecf5ef;margin:0 0 90px;padding:72px 14%}.travel-note-label{display:flex;flex-direction:column;gap:7px}.travel-note-label span{font-size:12px;letter-spacing:.16em;color:var(--teal);font-weight:700}.travel-note-label strong{font-family:Georgia,serif;font-size:26px;font-weight:500}.travel-note-label button{width:max-content;border:0;border-bottom:1px solid var(--teal);background:none;color:var(--teal);padding:0 0 4px;margin-top:20px;cursor:pointer}.travel-note-copy{max-width:620px}.travel-note-copy p{font-family:Georgia,'Songti SC',serif;font-size:19px;line-height:1.9;margin:0;color:var(--ink)}.travel-note-copy p.first{font-size:30px;margin-bottom:12px}.travel-note-copy p.hashtag,.travel-note-copy .hashtag{font-family:inherit;color:var(--teal);font-size:12px;line-height:1.8;margin-top:2px}.share-section{display:grid;grid-template-columns:1fr 300px;gap:12%;align-items:center;padding:15px 12% 100px}.share-copy h2{font-family:Georgia,'Songti SC',serif;font-size:40px;font-weight:500;line-height:1.2;margin:14px 0}.share-copy p{max-width:440px;color:var(--muted);font-size:14px;line-height:1.8}.share-actions{display:flex;gap:10px;margin-top:24px}.poster-preview{position:relative;border:0;background:#18332f;border-radius:8px;padding:16px;cursor:pointer;box-shadow:0 22px 50px rgba(20,55,48,.2);transform:rotate(2deg);transition:transform .25s}.poster-preview:hover{transform:rotate(0) translateY(-4px)}.poster-preview>div{line-height:0}.poster-preview :deep(svg){width:100%;height:auto;display:block}.poster-preview>span{position:absolute;bottom:24px;right:24px;color:#fff;background:rgba(0,0,0,.45);border-radius:999px;padding:7px 10px;font-size:10px}.concierge-section{background:#18332f;color:#eef8f3;padding-top:70px}.concierge-header h2{font-family:Georgia,'Songti SC',serif;font-size:38px;font-weight:500;margin:12px 0}.concierge-header p{color:#a8c8bd;font-size:13px}.concierge-quick{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}.concierge-quick button,.chat-followups button{border:1px solid rgba(217,239,230,.25);border-radius:999px;background:transparent;color:#d9eee6;padding:9px 12px;font-size:12px;cursor:pointer}.concierge-quick button:hover,.chat-followups button:hover{background:rgba(255,255,255,.1)}.concierge-chat{display:grid;gap:10px;max-height:340px;overflow:auto;margin:20px 0}.concierge-bubble{max-width:80%;padding:13px 16px;border-radius:4px 14px 14px 14px;background:rgba(255,255,255,.1);line-height:1.7;font-size:13px}.concierge-bubble.is-user{justify-self:end;border-radius:14px 4px 14px 14px;background:#dcefe7;color:var(--ink)}.concierge-bubble .chat-suggestions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));margin-top:15px}.concierge-bubble .product-card{background:#fff;color:var(--ink)}.concierge-input{display:flex;gap:8px;max-width:680px}.concierge-input :deep(.el-input__wrapper){background:rgba(255,255,255,.95)}.booking-bar{display:flex;justify-content:space-between;align-items:center;gap:30px;padding:56px 7%;background:#f5eee1}.booking-bar h2{font-family:Georgia,'Songti SC',serif;font-size:30px;font-weight:500;margin:10px 0}.booking-bar p{max-width:610px;color:var(--muted);font-size:13px;line-height:1.7}.booking-bar__right{text-align:right;min-width:210px}.booking-bar__right strong{font-size:30px;color:var(--teal-dark)}.booking-bar__right span{display:block;color:var(--muted);font-size:12px;margin:3px 0 15px}.poster-dialog__image{background:#f2eee4;padding:18px}.poster-dialog__image :deep(svg){width:100%;height:auto;display:block}.form-tip{margin-top:7px;color:var(--muted);font-size:12px;line-height:1.6}.detail-loading{min-height:360px;display:grid;place-items:center;color:var(--muted)}.detail-loading span,.home-loading span{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--teal);box-shadow:16px 0 var(--gold),32px 0 var(--teal);margin-right:42px;animation:stay-breathe 1.2s infinite alternate}.home-empty{text-align:center;padding:75px 24px;border:1px solid var(--line);background:#fff}.empty-mark{margin:0 auto 14px;width:42px;height:42px;display:grid;place-items:center;border-radius:14px;background:var(--teal);color:#fff;font-family:Georgia,serif;font-size:25px}.home-empty h3{font-family:Georgia,serif;font-size:24px;font-weight:500;margin:10px 0}.home-empty p{color:var(--muted);font-size:13px;line-height:1.8}.home-empty .el-button{margin-top:12px}@media(max-width:800px){.product-detail-hero{min-height:520px}.product-detail-hero__content{left:24px;right:24px}.product-detail-hero__meta{flex-wrap:wrap}.detail-intro-line{display:grid;grid-template-columns:1fr 1fr}.story-layout,.share-section,.travel-note-section{grid-template-columns:1fr;padding:65px 5%;gap:32px}.story-fact{max-width:300px}.experience-section,.moments-section,.concierge-section{padding-left:5%;padding-right:5%}.experience-row{grid-template-columns:90px 1fr 35px;gap:10px}.moments-grid{grid-template-columns:1fr 1fr}.moments-grid .media-image:nth-child(2),.moments-grid .media-image:nth-child(3){margin-top:0}.moments-grid .media-image:first-child{grid-column:1/-1}.booking-bar{display:block;padding:42px 5%}.booking-bar__right{text-align:left;margin-top:25px}.concierge-bubble .chat-suggestions{grid-template-columns:1fr}}@keyframes stay-breathe{to{transform:translateX(7px);opacity:.5}}
.intent-summary{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}.intent-summary span{padding:7px 10px;border-radius:999px;background:#edf7f2;color:var(--teal-dark);font-size:12px}.age-row{display:flex;gap:8px;flex-wrap:wrap}.age-row :deep(.el-input-number){width:92px}.safety-callout{margin-top:12px;padding:11px 13px;border-radius:10px;background:#fff8eb;color:#8b6a36;font-size:12px;line-height:1.6}
</style>
