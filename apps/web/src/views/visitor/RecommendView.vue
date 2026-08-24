<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { showToast } from 'vant'
import { visitorApi } from '../../api'
import { errorMessage } from '../../api/client'
import ProductCard from '../../components/ProductCard.vue'
import type { Recommendation, TravelProduct } from '../../types'
import { saveVisitorProfile, type VisitorProfile, visitorConversationId } from '../../utils/visitorProfile'

type Stage = 'input' | 'review' | 'results'
type StructuredField = keyof Omit<VisitorProfile, 'natural_language'>

const stage = ref<Stage>('input')
const loading = ref(false)
const results = ref<Recommendation[]>([])
const alternatives = ref<TravelProduct[]>([])
const interpreted = ref<Record<string, any> | null>(null)
const followUps = ref<string[]>([])
const reviewText = ref('')
const manualFields = ref<Set<string>>(new Set())
const form = reactive({ people: '', places: '', notes: '' })
const needs = reactive<VisitorProfile>({
  natural_language: '', target_date: null, weather: 'RAIN', target_crowd: 'FAMILY', adult_count: 2,
  child_count: 0, child_ages: [], budget: '700', interests: [], negative_interests: [], activity_level: 'MEDIUM',
  requested_places: [], dietary_restrictions: [], allergy_information: '', arrival_time: null,
  preferred_experience_time: null, other_requirements: ''
})
const combinedText = computed(() => [form.people, form.places, form.notes].map((item) => item.trim()).filter(Boolean).join('；'))
const valueOf = (key: string, fallback = '未提及') => {
  const value = interpreted.value?.[key]
  if (Array.isArray(value)) return value.length ? value.join('、') : fallback
  return value === undefined || value === null || value === '' ? fallback : String(value)
}
const weatherLabel = computed(() => ({ RAIN: '雨天 / 室内优先', SUNNY: '晴天 / 可安排户外', CLOUDY: '多云 / 灵活组合' }[String(needs.weather)] || needs.weather))

function useExample(text: string) {
  const parts = text.split('；'); form.people = parts[0] || text; form.places = parts[1] || ''; form.notes = parts[2] || ''
}

function toArray(value: unknown) { return Array.isArray(value) ? value.map(String) : [] }

function applyInterpreted(data: Record<string, any>, preserveManual = false) {
  const fields: StructuredField[] = ['target_date', 'weather', 'target_crowd', 'adult_count', 'child_count', 'child_ages', 'budget', 'interests', 'negative_interests', 'activity_level', 'requested_places', 'dietary_restrictions', 'allergy_information', 'arrival_time', 'preferred_experience_time', 'other_requirements']
  fields.forEach((field) => {
    if (preserveManual && manualFields.value.has(field)) return
    const value = data[field]
    if (value === undefined) return
    if (['interests', 'negative_interests', 'requested_places', 'dietary_restrictions'].includes(field)) (needs as any)[field] = toArray(value)
    else if (field === 'child_ages') needs.child_ages = Array.isArray(value) ? value.map((item) => Number(item)).filter((item) => Number.isFinite(item)) : []
    else (needs as any)[field] = value
  })
  needs.natural_language = reviewText.value
  interpreted.value = { ...data }
  syncChildAges(false)
}

function syncChildAges(mark = true) {
  const count = Math.max(0, Number(needs.child_count) || 0)
  const ages = [...needs.child_ages].slice(0, count)
  while (ages.length < count) ages.push(6)
  needs.child_ages = ages
  if (mark) manualFields.value.add('child_ages')
}

function mark(field: string) { manualFields.value.add(field) }
function editNeeds() { stage.value = 'input' }
function askFollowUp(question: string) { form.notes = question; stage.value = 'input' }

async function analyzeNeeds() {
  const text = combinedText.value || reviewText.value.trim()
  if (!text) { showToast('请先写下同行信息或想去哪里'); return }
  loading.value = true
  try {
    reviewText.value = text
    const response = await visitorApi.interpret({ natural_language: text })
    applyInterpreted(response.data.interpreted_needs, true)
    followUps.value = response.data.follow_up_questions || []
    stage.value = 'review'
  } catch (e) { showToast(errorMessage(e)) }
  finally { loading.value = false }
}

