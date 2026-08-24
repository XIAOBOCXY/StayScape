<script setup lang="ts">
import { posterSvgDataUri } from '../../utils/posterSvg'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import MediaImage from '../../components/MediaImage.vue'
import ProductCard from '../../components/ProductCard.vue'
import type { MarketingAsset, TravelProduct } from '../../types'
import { experienceLabelZh, experienceMoments, mediaForProduct, mediaForResource } from '../../utils/productMedia'
import { publicTravelCopy } from '../../utils/publicTravelCopy'
import { loadVisitorProfile, saveVisitorProfile, type VisitorProfile, visitorConversationId } from '../../utils/visitorProfile'

const route = useRoute()
const router = useRouter()
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

const gallery = computed(() => experienceMoments(product.value))
const resourceCount = computed(() => product.value?.resources.length || 0)
const crowdLabel = computed(() => ({ FAMILY: '亲子出行', COUPLE: '双人同游', FRIENDS: '好友相聚', SOLO: '一个人慢游' } as Record<string, string>)[String(product.value?.target_crowd || '')] || '城市旅行')
const socialLines = computed(() => String(social.value?.content || '').split('\n').map((line) => line.trim()).filter(Boolean).slice(0, 6))
const poster = computed(() => product.value?.marketing_assets?.find((asset) => asset.asset_type === 'POSTER'))
const social = computed(() => product.value?.marketing_assets?.find((asset) => asset.asset_type === 'SOCIAL_POST'))
const hero = computed(() => mediaForProduct(product.value)[0])
// The formatted SVG is the share asset: it reserves dedicated space for the
// route and title.  A Wan image remains the product hero, not a substitute
// that can hide text in a sharing preview.
const posterVisual = computed(() => poster.value?.poster_svg ? posterSvgDataUri(poster.value.poster_svg) : (poster.value?.image_url || ''))
const publicTitle = computed(() => publicTravelCopy(
  product.value?.marketing_title || product.value?.marketing_content,
  '把杭州的一段时光留给今天。',
))
const story = computed(() => {
  const fallback = product.value ? '从 ' + product.value.theme + ' 出发，把一段想去的杭州留给今晚。' : ''
  return publicTravelCopy(product.value?.marketing_content || product.value?.recommendation_reason, fallback)
})
const recommendationNote = computed(() => publicTravelCopy(
  product.value?.recommendation_reason,
  '住进杭州，慢慢体验这座城市的另一面。',
))

function resourceSummary(item: TravelProduct['resources'][number]) {
  const fallback = item.resource_type === 'ROOM'
    ? '把行李放好，留一晚慢慢休息。'
    : item.resource_type === 'HOTEL_SERVICE'
      ? '在酒店里留出一点轻松的时间。'
      : '把这段城市体验排进当天的行程里。'
  return publicTravelCopy(item.description, fallback)
}

function resourceMeta(item: TravelProduct['resources'][number]) {
  const place = item.address || (item.resource_type === 'ROOM' || item.resource_type === 'HOTEL_SERVICE' ? '酒店内' : '杭州')
  const time = item.start_time && item.end_time ? item.start_time.slice(0, 5) + ' – ' + item.end_time.slice(0, 5) : '时间以确认信息为准'
  return place + ' · ' + time
}

function itineraryTime(item: TravelProduct['resources'][number], index: number) {
  if (item.start_time && item.end_time) return `${item.start_time.slice(0, 5)} – ${item.end_time.slice(0, 5)}`
  if (item.resource_type === 'ROOM') return index === 0 ? '15:00 后办理入住' : '次日 12:00 前退房'
  if (item.resource_type === 'HOTEL_SERVICE') return '入住后按酒店确认时间体验'
  return '具体时间以预约确认信息为准'
}

function itineraryAction(item: TravelProduct['resources'][number]) {
  if (item.resource_type === 'ROOM') return '办理入住，放下行李后慢慢开始'
  if (item.resource_type === 'HOTEL_SERVICE') return '到店后向前台确认使用方式'
  return item.address ? `抵达 ${item.address} 后开始体验` : '出发前留意商家发送的预约信息'
}

