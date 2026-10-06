<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { visitorApi } from '../api'
import { errorMessage } from '../api/client'
import ProductCard from './ProductCard.vue'
import type { TravelProduct } from '../types'
import { visitorConversationId } from '../utils/visitorProfile'

const props = defineProps<{ productId?: number | null; weather?: string; pageLayout?: boolean }>()

type RoomOption = {
  room_inventory_id: number
  room_type: string
  max_guests: number
  price: string
  remaining: number
  is_current: boolean
  image_url?: string
}
type DateOption = {
  id: number
  target_date: string
  weekday: string
  price: string
  room_type: string
  sale_quantity: number
}
type Chat = {
  mode?: 'product_context' | 'discovery' | 'room_options' | 'date_options'
  user?: string
  answer?: string
  safety_notes?: string
  reasons?: Record<string, string>
  reason_tags?: Record<string, string[]>
  reason_notes?: Record<string, string>
  schedule_notes?: Record<string, Array<{ time?: string; content?: string }>>
  limited_adjustments?: Record<string, string[]>
  product?: TravelProduct | null
  suggestions?: TravelProduct[]
  follow_up_questions?: string[]
  product_id?: number | null
  room_options?: RoomOption[]
  date_options?: DateOption[]
}

// Keep practical reasons, schedule details, and source status attached to each answer.
function nameFor(chat: Chat, id: string) {
  const found = (chat.suggestions || []).find((item) => String(item.id) === String(id))
  if (found?.product_name) return found.product_name
  if (chat.product && String(chat.product.id) === String(id)) return chat.product.product_name
  return '推荐方案'
}

// 兜底：模型偶尔会复述内部枚举（FAMILY / RAIN…），展示前统一换成中文。
const ENUM_LABELS: Record<string, string> = {
  FAMILY: '亲子家庭', COUPLE: '两人同行', FRIENDS: '朋友同行', SOLO: '独自出行',
  LOCAL_WEEKEND: '本地周末客', ALL: '不限客群', RAIN: '有雨', SUNNY: '晴天', CLOUDY: '多云', SNOW: '有雪',
}

function humanizeEnums(value: unknown) {
  return String(value ?? '').replace(/(^|[^A-Za-z0-9_])([A-Z][A-Z_]{2,})(?![A-Za-z0-9_])/g, (match, prefix: string, token: string) => `${prefix}${ENUM_LABELS[token] || token}`)
}

function reasonRows(chat: Chat) {
  return Object.entries(chat.reasons || {}).map(([id, text]) => ({ name: nameFor(chat, id), text: humanizeEnums(text) }))
}

function scheduleRows(chat: Chat) {
  return Object.entries(chat.schedule_notes || {})
    .map(([id, items]) => ({
      key: id,
      name: nameFor(chat, id),
      items: (Array.isArray(items) ? items : []).map((item) => ({ ...item, content: humanizeEnums(item?.content) })),
    }))
    .filter((row) => row.items.length)
}

function limitRows(chat: Chat) {
  return Object.entries(chat.limited_adjustments || {})
    .map(([id, items]) => ({ name: nameFor(chat, id), text: humanizeEnums(Array.isArray(items) ? items.join('；') : items) }))
    .filter((row) => row.text)
}
function alternativeRooms(chat: Chat) {
  return (chat.room_options || []).filter((room) => !room.is_current && room.remaining > 0)
}
function reasonFor(chat: Chat, id: number | string) {
  return humanizeEnums(chat.reasons?.[String(id)] || '')
}
function reasonNote(chat: Chat, id: number | string) {
  return humanizeEnums(chat.reason_notes?.[String(id)] || '')
}
function reasonTags(chat: Chat, id: number | string) {
  const values = chat.reason_tags?.[String(id)]
  return Array.isArray(values) ? values.map(humanizeEnums).filter(Boolean).slice(0, 4) : []
}
function scheduleFor(chat: Chat, id: number | string) {
  return scheduleRows(chat).find((row) => row.key === String(id))?.items || []
}
function limitFor(chat: Chat, id: number | string) {
  const value = chat.limited_adjustments?.[String(id)]
  return humanizeEnums(Array.isArray(value) ? value.join('；') : value || '')
}

const question = ref('')
const chats = ref<Chat[]>([])
const asking = ref(false)
// 等待期间给出行进感：模型一次返回需要十几秒，分阶段提示比一句「正在查询」更好等。
const PENDING_STEPS = ['正在检索当前在售的商品…', '正在核对房态、名额与场次…', '正在按同行人数与天气排序…', '正在整理行程与注意事项…']
const pendingStep = ref(0)
let pendingTimer: number | undefined
const pendingLabel = computed(() => PENDING_STEPS[Math.min(pendingStep.value, PENDING_STEPS.length - 1)])
const greeting = ref('告诉我日期、同行人、预算或想体验的内容，我会结合天气和当前可售套餐帮你推荐。')
const starters = ref<string[]>([])
const contextProduct = ref<TravelProduct | null>(null)
const conversationScope = ref<'product_context' | 'discovery'>(props.productId ? 'product_context' : 'discovery')
const scroller = ref<HTMLElement | null>(null)
const showScrollEnd = ref(false)
let introSequence = 0
let askSequence = 0

const canAsk = computed(() => Boolean(question.value.trim()) && !asking.value)