function profilePayload(): VisitorProfile {
  return { ...needs, natural_language: reviewText.value.trim(), child_ages: [...needs.child_ages], interests: [...needs.interests], negative_interests: [...needs.negative_interests], requested_places: [...needs.requested_places], dietary_restrictions: [...needs.dietary_restrictions] }
}

async function getRecommendations() {
  if (!reviewText.value.trim()) { showToast('请保留一段原始需求，方便酒店理解上下文'); return }
  const profile = profilePayload(); saveVisitorProfile(profile)
  loading.value = true
  try {
    const response = await visitorApi.recommend({ ...profile, structured_confirmed: true, conversation_id: visitorConversationId() })
    results.value = response.data.results; alternatives.value = []; interpreted.value = response.data.interpreted_needs || interpreted.value; stage.value = 'results'
    if (!results.value.length) {
      try { alternatives.value = (await visitorApi.products()).data.slice(0, 3) } catch { alternatives.value = [] }
      showToast('当前没有完全匹配的方案，已展示仍在售的可调整套餐')
    } else showToast(`已找到 ${results.value.length} 个个性化套餐`)
  } catch (e) { showToast(errorMessage(e)) }
  finally { loading.value = false }
}

function openProduct(id: number) { saveVisitorProfile(profilePayload()); window.location.href = `/visitor/products/${id}` }

watch(() => needs.child_count, () => syncChildAges())
</script>