function customizeProduct() {
  if (!product.value) return
  router.push({
    path: '/visitor/recommend',
    query: {
      q: `想把${product.value.product_name}改成自己的行程，${product.value.target_date}出发`,
      product: String(product.value.id),
    },
  })
}

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
    showToast('预约意向已提交，酒店会尽快与你确认出行安排。'); intentDialog.value = false
  } catch (e) { showToast(errorMessage(e)) }
  finally { intentLoading.value = false }
}

onMounted(load)
</script>

<template>
  <div v-if="loading" class="detail-loading"><span /> 正在打开这段杭州体验…</div>
  <div v-else-if="product" class="visitor-product-detail">
    <section class="product-detail-hero">
      <img v-if="poster?.image_url" class="product-detail-hero__ai" :src="poster.image_url" :alt="poster.title || product.product_name" />
      <MediaImage v-else :media="hero" aspect="hero" />
      <div class="product-detail-hero__veil" />
      <router-link to="/visitor/products" class="back-to-list">← 返回体验列表</router-link>
      <div class="product-detail-hero__content">
        <div class="hero-kicker"><span>{{ product.theme || '杭州周末提案' }}</span><i /> <span>{{ crowdLabel }}</span></div>
        <h1>{{ product.product_name }}</h1>
        <p>{{ publicTitle }}</p>
      </div>
      <div class="hero-price"><strong>¥{{ product.suggested_price }}</strong><span>起 / 套</span></div>
    </section>

    <section class="trip-strip">
      <div><span>出行日期</span><strong>{{ product.target_date }}</strong></div>
      <div><span>适合谁去</span><strong>{{ crowdLabel }}</strong></div>
      <div><span>已安排</span><strong>{{ resourceCount }} 项旅居内容</strong></div>
    </section>

    <main class="detail-content">
      <section class="compact-story">
        <div class="section-heading">
          <div><span class="section-kicker">这趟的亮点</span><h2>{{ product.theme || '一段刚刚好的杭州时光' }}</h2></div>
          <span class="section-count">01</span>
        </div>
        <p class="story-lead">{{ story }}</p>
        <p class="story-note">{{ recommendationNote }}</p>
        <div class="story-tags"><span>{{ crowdLabel }}</span><span>{{ product.target_date }}</span><span>杭州周末</span></div>
      </section>

      <section class="itinerary-section">
        <div class="section-heading">
          <div><span class="section-kicker">怎么度过</span><h2>这一趟已经为你排好</h2></div>
          <span class="section-count">02</span>
        </div>
        <div class="itinerary-list">
          <article v-for="(item, index) in product.resources" :key="item.id" class="itinerary-card">
            <div class="itinerary-card__image"><MediaImage :media="mediaForResource(product, item, index)" aspect="card" /></div>
            <div class="itinerary-card__body">
              <div class="itinerary-card__top"><span>{{ experienceLabelZh(item.resource_type) }}</span><b>第 {{ index + 1 }} 段</b></div>
              <h3>{{ item.resource_name }}</h3>
              <p>{{ resourceSummary(item) }}</p>
              <strong class="itinerary-card__time">{{ itineraryTime(item, index) }}</strong>
              <small>{{ itineraryAction(item) }} · {{ resourceMeta(item) }}</small>
            </div>
            <strong class="itinerary-card__quantity">×{{ item.quantity_per_package }}</strong>
          </article>
        </div>
      </section>

      <section v-if="gallery.length" class="moments-section">
        <div class="section-heading">
          <div><span class="section-kicker">体验瞬间</span><h2>每一段都有不同的风景</h2></div>
          <span class="section-count">03</span>
        </div>
        <div class="moments-grid">
          <figure v-for="(moment, index) in gallery" :key="moment.media.id">
            <MediaImage :media="moment.media" aspect="card" />
            <figcaption><span>第 {{ index + 1 }} 段 · {{ experienceLabelZh(moment.resource_type) }}</span><strong>{{ moment.resource_name }}</strong></figcaption>
          </figure>
        </div>
      </section>

      <section v-if="social" class="travel-note-section">
        <div class="travel-note-heading"><span class="section-kicker">旅行者的周末记录</span><h2>带走这段旅行灵感</h2><button @click="copySocial">复制这段文字</button></div>
        <div class="travel-note-copy"><p v-for="(line, index) in socialLines" :key="index" :class="{ first: index === 0, hashtag: line.startsWith('#') }">{{ line }}</p></div>
      </section>

      <section v-if="poster" class="share-section">
        <button class="poster-preview" @click="posterDialog = true"><img v-if="posterVisual" :src="posterVisual" :alt="poster.title" /></button>
        <div class="share-copy"><span class="section-kicker">一张可直接分享的海报</span><h2>把这趟杭州<br />发给同行的人</h2><p>这张海报会根据当前产品内容生成，适合保存、转发或继续做成你的旅行笔记。</p><div class="share-actions"><el-button type="primary" @click="posterDialog = true">查看海报</el-button><el-button plain @click="downloadPoster(poster)">下载 SVG</el-button></div></div>
      </section>

      <section class="concierge-section">
        <div class="concierge-header"><span class="section-kicker">在线问问</span><h2>问问杭州旅居助手</h2><p>关于同行人、天气、儿童年龄或饮食偏好，都可以直接问。</p></div>
        <div class="concierge-quick"><button v-for="item in ['适合6岁小朋友吗？', '下雨还能体验吗？', '花生过敏需要注意什么？', '还有什么室内体验？']" :key="item" @click="question = item; consult()">{{ item }}</button></div>
        <div v-if="chats.length || consultLoading" class="concierge-chat"><div v-for="(chat, index) in chats" :key="index" :class="['concierge-bubble', chat.user ? 'is-user' : '']"><span>{{ chat.user || chat.answer }}</span><div v-if="chat.suggestions?.length" class="chat-suggestions"><ProductCard v-for="suggestion in chat.suggestions" :key="suggestion.id" :product="suggestion" public-view compact /></div><div v-if="chat.follow_up_questions?.length" class="chat-followups"><button v-for="item in chat.follow_up_questions" :key="item" @click="question = item">{{ item }}</button></div></div><div v-if="consultLoading" class="concierge-bubble">正在为你查看可用体验…</div></div>
        <div class="concierge-input"><el-input v-model="question" placeholder="例如：下雨天还适合去吗？" @keyup.enter="consult" /><el-button type="primary" @click="consult">发送</el-button></div>
      </section>
    </main>

    <section class="booking-bar">
      <div><span class="section-kicker">想去就先留个位置</span><p>提交预约意向后，酒店会和你确认出行安排。</p></div>
      <div class="booking-bar__right"><strong>¥{{ product.suggested_price }}</strong><span>起 / 套</span><el-button plain @click="customizeProduct">调整行程</el-button><el-button type="primary" :disabled="product.sale_quantity <= 0" @click="openIntent">提交预约</el-button></div>
    </section>

    <el-dialog v-model="posterDialog" title="分享这段杭州体验" width="min(92vw, 560px)" class="poster-dialog"><img v-if="posterVisual" class="poster-dialog__image" :src="posterVisual" :alt="poster?.title" /><template #footer><el-button @click="posterDialog = false">关闭</el-button><el-button v-if="poster?.poster_svg" type="primary" @click="downloadPoster(poster)">下载 SVG 海报</el-button></template></el-dialog>
    <el-dialog v-model="intentDialog" title="确认预约需求" width="min(94vw, 720px)"><el-form label-position="top"><el-form-item label="原始需求（保留给酒店）" required><el-input v-model="form.natural_language" type="textarea" :rows="4" maxlength="800" show-word-limit placeholder="例如：一家四口，孩子6岁和9岁，预算1000元，下午三点到，下雨，孩子喜欢玩，不想喝茶。" /><div class="form-tip"><el-button link type="primary" @click="parseIntent">重新解析这句话</el-button> 解析后仍可直接修改下方确认字段。</div></el-form-item><div class="intent-summary"><span>入住 {{ intentNeeds.target_date || product.target_date }}</span><span>{{ intentNeeds.adult_count }} 成人 + {{ intentNeeds.child_count }} 儿童</span><span>预算 ¥{{ intentNeeds.budget }}</span></div><div class="form-grid"><el-form-item label="成人数量"><el-input-number v-model="intentNeeds.adult_count" :min="1" :max="20" style="width:100%" /></el-form-item><el-form-item label="儿童数量"><el-input-number v-model="intentNeeds.child_count" :min="0" :max="20" style="width:100%" @change="syncIntentAges" /></el-form-item><el-form-item v-if="intentNeeds.child_count" class="full" label="每位儿童年龄"><div class="age-row"><el-input-number v-for="(_, index) in intentNeeds.child_ages" :key="index" v-model="intentNeeds.child_ages[index]" :min="0" :max="18" :controls="false" /></div></el-form-item><el-form-item label="预算上限"><el-input v-model="intentNeeds.budget"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="到店时间"><el-time-picker v-model="intentNeeds.arrival_time" value-format="HH:mm:ss" format="HH:mm" style="width:100%" /></el-form-item><el-form-item label="体验时间偏好"><el-time-picker v-model="intentNeeds.preferred_experience_time" value-format="HH:mm:ss" format="HH:mm" style="width:100%" /></el-form-item><el-form-item label="偏好体验"><el-select v-model="intentNeeds.interests" multiple filterable allow-create collapse-tags style="width:100%"><el-option label="主题乐园" value="THEME_PARK" /><el-option label="运动娱乐" value="SPORT" /><el-option label="夜游" value="NIGHTLIFE" /><el-option label="旅拍" value="PHOTO" /><el-option label="美食" value="FOOD" /><el-option label="自然" value="NATURE" /><el-option label="文化手作" value="CULTURE" /></el-select></el-form-item><el-form-item label="明确不喜欢"><el-select v-model="intentNeeds.negative_interests" multiple filterable allow-create collapse-tags style="width:100%"><el-option label="茶文化" value="TEA" /><el-option label="博物馆" value="CULTURE" /><el-option label="走很多路" value="CITY_WALK" /><el-option label="运动" value="SPORT" /></el-select></el-form-item><el-form-item label="饮食禁忌"><el-select v-model="intentNeeds.dietary_restrictions" multiple filterable allow-create collapse-tags style="width:100%"><el-option label="不吃辣" value="不吃辣" /><el-option label="素食" value="素食" /><el-option label="不吃海鲜" value="不吃海鲜" /></el-select></el-form-item><el-form-item label="过敏信息"><el-input v-model="intentNeeds.allergy_information" placeholder="没有可以留空，例如花生过敏" /></el-form-item><el-form-item class="full" label="联系人与电话"><div class="form-grid"><el-input v-model="form.contact_name" placeholder="怎么称呼" /><el-input v-model="form.contact_phone" placeholder="便于酒店联系确认" /></div></el-form-item></div></el-form><div class="safety-callout">预约将使用右侧确认后的成人数、儿童年龄、预算、时间、饮食和过敏信息，不会再次用原话覆盖。</div><template #footer><el-button @click="intentDialog = false">取消</el-button><el-button type="primary" :loading="intentLoading" @click="submitIntent">提交并暂留1套</el-button></template></el-dialog>

  </div>
  <div v-else class="home-empty"><div class="empty-mark">S</div><h3>这段体验暂时离开了</h3><p>它可能刚刚被其他旅人安排上了。</p><el-button type="primary" @click="$router.push('/visitor/products')">回到体验列表</el-button></div>