// 按句号切段显示，避免一整段大白话，让「推荐理由」读起来更清楚。
function answerParagraphs(chat: Chat): string[] {
  const source = humanizeEnums(chat.answer).replace(/\r/g, '').replace(/\*\*(.*?)\*\*/g, '$1')
  const blocks = source.split(/\n\s*\n+/)
  const result: string[] = []
  for (const block of blocks) {
    const lines = block.split(/\n+/).map((raw) => raw.trim()
      .replace(/^[-*•·∙⋅▪◦]+\s*/, '')
      .replace(/^[,，、；;:：]+\s*/, '')
      .trim())
      .filter((line) => line && !/^[\s•·∙⋅▪◦;；:,，、.!?。…—–()（）\[\]{}]+$/.test(line))
    if (lines.length) result.push(lines.join(' '))
  }
  return result
}

function growInput(event: Event) {
  const el = event.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

async function loadIntro(productId = props.productId) {
  const requestId = ++introSequence
  contextProduct.value = null
  if (productId) {
    void visitorApi.product(productId).then((response) => {
      if (requestId === introSequence) contextProduct.value = response.data
    }).catch(() => undefined)
  }
  try {
    const response = await visitorApi.assistantIntro(productId ?? null)
    if (requestId !== introSequence) return
    greeting.value = response.data.greeting
    starters.value = response.data.suggestions || []
  } catch {
    if (requestId !== introSequence) return
    starters.value = productId
      ? ['这套产品包含哪些权益？', '这套产品的行程怎么安排？', '体验适合哪些人？', '需要提前预约吗？', '下雨天怎么调整？', '还有其他可售日期吗？']
      : ['预算 700 左右，一家三口有什么推荐？', '今天有雨，适合安排什么室内行程？', '周末两天，怎么安排杭州亲子行程？', '晚上有什么轻松的在售套餐？', '西湖附近有哪些慢游体验？', '第一次来杭州选哪个套餐？']
  }
}

async function ask(text?: string) {
  const value = String(text ?? question.value).trim()
  if (!value || asking.value) return
  const requestId = ++askSequence
  const pageProductId = props.productId
  const contextProductId = conversationScope.value === 'product_context' ? props.productId : null
  question.value = ''
  const priorTurns = chats.value
    .map((chat) => chat.user?.trim())
    .filter((turn): turn is string => Boolean(turn))
    .slice(-20)
  chats.value.push({ user: value })
  const questionIndex = chats.value.length - 1
  activeQuestionIndex = questionIndex
  asking.value = true
  pendingStep.value = 0
  pendingTimer = window.setInterval(() => { pendingStep.value += 1 }, 2600)
  await scrollQuestionIntoView(questionIndex)
  try {
    const naturalLanguage = [...priorTurns, value].join('；').slice(-5000)
    const response = await visitorApi.consult({
      product_id: contextProductId ?? undefined,
      question: value,
      natural_language: naturalLanguage,
      weather: props.weather || 'UNKNOWN',
      conversation_id: visitorConversationId(),
    })
    if (requestId !== askSequence || pageProductId !== props.productId) return
    conversationScope.value = response.data.mode === 'discovery' ? 'discovery' : contextProductId ? 'product_context' : 'discovery'
    chats.value.push({
      answer: String(response.data.answer || ''),
      mode: (response.data.mode as Chat['mode']) || (contextProductId ? 'product_context' : 'discovery'),
      safety_notes: String(response.data.safety_notes || ''),
      product: (response.data.product as TravelProduct | null) || null,
      reasons: (response.data.reasons as Record<string, string>) || {},
      reason_tags: (response.data.reason_tags as Record<string, string[]>) || {},
      reason_notes: (response.data.reason_notes as Record<string, string>) || {},
      schedule_notes: (response.data.schedule_notes as Chat['schedule_notes']) || {},
      limited_adjustments: (response.data.limited_adjustments as Chat['limited_adjustments']) || {},
      suggestions: (response.data.suggestions as TravelProduct[]) || [],
      follow_up_questions: (response.data.follow_up_questions as string[]) || [],
      product_id: (response.data.product_id as number) ?? contextProductId ?? null,
      room_options: (response.data.room_options as RoomOption[]) || [],
      date_options: (response.data.date_options as DateOption[]) || [],
    })
  } catch (e) {
    if (requestId === askSequence && pageProductId === props.productId) chats.value.push({ answer: errorMessage(e) })
  } finally {
    if (requestId === askSequence) {
      asking.value = false
      if (pendingTimer) { window.clearInterval(pendingTimer); pendingTimer = undefined }
      await nextTick()
      restoreQuestionPosition()
      updateScrollEnd()
    }
  }
}

let activeQuestionIndex: number | null = null

async function scrollQuestionIntoView(index: number) {
  await nextTick()
  const el = scroller.value
  const questionEl = el?.querySelector<HTMLElement>(`[data-question-index="${index}"]`)
  if (!el || !questionEl) return
  const containerTop = el.getBoundingClientRect().top
  const questionTop = questionEl.getBoundingClientRect().top
  el.scrollTop += questionTop - containerTop - 16
  showScrollEnd.value = false
}

function restoreQuestionPosition() {
  const el = scroller.value
  if (!el || activeQuestionIndex === null) return
  const questionEl = el.querySelector<HTMLElement>(`[data-question-index="${activeQuestionIndex}"]`)
  if (!questionEl) return
  const containerTop = el.getBoundingClientRect().top
  const questionTop = questionEl.getBoundingClientRect().top
  el.scrollTop += questionTop - containerTop - 16
}

function updateScrollEnd() {
  const el = scroller.value
  if (!el) { showScrollEnd.value = false; return }
  showScrollEnd.value = el.scrollHeight - el.scrollTop - el.clientHeight > 24
}

async function scrollToEnd() {
  await nextTick()
  const el = scroller.value
  if (el) {
    el.scrollTop = el.scrollHeight
    showScrollEnd.value = false
  }
}
watch(() => props.productId, (productId, previous) => {
  if (previous !== undefined && productId !== previous) {
    conversationScope.value = productId ? 'product_context' : 'discovery'
    askSequence += 1
    asking.value = false
    chats.value = []
    activeQuestionIndex = null
    question.value = ''
    if (pendingTimer) { window.clearInterval(pendingTimer); pendingTimer = undefined }
  }
  void loadIntro(productId)
}, { immediate: true })
</script>

<template>
  <section class="assistant" :class="{ 'assistant--page': pageLayout }">
    <header v-if="pageLayout && productId" class="assistant-context">
      <div><span>{{ conversationScope === 'product_context' ? '正在咨询' : '正在浏览全部在售套餐' }}</span><strong>{{ conversationScope === 'product_context' ? (contextProduct?.product_name || '当前旅居产品') : '可按预算、人数和偏好继续筛选' }}</strong></div>
      <router-link v-if="contextProduct" :to="`/visitor/products/${contextProduct.id}`">{{ conversationScope === 'product_context' ? '查看产品' : '返回当前产品' }}</router-link>
    </header>
    <div ref="scroller" class="assistant-scroll" @scroll.passive="updateScrollEnd">
      <div v-if="!chats.length" class="assistant-intro">
        <div class="assistant-intro__heading">
          <h2>{{ greeting || '把想法，变成一趟合适的旅程' }}</h2>
        </div>
        <div class="assistant-starters">
          <button v-for="(item, index) in starters" :key="item" type="button" @click="ask(item)">
            <span>{{ item }}</span><b aria-hidden="true">↗</b>
          </button>
        </div>
      </div>

      <div v-if="chats.length" class="assistant-chat">
        <template v-for="(chat, index) in chats" :key="index">
          <div v-if="chat.user" class="assistant-bubble is-user" :data-question-index="index"><span>{{ chat.user }}</span></div>
          <div v-else class="assistant-answer">
            <p v-for="(paragraph, i) in answerParagraphs(chat)" :key="i" class="assistant-paragraph">{{ paragraph }}</p>
            <div v-if="chat.mode === 'room_options' && alternativeRooms(chat).length" class="assistant-rooms">
              <div class="assistant-rooms__list">
                <router-link
                  v-for="room in alternativeRooms(chat)"
                  :key="room.room_inventory_id"
                  class="assistant-room"
                  :class="{ 'is-current': room.is_current, 'is-soldout': room.remaining <= 0 }"
                  :to="{ path: `/visitor/products/${chat.product_id}`, query: { room: String(room.room_inventory_id) } }"
                >
                  <img v-if="room.image_url" :src="room.image_url" :alt="room.room_type" loading="lazy" />
                  <div class="assistant-room__copy">
                    <b>{{ room.room_type }}<em v-if="room.is_current">当前</em></b>
                    <small>可住 {{ room.max_guests }} 人 · {{ room.remaining > 0 ? `余 ${room.remaining} 套` : '已售罄' }}</small>
                  </div>
                  <span>¥{{ room.price }}<small>/ 套</small></span>
                </router-link>
              </div>
            </div>
            <div v-if="chat.mode === 'date_options' && chat.date_options?.length && !chat.suggestions?.length" class="assistant-date-options">
              <router-link v-for="option in chat.date_options" :key="option.id" :to="`/visitor/products/${option.id}`" class="assistant-date-option">
                <span><b>{{ Number(option.target_date.slice(5, 7)) }}月{{ Number(option.target_date.slice(8, 10)) }}日</b><small>{{ option.weekday }} · {{ option.room_type }} · 余 {{ option.sale_quantity }} 套</small></span>
                <strong>¥{{ option.price }}<small>/ 套</small></strong>
                <em>查看这天</em>
              </router-link>
            </div>
            <div v-if="chat.suggestions?.length" class="assistant-cards">
              <ProductCard
                v-for="item in chat.suggestions"
                :key="item.id"
                :product="item"
                public-view
                compact
                :recommendation="reasonFor(chat, item.id)"
                :recommendation-note="reasonNote(chat, item.id)"
                :recommendation-tags="reasonTags(chat, item.id)"
              />
            </div>
            <div v-if="!chat.suggestions?.length && !chat.product && (reasonRows(chat).length || scheduleRows(chat).length || limitRows(chat).length)" class="assistant-product-advice assistant-product-advice--general">
              <p v-for="row in reasonRows(chat)" :key="`reason-${row.name}`"><b>{{ row.name }}</b><span>{{ row.text }}</span></p>
              <p v-for="row in scheduleRows(chat)" :key="`schedule-${row.key}`"><b>{{ row.name }} · 行程</b><span>{{ row.items.map((entry) => `${entry.time ? `${entry.time} ` : ''}${entry.content}`).join('；') }}</span></p>
              <p v-for="row in limitRows(chat)" :key="`limit-${row.name}`"><b>{{ row.name }} · 提醒</b><span>{{ row.text }}</span></p>
            </div>
            <p v-if="chat.safety_notes" class="assistant-safety-line">出行提醒：{{ humanizeEnums(chat.safety_notes) }}</p>
            <div v-if="chat.follow_up_questions?.length" class="assistant-followups">
              <button v-for="item in chat.follow_up_questions" :key="item" type="button" @click="ask(item)">{{ item }}</button>
            </div>
          </div>
        </template>
        <div v-if="asking" class="assistant-answer assistant-answer--pending">{{ pendingLabel }}</div>
      </div>
    </div>

    <button v-if="showScrollEnd" type="button" class="assistant-scroll-end" aria-label="滚动到最新回复" title="滚动到最新回复" @click="scrollToEnd">↓</button>
    <form class="assistant-input" :class="{ 'assistant-input--empty': !chats.length }" @submit.prevent="ask()">
      <textarea v-model="question" rows="1" placeholder="例如：下雨天带孩子去哪一组？" @input="growInput" @keydown.enter.exact.prevent="ask()" />
      <button type="submit" :disabled="!canAsk">发送</button>
    </form>
  </section>
</template>

<style scoped>
.assistant { display: flex; flex-direction: column; width: 100%; max-width: 100%; min-width: 0; height: 100%; min-height: 0; box-sizing: border-box; }
.assistant-scroll { flex: 1 1 auto; width: 100%; max-width: 100%; min-width: 0; min-height: 0; box-sizing: border-box; overflow-y: auto; padding: 4px 2px 12px; scrollbar-width: none; }
.assistant-scroll::-webkit-scrollbar { width: 0; height: 0; display: none; }
.assistant-intro { display: grid; gap: 20px; width: min(100%, 760px); margin: clamp(24px, 8vh, 86px) auto 36px; padding: clamp(22px, 4vw, 42px); border: 1px solid #e9e3d7; border-radius: 22px; background: radial-gradient(ellipse at 100% 0, rgba(224, 236, 222, .72), transparent 42%), linear-gradient(145deg, #fffefa 0%, #f8f5ed 100%); box-shadow: 0 22px 65px rgba(35, 58, 48, .08); }
.assistant-intro__heading { display: flex; align-items: center; gap: 15px; }
.assistant-intro__mark { display: grid; place-items: center; width: 48px; height: 48px; flex: 0 0 auto; border-radius: 16px; background: #173f37; color: #ecd39e; font: 500 27px/1 Georgia, serif; box-shadow: 0 8px 18px rgba(23, 63, 55, .16); }

.assistant-intro__heading h2 { margin: 0; color: #203b32; font: 500 clamp(24px, 3vw, 32px)/1.35 Georgia, 'Songti SC', serif; letter-spacing: -.4px; }

.assistant-starters { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px; }

.assistant-starters button { display: grid; grid-template-columns: minmax(0,1fr) 14px; align-items: center; gap: 9px; min-height: 52px; padding: 9px 11px; border: 1px solid #e9e4da; border-radius: 11px; background: rgba(255,255,255,.8); color: #41584b; text-align: left; font-size: 11.5px; line-height: 1.5; cursor: pointer; transition: border-color .18s, background .18s, transform .18s; }
.assistant-starters button:hover { transform: translateY(-1px); border-color: #a9c5b2; background: #fff; }

.assistant-starters button b { color: #a9b5ab; font-size: 13px; font-weight: 500; }

@media (max-width: 600px) {
  .assistant-intro { gap: 15px; margin: 20px auto 26px; padding: 21px 17px; border-radius: 17px; }
  .assistant-intro__mark { width: 42px; height: 42px; border-radius: 14px; font-size: 24px; }
  .assistant-starters { grid-template-columns: 1fr; }
  .assistant-starters button { min-height: 46px; }
}
.assistant-chat { display: grid; gap: 14px; width: min(100%, 920px); min-width: 0; margin-inline: auto; box-sizing: border-box; }
.assistant-bubble { max-width: 82%; padding: 10px 13px; border-radius: 14px 14px 4px 14px; background: #eaf4ef; color: #23483d; font-size: 13px; line-height: 1.7; justify-self: end; }
.assistant-answer { width: 100%; min-width: 0; max-width: 100%; box-sizing: border-box; color: #33403b; font-size: 14px; line-height: 1.8; }
.assistant-answer--pending { width: 100%; min-width: 0; box-sizing: border-box; color: var(--muted); font-size: 13px; }
.assistant-paragraph { margin: 0 0 8px; }
.assistant-paragraph:last-child { margin-bottom: 0; }
.assistant-cards { display: grid; gap: 10px; margin-top: 12px; }
.assistant-rooms { margin-top: 12px; }
.assistant-date-options { display: grid; gap: 8px; margin-top: 12px; }
.assistant-date-option { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 14px; padding: 12px 14px; border: 1px solid #e7ded6; border-radius: 12px; background: #fff; color: #33302e; text-decoration: none; }
.assistant-date-option > span { display: grid; gap: 4px; min-width: 0; }
.assistant-date-option b { color: #344b3f; font-size: 14px; }
.assistant-date-option small { color: #758178; font-size: 12px; }
.assistant-date-option > strong { color: #d56835; font-size: 16px; white-space: nowrap; }
.assistant-date-option > strong small { margin-left: 3px; font-size: 11px; font-weight: 400; }
.assistant-date-option em { color: #64806f; font-size: 12px; font-style: normal; white-space: nowrap; }
.assistant-date-option:hover { border-color: #c99471; }
.assistant-rooms__list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.assistant-room { display: grid; grid-template-columns: 112px minmax(0, 1fr) auto; align-items: center; gap: 12px; width: 100%; min-width: 0; padding: 8px; border: 1px solid #e7ded6; border-radius: 12px; background: #fff; color: #33302e; text-decoration: none; transition: border-color .18s, box-shadow .18s; box-sizing: border-box; }
.assistant-room > img { display: block; width: 112px; height: 76px; object-fit: cover; border-radius: 8px; background: #eef1ed; }
.assistant-room__copy { display: grid; gap: 5px; min-width: 0; }
.assistant-room:hover { border-color: #ff6a00; box-shadow: 0 6px 16px rgba(213, 104, 53, .12); }
.assistant-room b { display: flex; align-items: center; gap: 6px; min-width: 0; font-size: 14px; font-weight: 650; }
.assistant-room b em { padding: 1px 6px; border-radius: 999px; background: #fff1e4; color: #d56835; font-size: 11.5px; font-style: normal; font-weight: 600; }
.assistant-room > span { color: #d56835; font-size: 16px; font-weight: 700; white-space: nowrap; }
.assistant-room > span small { color: #9a8f87; font-size: 11.5px; font-weight: 400; }
.assistant-room__copy small { color: #758178; font-size: 12px; }
.assistant-room.is-current { border-color: #ff6a00; background: #fff8f2; }
.assistant-room.is-soldout { opacity: .5; }
.assistant-card { display: grid; gap: 6px; }
.assistant-card__link { display: inline-block; color: #d56835; font-size: 12px; font-weight: 650; text-decoration: none; }
.assistant-card__link:hover { text-decoration: underline; }
/* 结构化回答：为什么推荐 / 时间怎么排 / 注意事项 */
.assistant-block { display: grid; gap: 7px; margin-top: 12px; padding: 11px 13px; border: 1px solid #ece2da; border-radius: 12px; background: #fdfbf9; }
.assistant-block > b { color: #b4531f; font-size: 12.5px; font-weight: 700; }
.assistant-block ul { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.assistant-block li { display: grid; gap: 3px; color: #4a423c; font-size: 12.5px; line-height: 1.7; }
.assistant-block li strong { color: #26211d; font-size: 12.5px; font-weight: 650; }
.assistant-block--note { border-color: #f0e2cf; background: #fffaf2; }
.assistant-followups { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.assistant-followups button { padding: 6px 10px; border: 1px solid #e6ded7; border-radius: 999px; background: #fff; color: #7a6f68; font-size: 11px; cursor: pointer; }

/* 输入框固定在页面最下方（ChatGPT / Codex 那种布局），本身不铺白底。 */
.assistant-input { flex: 0 0 auto; display: flex; gap: 8px; align-items: flex-end; padding: 10px 0 2px; background: transparent; }
.assistant-input textarea { flex: 1; min-width: 0; min-height: 44px; max-height: 160px; padding: 12px 14px; border: 1px solid #e2dbd4; border-radius: 14px; background: transparent; color: #33302e; font-size: 13px; line-height: 1.6; resize: none; outline: none; overflow-y: auto; scrollbar-width: none; }
.assistant-input textarea::-webkit-scrollbar { width: 0; height: 0; display: none; }
.assistant-input textarea:focus { border-color: #d56835; box-shadow: 0 0 0 3px rgba(213, 104, 53, .12); }
.assistant-input button { flex: 0 0 auto; height: 44px; padding: 0 22px; border: 0; border-radius: 14px; background: #ff6a00; color: #fff; font-size: 14px; font-weight: 650; cursor: pointer; }
.assistant-input button:disabled { opacity: .5; cursor: not-allowed; }

.assistant-cards :deep(.product-card--compact) { grid-template-columns: 132px minmax(0, 1fr); min-height: 116px; border: 1px solid #eee3da; border-radius: 12px; }
.assistant-cards :deep(.product-card--compact > .product-card__media) { height: 100%; min-height: 104px; }
.assistant-cards :deep(.product-card--compact > .product-card__media > .media-image) { height: 100%; min-height: 104px; aspect-ratio: auto; }
.assistant-cards :deep(.product-card--compact .product-card__body) { display: grid; align-content: center; gap: 4px; padding: 9px 11px; }
.assistant-cards :deep(.product-card--compact h3) { margin: 0; font-size: 13px; line-height: 1.35; white-space: normal; }
.assistant-cards :deep(.product-card--compact .product-card__bottom) { padding-top: 6px; }
.assistant-cards :deep(.product-card--compact .product-card__bottom strong) { font-size: 15px; }

@media (max-width: 700px) {
  .assistant-answer { font-size: 13px; }
  .assistant-input button { height: 40px; padding: 0 16px; font-size: 13px; border-radius: 12px; }
  .assistant-input textarea { min-height: 40px; font-size: 12px; }
  .assistant-cards :deep(.product-card--compact) { grid-template-columns: 116px minmax(0, 1fr); min-height: 104px; }
  .assistant-cards :deep(.product-card--compact > .product-card__media),
  .assistant-cards :deep(.product-card--compact > .product-card__media > .media-image) { min-height: 92px; }
}
.assistant-product-recommendation { display:grid; gap:8px; min-width:0; }
.assistant-product-advice { display:grid; gap:6px; padding:3px 2px 6px 10px; border-left:2px solid #dbe8df; color:#4b5d53; font-size:12px; line-height:1.65; }
.assistant-product-advice p,.assistant-product-advice div { display:grid; grid-template-columns:82px minmax(0,1fr); gap:8px; margin:0; }
.assistant-product-advice div > span { grid-column:2; }
.assistant-product-advice b { color:#315746; font-weight:650; }
.assistant-cards :deep(.product-card--compact) { width:100%; min-width:0; box-sizing:border-box; }
.assistant-block { border:0; border-left:2px solid #e5e9e5; border-radius:0; background:transparent; padding:4px 0 4px 10px; }
.assistant-product-recommendation { gap:5px; padding:10px 0 12px; border-bottom:1px solid #edf0ed; }
.assistant-product-reason { margin:0; color:#56665d; font-size:13px; line-height:1.6; }
.assistant-product-advice { display:grid; gap:5px; padding:3px 0 2px 10px; border-left:2px solid #dfe8e1; color:#53645a; font-size:13px; line-height:1.65; }
.assistant-product-advice p { display:grid; grid-template-columns:78px minmax(0,1fr); gap:7px; margin:0; }
.assistant-product-advice b { color:#315746; font-weight:650; }
.assistant-product-advice--general { margin-top:12px; }
.assistant-safety-line { margin:10px 0 0; color:#7d6748; font-size:12.5px; line-height:1.65; }
@media(max-width:600px){.assistant-product-advice p{grid-template-columns:1fr;gap:1px}}
.assistant-cards :deep(.product-card--compact) { display:grid; grid-template-columns:190px minmax(0,1fr); min-height:146px; overflow:hidden; padding:0; border:1px solid #e8e6df; border-radius:12px; background:#fff; box-shadow:0 3px 12px rgba(34,53,44,.04); }
.assistant-cards :deep(.product-card--compact:hover) { transform:translateY(-1px); border-color:#d8ded8; box-shadow:0 7px 18px rgba(34,53,44,.08); }
.assistant-cards :deep(.product-card--compact > .product-card__media) { display:block; height:100%; min-height:146px; overflow:hidden; }
.assistant-cards :deep(.product-card--compact > .product-card__media > .media-image) { width:100%; height:100%; min-height:146px; aspect-ratio:auto; border-radius:0; }
.assistant-cards :deep(.product-card--compact .product-card__body) { display:grid; align-content:center; gap:7px; min-width:0; padding:13px 16px; }
.assistant-cards :deep(.product-card--compact h3) { color:#263b32; font-size:16px; line-height:1.4; }
.assistant-cards :deep(.product-card--compact .product-card__inclusions) { display:flex; flex-wrap:wrap; gap:5px; }
.assistant-cards :deep(.product-card--compact .product-card__inclusions span) { padding:3px 7px; border-radius:999px; background:#f1f5f1; color:#627167; font-size:11px; }
.assistant-cards :deep(.product-card--compact .product-card__bottom) { padding-top:7px; border-top:1px solid #eef0ed; }
.assistant-cards :deep(.product-card--compact .product-card__bottom strong) { font-size:16px; }
@media(max-width:700px){
  .assistant-cards :deep(.product-card--compact){grid-template-columns:118px minmax(0,1fr);min-height:132px}
  .assistant-cards :deep(.product-card--compact > .product-card__media),
  .assistant-cards :deep(.product-card--compact > .product-card__media > .media-image){min-height:132px}
  .assistant-cards :deep(.product-card--compact .product-card__body){padding:10px 11px;gap:5px}
  .assistant-cards :deep(.product-card--compact h3){font-size:14px}
}
@media(max-width:600px){
  .assistant-date-option { grid-template-columns: minmax(0,1fr) auto; gap: 8px; padding: 10px; }
  .assistant-date-option em { grid-column: 1 / -1; justify-self: end; }
  .assistant-room { grid-template-columns: 86px minmax(0, 1fr) auto; gap: 9px; padding: 7px; }
  .assistant-room > img { width: 86px; height: 66px; }
  .assistant-room > span { font-size: 14px; }
  .assistant-room b { font-size: 13px; }
}

.assistant-intro{width:min(100%,920px);box-sizing:border-box;margin:clamp(14px,3vh,28px) auto 20px;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none;gap:16px}
.assistant-input--empty{margin-top:2px;padding:0}
.assistant-intro__heading h2{font:500 clamp(19px,2.3vw,24px)/1.5 var(--font-sans);letter-spacing:0;color:#284238}
.assistant-starters{gap:9px}
.assistant-starters button{min-height:44px;padding:9px 12px;border-color:#e2e8e3;border-radius:9px;background:#fff;font-size:12px;box-shadow:none}
.assistant-chat{display:flex;flex-direction:column;align-items:stretch;width:100%;max-width:920px}
.assistant-bubble{align-self:flex-end;justify-self:auto}
.assistant-answer{flex:0 0 auto;width:100%;min-width:0;box-sizing:border-box}
.assistant-answer--pending{min-height:24px}
@media(max-width:600px){.assistant-intro{margin:24px auto;padding:0}.assistant-intro__heading h2{font-size:19px}}

.assistant-product-recommendation { gap: 0; padding: 0; overflow: hidden; border: 1px solid #e8ebe6; border-radius: 12px; background: #fff; box-shadow: 0 2px 10px rgba(38,55,45,.035); }
.assistant-cards :deep(.product-card--compact) { border: 0; border-radius: 0; box-shadow: none; background: #fff; }
.assistant-product-advice { display: grid; gap: 7px; margin: 0; padding: 10px 14px 12px; border: 0; border-top: 1px solid #edf0eb; border-radius: 0; background: #fbfcfa; color: #4c5a51; font-size: 13px; line-height: 1.65; }
.assistant-product-advice > strong { color: #315746; font-size: 13px; font-weight: 650; }
.assistant-product-advice p { display: block; margin: 0; color: #526057; }
.assistant-product-advice .assistant-reason-tags { display: flex !important; grid-template-columns: none !important; flex-wrap: wrap; align-items: center; gap: 6px; }
.assistant-product-advice .assistant-reason-tags span { display: inline-flex; flex: 0 0 auto; width: max-content; max-width: 100%; padding: 4px 9px; border-radius: 999px; background: #eef2ed; color: #526257; font-size: 11.5px; line-height: 1.4; }

</style>



<style scoped>
.assistant--page .assistant-scroll { padding: 4px 0 12px; }
.assistant--page .assistant-intro {
  width: min(100%, 1000px);
  margin: clamp(56px, 8vh, 76px) auto 24px;
  padding: 0;
  gap: 22px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
.assistant--page .assistant-intro__heading h2 {
  max-width: 960px;
  color: #284238;
  font: 600 clamp(24px, 2.1vw, 28px)/1.45 var(--font-sans);
  letter-spacing: 0;
}
.assistant--page .assistant-starters { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px; }
.assistant--page .assistant-starters button {
  min-height: 58px;
  padding: 10px 14px;
  border-color: #e2e8e3;
  border-radius: 10px;
  background: #fff;
  color: #41584b;
  font-size: 13px;
  line-height: 1.5;
  box-shadow: none;
}
.assistant--page .assistant-starters button:hover { border-color: #b9cec0; background: #fbfcfb; }
.assistant--page .assistant-input {
  width: min(100%, 960px);
  max-width: 960px;
  align-items: stretch;
  gap: 12px;
  margin-inline: auto;
  padding: 12px 0 0;
}
.assistant--page .assistant-input--empty { width: 100%; max-width: 100%; margin: 0; padding: 0; }
.assistant--page .assistant-input textarea { min-height: 52px; padding: 13px 15px; border-radius: 10px; background: #fff; font-size: 14px; }
.assistant--page .assistant-input button { height: 52px; min-width: 92px; padding-inline: 20px; border-radius: 9px; background: var(--visitor-action, #e96b24); font-size: 14px; }
.assistant--page .assistant-chat { width: 100%; max-width: 960px; margin-inline: auto; }
@media (max-width: 700px) {
  .assistant--page .assistant-intro { margin: 42px auto 20px; gap: 18px; }
  .assistant--page .assistant-intro__heading h2 { font-size: 24px; }
  .assistant--page .assistant-starters { grid-template-columns: 1fr 1fr; gap: 8px; }
  .assistant--page .assistant-starters button { min-height: 54px; padding: 8px 10px; font-size: 12px; }
  .assistant--page .assistant-input { gap: 8px; }
  .assistant--page .assistant-input textarea { min-height: 50px; padding: 12px; }
  .assistant--page .assistant-input button { min-width: 76px; height: 50px; padding-inline: 13px; }
}
@media (max-width: 420px) {
  .assistant--page .assistant-starters { grid-template-columns: 1fr; }
}
</style>

<style scoped>
.assistant--page { width: 100%; max-width: 100%; min-width: 0; min-height: 0; }
.assistant-context { position: sticky; top: 0; z-index: 4; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex: 0 0 auto; width: 100%; max-width: 1000px; min-height: 50px; margin: 0 auto; border-bottom: 1px solid #e5e9e5; background: #f7f8f6; }
.assistant-context > div { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.assistant-context span { color: #7d8981; font-size: 12px; white-space: nowrap; }
.assistant-context strong { overflow: hidden; color: #34483d; font-size: 14px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.assistant-context a { color: #597865; font-size: 12px; text-decoration: none; white-space: nowrap; }
.assistant--page .assistant-scroll { flex: 1 1 0; min-height: 0; width: 100%; overflow-x: hidden; overflow-y: auto; padding: 0 0 18px; }
.assistant--page .assistant-intro { width: min(100%, 960px); margin: clamp(32px, 6vh, 64px) auto 20px; gap: 18px; }
.assistant--page .assistant-intro__heading h2 { font-size: 24px; line-height: 1.5; }
.assistant--page .assistant-chat { width: min(100%, 920px); max-width: 920px; padding-bottom: 12px; }
.assistant--page .assistant-input { position: sticky; bottom: 0; z-index: 3; flex: 0 0 auto; width: min(100%, 960px); max-width: 960px; margin: 0 auto; padding: 12px 0 max(12px, env(safe-area-inset-bottom)); background: #f7f8f6; box-shadow: 0 -8px 18px rgba(247, 248, 246, .92); }
.assistant--page .assistant-input--empty { width: min(100%, 960px); max-width: 960px; margin: 0 auto; padding: 12px 0 max(12px, env(safe-area-inset-bottom)); }
.assistant--page .assistant-starters button { min-height: 54px; font-size: 13px; }
@media (max-width: 700px) {
  .assistant-context { min-height: 46px; }
  .assistant--page .assistant-intro { margin: 32px auto 16px; }
  .assistant--page .assistant-intro__heading h2 { font-size: 22px; }
  .assistant--page .assistant-input { gap: 8px; }
}
</style>

<style scoped>
.assistant--page { position: relative; }
.assistant--page .assistant-scroll { overflow-anchor: none; }
.assistant-scroll-end {
  position: absolute;
  z-index: 5;
  right: max(12px, calc((100% - 960px) / 2 + 12px));
  bottom: 78px;
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid #dce5dd;
  border-radius: 50%;
  background: #fff;
  color: #385b49;
  box-shadow: 0 3px 12px rgba(36, 55, 44, .14);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}
.assistant-scroll-end:hover { background: #f2f7f2; }
@media (max-width: 700px) { .assistant-scroll-end { right: 14px; bottom: 72px; } }
</style>

<style scoped>
.assistant-product-recommendation { display: grid; gap: 7px; padding: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; }
.assistant-product-advice { gap: 4px; padding: 0 2px 2px; border: 0; background: transparent; font-size: 13px; line-height: 1.55; }
.assistant-product-advice > strong { color: #3b5848; font-size: 13px; }
.assistant-product-advice p { color: #425248; }
.assistant-product-advice .assistant-reason-tags { gap: 6px; }
.assistant-product-advice .assistant-reason-tags span { padding: 3px 8px; background: #f0f3ef; font-size: 11px; }
.assistant-cards :deep(.product-card--compact) { display: grid; grid-template-columns: 180px minmax(0, 1fr); min-height: 130px; max-height: 190px; overflow: hidden; border: 1px solid #e8e9e5; border-radius: 12px; background: #fff; box-shadow: 0 2px 9px rgba(38, 55, 45, .035); }
.assistant-cards :deep(.product-card--compact > .product-card__media) { height: 130px; min-height: 130px; overflow: hidden; }
.assistant-cards :deep(.product-card--compact > .product-card__media > .media-image) { width: 100%; height: 130px; min-height: 130px; aspect-ratio: auto; border-radius: 0; }
.assistant-cards :deep(.product-card--compact .product-card__body) { align-content: center; gap: 5px; padding: 10px 13px; }
.assistant-cards :deep(.product-card--compact h3) { font-size: 15px; line-height: 1.35; }
@media (max-width: 700px) {
  .assistant-cards :deep(.product-card--compact) { grid-template-columns: 112px minmax(0,1fr); min-height: 108px; max-height: 170px; }
  .assistant-cards :deep(.product-card--compact > .product-card__media),
  .assistant-cards :deep(.product-card--compact > .product-card__media > .media-image) { height: 108px; min-height: 108px; }
}
</style>

<style scoped>
.assistant-cards { display:grid; grid-template-columns:minmax(0,1fr); gap:16px; }
.assistant-cards :deep(.product-card--recommendation) {
  display:grid; grid-template-columns:200px minmax(0,1fr); grid-template-rows:auto auto;
  min-width:0; max-height:none; overflow:hidden; padding:0; border:1px solid #e5e9e3;
  border-radius:14px; background:#fff; box-shadow:0 3px 14px rgba(38,55,45,.045);
}
.assistant-cards :deep(.product-card--recommendation > .product-card__media) {
  grid-column:1; grid-row:1; width:200px; height:142px; min-height:142px; overflow:hidden; cursor:pointer;
}
.assistant-cards :deep(.product-card--recommendation > .product-card__media > .media-image),
.assistant-cards :deep(.product-card--recommendation > .product-card__media img) {
  width:100%; height:100%; min-height:142px; aspect-ratio:auto; object-fit:cover; border-radius:0;
}
.assistant-cards :deep(.product-card--recommendation > .product-card__body) {
  grid-column:2; grid-row:1; display:grid; align-content:center; gap:7px; min-width:0; padding:14px 18px; cursor:pointer;
}
.assistant-cards :deep(.product-card--recommendation h3) { margin:0; color:#243a31; font-size:16px; line-height:1.4; }
.assistant-cards :deep(.product-card__recommendation-meta) { display:flex; flex-wrap:wrap; gap:5px 12px; color:#78827b; font-size:12px; }
.assistant-cards :deep(.product-card--recommendation .product-card__inclusions) { display:flex; flex-wrap:wrap; gap:5px; }
.assistant-cards :deep(.product-card--recommendation .product-card__inclusions span) { padding:3px 8px; border-radius:999px; background:#f1f4f0; color:#596a5f; font-size:11.5px; }
.assistant-cards :deep(.product-card--recommendation .product-card__bottom) { display:flex; justify-content:space-between; align-items:baseline; gap:12px; padding-top:5px; border-top:1px solid #eef0ed; }
.assistant-cards :deep(.product-card--recommendation .product-card__bottom strong) { color:#f06a22; font-size:17px; }
.assistant-cards :deep(.product-card__recommendation) {
  grid-column:1/-1; display:grid; gap:7px; min-width:0; padding:14px 18px 16px;
  border-top:1px solid #edf0eb; background:#fafcf9; color:#46564c; cursor:default;
}
.assistant-cards :deep(.product-card__recommendation > strong) { color:#315746; font-size:14px; font-weight:650; }
.assistant-cards :deep(.product-card__recommendation > p) { max-width:900px; margin:0; font-size:13.5px; line-height:1.75; }
.assistant-cards :deep(.product-card__recommendation-tags) { display:flex; flex-wrap:wrap; gap:6px; }
.assistant-cards :deep(.product-card__recommendation-tags span) {
  display:inline-flex; width:max-content; max-width:100%; padding:4px 9px; border-radius:999px;
  background:#eef2ed; color:#526257; font-size:11.5px; line-height:1.4;
}
@media(max-width:700px) {
  .assistant-cards :deep(.product-card--recommendation) { grid-template-columns:112px minmax(0,1fr); }
  .assistant-cards :deep(.product-card--recommendation > .product-card__media) { width:112px; height:124px; min-height:124px; }
  .assistant-cards :deep(.product-card--recommendation > .product-card__media > .media-image),
  .assistant-cards :deep(.product-card--recommendation > .product-card__media img) { min-height:124px; }
  .assistant-cards :deep(.product-card--recommendation > .product-card__body) { gap:5px; padding:10px 11px; }
  .assistant-cards :deep(.product-card--recommendation h3) { font-size:14px; }
  .assistant-cards :deep(.product-card__recommendation) { padding:12px; }
}
</style>


<style scoped>
.assistant-cards :deep(.product-card__recommendation-note) {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 0;
  color: #69756d;
  font-size: 12.5px;
  line-height: 1.55;
}
.assistant-cards :deep(.product-card__recommendation-note b) {
  flex: 0 0 auto;
  color: #826346;
  font-weight: 600;
}
</style>