<template>
  <div class="page-head recommendation-head"><div><div class="eyebrow">NATURAL LANGUAGE TRAVEL MATCHING</div><h1>把想法说出来，生成一份杭州旅居方案</h1><p>先用日常语言描述，再由你确认结构化需求。最终提交的成人数、儿童年龄、预算和时间以这张确认卡为准。</p></div><div class="recommendation-badge">AI 理解<br><strong>+ 你来确认</strong></div></div>
  <div class="stage-rail"><div :class="['stage-item', { active: stage === 'input', done: stage !== 'input' }]" @click="editNeeds"><span>01</span><div><strong>说出想法</strong><small>自然语言</small></div></div><div class="stage-line" /><div :class="['stage-item', { active: stage === 'review', done: stage === 'results', clickable: !!interpreted }]" @click="interpreted && (stage = 'review')"><span>02</span><div><strong>确认需求</strong><small>可编辑需求卡</small></div></div><div class="stage-line" /><div :class="['stage-item', { active: stage === 'results' }]" ><span>03</span><div><strong>查看推荐</strong><small>套餐与时间安排</small></div></div></div>

  <div v-if="stage === 'input'" class="split-layout recommendation-layout">
    <div class="panel input-panel"><div class="section-title" style="margin-top:0"><h2>告诉我这次怎么出发</h2><span>不需要标准答案</span></div><div class="natural-block"><div class="natural-icon">01</div><div><label>同行与时间</label><p>例如：两大两小，孩子6岁和9岁，周六下午三点到店</p><el-input v-model="form.people" type="textarea" :rows="4" maxlength="400" show-word-limit placeholder="几个人、儿童年龄、哪天、几点到……" /></div></div><div class="natural-block"><div class="natural-icon">02</div><div><label>想去哪里 / 想玩什么</label><p>例如：想去西湖和运河，雨天更想做室内非遗手作</p><el-input v-model="form.places" type="textarea" :rows="4" maxlength="400" show-word-limit placeholder="地点、兴趣、旅行节奏、喜欢的文化体验……" /></div></div><div class="natural-block"><div class="natural-icon">03</div><div><label>预算与其他注意事项</label><p>例如：预算1000元，花生过敏，不吃辣，不想赶行程</p><el-input v-model="form.notes" type="textarea" :rows="4" maxlength="400" show-word-limit placeholder="预算、饮食、过敏、行动偏好或其他需要酒店提前知道的事……" /></div></div><div class="example-row"><span>试试示例：</span><button @click="useExample('两大两小，孩子6岁和9岁，周六下午三点到店；想去西湖和运河，雨天做室内非遗手作；预算1000元，花生过敏，不赶行程')">亲子雨天</button><button @click="useExample('情侣两人，周末入住；想要茶文化、安静的杭州慢游；预算800元，不吃辣，希望下午有空闲时间')">情侣慢游</button><button @click="useExample('三位朋友，明天入住；想逛博物馆和老街，喜欢拍照；预算900元，尽量安排轻松路线')">朋友微度假</button></div><el-button class="primary-wide" type="primary" size="large" :loading="loading" @click="analyzeNeeds">✦ 智能整理我的需求</el-button></div>
    <div class="panel guidance-panel"><div class="section-title" style="margin-top:0"><h2>你可以随便说</h2><span>系统会提取关键信息</span></div><div class="guidance-card"><strong>同行</strong><p>“一家三口”“两大两小”“情侣两个人”</p></div><div class="guidance-card"><strong>兴趣</strong><p>“想去西湖”“想做点茶”“喜欢拍照和慢游”</p></div><div class="guidance-card"><strong>安全</strong><p>“孩子8岁”“花生过敏”“不吃辣”</p></div><div class="guidance-card"><strong>偏好</strong><p>“预算700”“下午到店”“不想赶行程”</p></div><div class="notice-box">系统只负责理解和校验；你可以在下一步直接改成人数、儿童年龄、预算和任何结构化字段。</div></div>
  </div>

  <div v-else-if="stage === 'review'" class="review-layout"><div class="panel review-editor"><div class="section-title" style="margin-top:0"><h2>确认需求</h2><span>手动修改优先</span></div><el-input v-model="reviewText" type="textarea" :rows="7" maxlength="1200" show-word-limit /><div class="review-actions"><el-button plain :loading="loading" @click="analyzeNeeds">重新解析这段话</el-button><span>你也可以只改右侧字段，不重新解析原话。</span></div><div class="follow-up-list" v-if="followUps.length"><strong>还可以补充</strong><button v-for="item in followUps" :key="item" @click="reviewText += `；${item}`">＋ {{ item }}</button></div><div class="form-actions"><el-button @click="editNeeds">返回修改原话</el-button><el-button type="primary" :loading="loading" @click="getRecommendations">使用确认值获取推荐</el-button></div></div><div class="panel requirement-card"><div class="section-title" style="margin-top:0"><div><h2>结构化确认卡</h2><small class="muted">识别结果可以直接编辑</small></div><span>最终提交版本</span></div><el-form label-position="top" class="structured-form"><div class="form-grid"><el-form-item label="入住日期"><el-date-picker v-model="needs.target_date" type="date" value-format="YYYY-MM-DD" style="width:100%" @change="mark('target_date')" /></el-form-item><el-form-item label="天气"><el-select v-model="needs.weather" style="width:100%" @change="mark('weather')"><el-option label="雨天" value="RAIN" /><el-option label="晴天" value="SUNNY" /><el-option label="多云" value="CLOUDY" /></el-select></el-form-item><el-form-item label="目标客群"><el-select v-model="needs.target_crowd" style="width:100%" @change="mark('target_crowd')"><el-option label="亲子家庭" value="FAMILY" /><el-option label="情侣" value="COUPLE" /><el-option label="朋友出行" value="FRIENDS" /><el-option label="一个人" value="SOLO" /><el-option label="本地周末" value="LOCAL_WEEKEND" /></el-select></el-form-item><el-form-item label="活动强度"><el-select v-model="needs.activity_level" style="width:100%" @change="mark('activity_level')"><el-option label="轻松" value="LOW" /><el-option label="适中" value="MEDIUM" /><el-option label="充实刺激" value="HIGH" /></el-select></el-form-item><el-form-item label="成人数量"><el-input-number v-model="needs.adult_count" :min="1" :max="20" style="width:100%" @change="mark('adult_count')" /></el-form-item><el-form-item label="儿童数量"><el-input-number v-model="needs.child_count" :min="0" :max="20" style="width:100%" @change="mark('child_count')" /></el-form-item><el-form-item v-if="needs.child_count" class="full" label="每位儿童年龄"><div class="age-row"><el-input-number v-for="(_, index) in needs.child_ages" :key="index" v-model="needs.child_ages[index]" :min="0" :max="18" :controls="false" @change="mark('child_ages')" /></div></el-form-item><el-form-item label="预算上限"><el-input v-model="needs.budget" @input="mark('budget')"><template #prepend>¥</template></el-input></el-form-item><el-form-item label="到店时间"><el-time-picker v-model="needs.arrival_time" value-format="HH:mm:ss" format="HH:mm" style="width:100%" @change="mark('arrival_time')" /></el-form-item><el-form-item label="偏好体验"><el-select v-model="needs.interests" multiple filterable allow-create collapse-tags style="width:100%" @change="mark('interests')"><el-option label="主题乐园" value="THEME_PARK" /><el-option label="儿童探索" value="KIDS" /><el-option label="运动娱乐" value="SPORT" /><el-option label="夜游" value="NIGHTLIFE" /><el-option label="旅拍" value="PHOTO" /><el-option label="美食" value="FOOD" /><el-option label="自然" value="NATURE" /><el-option label="文化手作" value="CULTURE" /><el-option label="茶文化" value="TEA" /></el-select></el-form-item><el-form-item label="明确不喜欢"><el-select v-model="needs.negative_interests" multiple filterable allow-create collapse-tags style="width:100%" @change="mark('negative_interests')"><el-option label="茶文化" value="TEA" /><el-option label="博物馆" value="CULTURE" /><el-option label="走很多路" value="CITY_WALK" /><el-option label="运动" value="SPORT" /></el-select></el-form-item><el-form-item label="活动时间偏好"><el-time-picker v-model="needs.preferred_experience_time" value-format="HH:mm:ss" format="HH:mm" style="width:100%" @change="mark('preferred_experience_time')" /></el-form-item><el-form-item label="想去地点"><el-select v-model="needs.requested_places" multiple filterable allow-create collapse-tags style="width:100%" @change="mark('requested_places')"><el-option label="西湖" value="西湖" /><el-option label="运河" value="运河" /><el-option label="拱宸桥" value="拱宸桥" /><el-option label="茶园" value="茶园" /><el-option label="博物馆" value="博物馆" /></el-select></el-form-item><el-form-item label="饮食禁忌"><el-select v-model="needs.dietary_restrictions" multiple filterable allow-create collapse-tags style="width:100%" @change="mark('dietary_restrictions')"><el-option label="不吃辣" value="不吃辣" /><el-option label="素食" value="素食" /><el-option label="不吃海鲜" value="不吃海鲜" /><el-option label="清真" value="清真" /></el-select></el-form-item><el-form-item class="full" label="过敏信息"><el-input v-model="needs.allergy_information" placeholder="没有可以留空，例如：花生过敏、乳制品过敏" @input="mark('allergy_information')" /></el-form-item><el-form-item class="full" label="其他要求"><el-input v-model="needs.other_requirements" type="textarea" :rows="3" placeholder="例如：希望少走路、需要儿童洗漱包" @input="mark('other_requirements')" /></el-form-item></div></el-form><div class="safety-callout">儿童年龄、过敏和饮食禁忌会进入推荐请求，并在预约提交时保存；最终仍需酒店与商户人工确认。</div></div></div>

  <div v-else class="results-layout"><div class="panel compact-summary"><div class="section-title" style="margin-top:0"><div><h2>本次推荐依据</h2><small class="muted">根据你刚刚填写的偏好</small></div><el-button link type="primary" @click="stage = 'review'">修改需求</el-button></div><div class="summary-chips"><span>{{ weatherLabel }}</span><span>{{ needs.adult_count }} 成人 + {{ needs.child_count }} 儿童</span><span>预算 ¥{{ needs.budget }}</span><span>{{ needs.requested_places?.join('、') || '杭州文化体验' }}</span><span v-if="needs.allergy_information" class="safety-chip">{{ needs.allergy_information }}</span></div></div><div v-if="!results.length && !loading" class="panel recommendation-empty"><div class="empty-mark">S</div><h3>暂时没有完全匹配的方案</h3><p>下面是仍然在售的体验，你可以打开详情，或返回修改日期、预算和兴趣。</p><div v-if="alternatives.length" class="alternative-grid"><ProductCard v-for="item in alternatives" :key="item.id" :product="item" public-view /></div><div v-else class="empty-state">当前还没有已发布的公开套餐，请先等待酒店发布产品。</div></div><div v-if="loading" class="panel empty-state">正在为你挑选合适的杭州玩法…</div><div v-for="item in results" :key="item.product.id" class="panel recommendation-panel"><div class="product-card__top"><span class="eyebrow">匹配分 {{ item.score }} / 100</span><span class="muted">可预约咨询 · ¥{{ item.product.suggested_price }}</span></div><ProductCard :product="item.product" public-view /><p class="recommendation-reason">{{ item.recommendation_reason }}</p><div class="product-card__resources"><span :class="item.budget_match ? '' : 'warning-text'">预算 {{ item.budget_match ? '匹配' : '超出' }}</span><span>儿童 {{ item.children_match ? '适配' : '需确认年龄' }}</span><span>天气 {{ item.weather_match ? '适配' : '不适配' }}</span><span>兴趣 {{ item.interest_match ? '命中' : '可替换' }}</span></div><div v-if="item.schedule.length" class="panel schedule-panel"><strong>这次怎么安排</strong><p v-for="event in item.schedule" :key="event.time + event.title" class="muted" style="line-height:1.5;margin:8px 0"><b>{{ event.time }}</b> · {{ event.title }}：{{ event.description }}</p></div><div v-if="item.limited_adjustments.length" class="adjustment-hints"><strong>可做的有限调整</strong><span v-for="hint in item.limited_adjustments" :key="hint">{{ hint }}</span></div><div v-if="item.allergy_warning" class="danger-text allergy-note">{{ item.allergy_warning }}</div><div style="text-align:right;margin-top:12px"><el-button type="primary" plain @click="openProduct(item.product.id)">查看套餐并预约</el-button></div></div><div class="panel follow-up-panel"><div><strong>还想换一种玩法？</strong><p class="muted">可以继续告诉我预算、地点、天气或“还有什么推荐的”。</p></div><div class="follow-up-actions"><el-button v-for="item in ['还有什么适合雨天的？', '换成更轻松、不赶路的安排', '再推荐一个茶文化体验']" :key="item" plain @click="askFollowUp(item)">{{ item }}</el-button></div></div></div>