</template>

<style scoped>
.visitor-product-detail{padding-bottom:86px}.detail-loading{min-height:300px;display:grid;place-items:center;color:var(--muted);font-size:14px}.detail-loading span{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--teal);box-shadow:14px 0 var(--gold),28px 0 var(--teal);margin-right:38px;animation:stay-breathe 1.2s infinite alternate}.product-detail-hero{position:relative;min-height:318px;border-radius:16px;overflow:hidden;background:#173b35;color:#fff}.product-detail-hero>.media-image{position:absolute;inset:0;min-height:100%;border-radius:inherit}.product-detail-hero__veil{position:absolute;inset:0;background:linear-gradient(90deg,rgba(12,39,34,.82),rgba(12,39,34,.2) 75%),linear-gradient(0deg,rgba(12,39,34,.65),transparent 52%)}.back-to-list{position:absolute;z-index:2;top:14px;left:14px;padding:6px 9px;border:1px solid rgba(255,255,255,.42);border-radius:999px;background:rgba(0,0,0,.16);color:#fff;font-size:11px}.product-detail-hero__content{position:absolute;z-index:2;left:5%;right:18%;bottom:30px;max-width:700px}.hero-kicker,.section-kicker{display:inline-flex;align-items:center;gap:8px;color:#23796c;font-size:11px;font-weight:700;letter-spacing:.08em}.hero-kicker{color:rgba(255,255,255,.9)}.hero-kicker i{width:3px;height:3px;border-radius:50%;background:currentColor}.product-detail-hero h1{margin:9px 0 7px;font-size:clamp(27px,3.3vw,40px);line-height:1.13;letter-spacing:-.8px}.product-detail-hero p{max-width:600px;margin:0;color:rgba(255,255,255,.88);font-size:13px;line-height:1.62}.hero-price{position:absolute;z-index:2;right:5%;bottom:29px;text-align:right}.hero-price strong{display:block;font-size:27px;line-height:1;color:#fff}.hero-price span{display:block;margin-top:5px;color:rgba(255,255,255,.78);font-size:10px}.trip-strip{display:grid;grid-template-columns:repeat(3,1fr);margin:10px 0 0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#fff}.trip-strip>div{min-width:0;padding:11px 14px;border-right:1px solid var(--line)}.trip-strip>div:last-child{border-right:0}.trip-strip span{display:block;margin-bottom:4px;color:var(--muted);font-size:10px}.trip-strip strong{display:block;overflow:hidden;color:var(--ink);font-size:13px;text-overflow:ellipsis;white-space:nowrap}.detail-content{max-width:960px;margin:0 auto;padding:26px 3% 14px}.compact-story,.itinerary-section,.moments-section{margin-bottom:26px}.section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:12px}.section-heading h2,.travel-note-heading h2,.share-copy h2,.concierge-header h2{margin:5px 0 0;color:var(--ink);font-family:var(--font-sans);font-size:21px;font-weight:680;line-height:1.22}.section-count{color:#aac8be;font-family:var(--font-mono);font-size:18px;line-height:1}.story-lead{max-width:760px;margin:0;color:var(--ink);font-size:14px;line-height:1.72}.story-note{max-width:720px;margin:8px 0 0;color:var(--muted);font-size:12px;line-height:1.62}.story-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.story-tags span{padding:5px 8px;border-radius:999px;background:#eff7f3;color:#2b7569;font-size:10px}.itinerary-list{display:grid;gap:7px}.itinerary-card{position:relative;display:grid;grid-template-columns:118px minmax(0,1fr) auto;gap:11px;align-items:stretch;min-height:112px;padding:7px;border:1px solid var(--line);border-radius:12px;background:#fff;box-shadow:0 4px 13px rgba(35,64,55,.03)}.itinerary-card__image,.itinerary-card__image .media-image{height:96px;border-radius:8px;overflow:hidden}.itinerary-card__body{min-width:0;padding:1px 0}.itinerary-card__top{display:flex;align-items:center;justify-content:space-between;gap:8px}.itinerary-card__top span{padding:3px 6px;border-radius:999px;background:#edf7f2;color:#287567;font-size:9px;font-weight:700}.itinerary-card__top b{color:#9aafa7;font-size:9px;font-weight:500}.itinerary-card h3{overflow:hidden;margin:5px 0 3px;color:var(--ink);font-size:14px;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}.itinerary-card p{display:-webkit-box;overflow:hidden;margin:0;color:#576963;font-size:11px;line-height:1.48;-webkit-box-orient:vertical;-webkit-line-clamp:2}.itinerary-card small{display:block;overflow:hidden;margin-top:5px;color:#93a19b;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.itinerary-card__quantity{align-self:start;padding:4px 3px 0 0;color:#597a70;font-size:11px}.moments-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.moments-grid figure{margin:0;overflow:hidden;border:1px solid var(--line);border-radius:11px;background:#fff}.moments-grid .media-image{height:148px}.moments-grid figcaption{padding:8px}.moments-grid figcaption span{display:block;overflow:hidden;color:#7e9690;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.moments-grid figcaption strong{display:block;overflow:hidden;margin-top:3px;color:var(--ink);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.travel-note-section{display:grid;grid-template-columns:170px minmax(0,1fr);gap:22px;margin:0 0 24px;padding:17px 18px;border-radius:13px;background:#f0f7f3}.travel-note-heading h2{font-size:19px}.travel-note-heading button{margin-top:9px;padding:0 0 3px;border:0;border-bottom:1px solid #438b7c;background:transparent;color:#317a6d;font-size:11px;cursor:pointer}.travel-note-copy{padding-top:1px}.travel-note-copy p{margin:0;color:#40544d;font-size:12px;line-height:1.6}.travel-note-copy p.first{margin-bottom:5px;color:var(--ink);font-size:14px;font-weight:650}.travel-note-copy p.hashtag{color:#338070;font-size:10px}.share-section{display:grid;grid-template-columns:108px minmax(0,1fr);gap:16px;align-items:center;margin:0 0 24px;padding:12px 14px;border:1px solid var(--line);border-radius:13px;background:#fff}.poster-preview{padding:5px;border:0;border-radius:8px;background:#163d36;box-shadow:0 6px 14px rgba(24,61,54,.16);cursor:pointer}.poster-preview img{display:block;width:100%;height:auto;border-radius:4px}.share-copy h2{font-size:20px}.share-copy p{max-width:560px;margin:7px 0 0;color:var(--muted);font-size:11px;line-height:1.55}.share-actions{display:flex;gap:7px;margin-top:9px}.concierge-section{padding:17px 18px;border:1px solid #d9ebe3;border-radius:13px;background:linear-gradient(135deg,#f5faf7,#eef7f2)}.concierge-header h2{font-size:20px}.concierge-header p{margin:6px 0 0;color:var(--muted);font-size:11px;line-height:1.55}.concierge-quick{display:flex;gap:6px;flex-wrap:wrap;margin:11px 0}.concierge-quick button,.chat-followups button{padding:6px 8px;border:1px solid #cfe4db;border-radius:999px;background:#fff;color:#3a7166;font-size:10px;cursor:pointer}.concierge-chat{display:grid;gap:7px;max-height:230px;overflow:auto;margin:10px 0}.concierge-bubble{max-width:83%;padding:9px 10px;border-radius:5px 11px 11px;background:#fff;color:#3e534c;font-size:11px;line-height:1.55;box-shadow:0 3px 9px rgba(27,77,63,.05)}.concierge-bubble.is-user{justify-self:end;border-radius:11px 5px 11px 11px;background:#dceee7;color:#1f4e43}.chat-suggestions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));margin-top:8px}.chat-suggestions .product-card{background:#fff}.chat-followups{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}.concierge-input{display:flex;gap:7px}.booking-bar{position:sticky;bottom:10px;z-index:11;display:flex;align-items:center;justify-content:space-between;gap:12px;max-width:960px;margin:0 auto;padding:11px 14px;border:1px solid #dce8e2;border-radius:12px;background:rgba(255,255,255,.96);box-shadow:0 8px 24px rgba(33,67,57,.13);backdrop-filter:blur(10px)}.booking-bar p{margin:3px 0 0;color:var(--muted);font-size:11px}.booking-bar__right{display:flex;align-items:center;gap:6px;white-space:nowrap}.booking-bar__right strong{color:#1c685a;font-family:var(--font-mono);font-size:20px}.booking-bar__right span{margin-right:3px;color:var(--muted);font-size:10px}.poster-dialog__image{display:block;width:100%;max-height:72vh;object-fit:contain;margin:0 auto;border-radius:6px;background:#edf4f0}.form-tip{margin-top:7px;color:var(--muted);font-size:12px;line-height:1.6}.intent-summary{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}.intent-summary span{padding:7px 10px;border-radius:999px;background:#edf7f2;color:var(--teal-dark);font-size:12px}.age-row{display:flex;gap:8px;flex-wrap:wrap}.age-row :deep(.el-input-number){width:92px}.safety-callout{margin-top:12px;padding:11px 13px;border-radius:10px;background:#fff8eb;color:#8b6a36;font-size:12px;line-height:1.6}.home-empty{text-align:center;padding:75px 24px;border:1px solid var(--line);background:#fff}.empty-mark{display:grid;place-items:center;width:42px;height:42px;margin:0 auto 14px;border-radius:14px;background:var(--teal);color:#fff;font-family:Georgia,serif;font-size:25px}.home-empty h3{margin:10px 0;color:var(--ink);font-family:Georgia,serif;font-size:24px;font-weight:500}.home-empty p{color:var(--muted);font-size:13px;line-height:1.8}.home-empty .el-button{margin-top:12px}@keyframes stay-breathe{to{transform:translateX(7px);opacity:.5}}@media(max-width:800px){.visitor-product-detail{padding-bottom:76px}.product-detail-hero{min-height:260px;border-radius:12px}.back-to-list{top:10px;left:10px;font-size:10px}.product-detail-hero__content{right:14px;bottom:15px;left:14px}.product-detail-hero h1{margin:7px 0 5px;font-size:25px;letter-spacing:-.5px}.product-detail-hero p{font-size:11px;line-height:1.45}.hero-price{right:13px;bottom:15px}.hero-price strong{font-size:20px}.trip-strip{margin-top:8px;border-radius:10px}.trip-strip>div{padding:8px 7px}.trip-strip span{font-size:9px}.trip-strip strong{font-size:10px}.detail-content{padding:20px 0 10px}.compact-story,.itinerary-section,.moments-section{margin-bottom:22px}.section-heading{margin-bottom:10px}.section-heading h2,.travel-note-heading h2,.share-copy h2,.concierge-header h2{font-size:19px}.section-count{font-size:16px}.story-lead{font-size:13px;line-height:1.62}.story-note{font-size:11px;line-height:1.52}.story-tags{margin-top:8px}.itinerary-list{gap:6px}.itinerary-card{grid-template-columns:86px minmax(0,1fr) 18px;gap:7px;min-height:92px;padding:5px;border-radius:10px}.itinerary-card__image,.itinerary-card__image .media-image{height:80px;border-radius:7px}.itinerary-card__body{padding:1px 0}.itinerary-card__top span{padding:2px 5px;font-size:8px}.itinerary-card h3{margin:4px 0 2px;font-size:13px}.itinerary-card p{font-size:10px;line-height:1.38}.itinerary-card small{margin-top:4px;font-size:8px}.itinerary-card__quantity{padding-top:4px;font-size:10px}.moments-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.moments-grid .media-image{height:110px}.moments-grid figure{border-radius:8px}.moments-grid figcaption{padding:6px}.moments-grid figcaption span{font-size:7px}.moments-grid figcaption strong{margin-top:2px;font-size:9px}.travel-note-section{grid-template-columns:1fr;gap:9px;margin-bottom:20px;padding:13px;border-radius:11px}.travel-note-heading h2{font-size:18px}.travel-note-heading button{margin-top:6px}.travel-note-copy p{font-size:11px;line-height:1.5}.travel-note-copy p.first{font-size:13px}.share-section{grid-template-columns:76px minmax(0,1fr);gap:10px;margin-bottom:20px;padding:10px;border-radius:11px}.share-copy h2{font-size:18px}.share-copy p{font-size:10px;line-height:1.45}.share-actions{gap:5px;margin-top:7px}.share-actions :deep(.el-button){padding:6px 7px;font-size:10px}.concierge-section{padding:13px;border-radius:11px}.concierge-header h2{font-size:18px}.concierge-quick{margin:9px 0}.concierge-quick button{padding:5px 7px;font-size:9px}.concierge-input :deep(.el-input__wrapper){min-height:30px}.concierge-input :deep(.el-button){padding:7px 9px}.booking-bar{position:fixed;right:9px;bottom:9px;left:9px;width:auto;padding:9px 10px;border-radius:10px}.booking-bar p{display:none}.booking-bar__right{gap:4px}.booking-bar__right strong{font-size:16px}.booking-bar__right span{display:none}.booking-bar__right :deep(.el-button){padding:7px 8px;font-size:10px}.poster-dialog__image{max-height:67vh}}@media(max-width:390px){.product-detail-hero h1{font-size:23px}.moments-grid .media-image{height:96px}.itinerary-card{grid-template-columns:80px minmax(0,1fr) 16px}.itinerary-card__image,.itinerary-card__image .media-image{height:74px}.booking-bar__right strong{font-size:14px}}
.product-detail-hero__ai{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.itinerary-card__time{display:block;margin-top:6px;color:var(--teal-dark);font-size:11px;font-weight:650}.chat-suggestions{grid-template-columns:1fr!important;gap:7px}.chat-suggestions .product-card--compact{width:100%}
</style>