</template>

<style scoped>
.recommendation-head{align-items:center}.recommendation-badge{padding:12px 16px;border:1px solid #cfe6dc;border-radius:16px;background:linear-gradient(135deg,#eff9f4,#fff9ec);color:var(--teal);font-size:12px;line-height:1.6;text-align:center}.recommendation-badge strong{font-size:15px}.stage-rail{display:flex;align-items:center;gap:12px;margin:-4px 0 20px}.stage-item{display:flex;align-items:center;gap:9px;color:#9aaba5;cursor:pointer}.stage-item span{width:30px;height:30px;display:grid;place-items:center;border-radius:50%;border:1px solid #d9e8e1;font-size:11px}.stage-item strong,.stage-item small{display:block}.stage-item strong{font-size:13px;color:inherit}.stage-item small{font-size:11px;margin-top:2px}.stage-item.active,.stage-item.done{color:var(--teal)}.stage-item.active span,.stage-item.done span{background:var(--teal);border-color:var(--teal);color:#fff}.stage-line{height:1px;flex:1;background:var(--line)}.recommendation-layout{grid-template-columns:minmax(0,1fr) 280px}.input-panel{padding:24px}.natural-block{display:grid;grid-template-columns:38px 1fr;gap:14px;padding:17px 0;border-top:1px solid var(--line)}.natural-icon{width:32px;height:32px;border-radius:11px;display:grid;place-items:center;background:#e5f4ed;color:var(--teal);font-weight:700;font-size:11px}.natural-block label{font-size:15px;font-weight:700}.natural-block p{margin:5px 0 10px;color:var(--muted);font-size:12px}.example-row{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:18px 0}.example-row>span{font-size:12px;color:var(--muted)}.example-row button,.follow-up-list button{border:1px solid #cfe6dc;background:#f2faf6;color:var(--teal);border-radius:999px;padding:7px 11px;font-size:12px}.primary-wide{width:100%;margin-top:3px}.guidance-panel{height:max-content;background:linear-gradient(150deg,#fff,#f2faf6)}.guidance-card{padding:13px 0;border-top:1px solid var(--line)}.guidance-card strong{font-size:13px}.guidance-card p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.6}.notice-box,.safety-callout{margin-top:16px;padding:12px 13px;border-radius:12px;background:#fff8eb;color:#8b6a36;font-size:12px;line-height:1.7}.review-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(520px,1.2fr);gap:18px;align-items:start}.review-editor,.requirement-card{padding:24px}.review-actions{display:flex;align-items:center;gap:10px;margin-top:12px;color:var(--muted);font-size:12px}.follow-up-list{display:grid;gap:8px;margin-top:18px}.follow-up-list strong{font-size:12px}.follow-up-list button{text-align:left;border-radius:10px}.structured-form :deep(.el-form-item){margin-bottom:16px}.age-row{display:flex;flex-wrap:wrap;gap:8px}.age-row :deep(.el-input-number){width:92px}.results-layout{max-width:960px;margin:0 auto}.compact-summary{margin-bottom:16px;padding:17px 20px}.summary-chips{display:flex;gap:8px;flex-wrap:wrap}.summary-chips span{padding:7px 10px;border:1px solid #dbece4;background:#f8fcfa;border-radius:999px;color:var(--teal-dark);font-size:12px}.summary-chips .safety-chip{border-color:#f0d2ac;background:#fff8eb;color:#9a6a2b}.recommendation-empty{margin-bottom:14px;text-align:center}.recommendation-empty h3{font:26px Georgia,serif;margin:8px 0}.recommendation-empty>p{color:var(--muted);font-size:13px}.alternative-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;text-align:left;margin-top:22px}.recommendation-panel{margin-bottom:14px}.recommendation-reason{font-size:14px;line-height:1.8;margin:4px 0}.schedule-panel{box-shadow:none;background:#f8fbf9;margin-top:12px}.adjustment-hints{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-top:12px}.adjustment-hints strong{font-size:12px}.adjustment-hints span{background:#fff;border:1px solid #dcece5;border-radius:999px;padding:6px 9px;font-size:11px;color:var(--teal-dark)}.allergy-note{font-size:12px;line-height:1.7;margin-top:12px}.follow-up-panel{display:flex;align-items:center;justify-content:space-between;gap:18px;background:linear-gradient(135deg,#f1faf5,#fffaf0)}.follow-up-panel p{margin:6px 0 0}.follow-up-actions{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:7px}@media(max-width:1100px){.review-layout{grid-template-columns:1fr}}@media(max-width:800px){.stage-rail{gap:6px}.stage-item div{display:none}.recommendation-layout,.review-layout{grid-template-columns:1fr}.alternative-grid{grid-template-columns:1fr}.follow-up-panel{display:block}.follow-up-actions{justify-content:flex-start;margin-top:12px}.recommendation-badge{display:none}.review-actions{display:block}.review-actions .el-button{margin-bottom:8px}}
</style>
