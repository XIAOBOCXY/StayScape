<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { visitorApi } from '../api'
import { errorMessage } from '../api/client'
import ProductCard from './ProductCard.vue'
import type { TravelProduct } from '../types'
import { visitorConversationId } from '../utils/visitorProfile'

const props = defineProps<{ productId?: number | null; weather?: string }>()

type RoomOption = {
  room_inventory_id: number
  room_type: string
  max_guests: number
  price: string
  remaining: number
  is_current: boolean
}
type Chat = {
  user?: string
  answer?: string
  safety_notes?: string
  reasons?: Record<string, string>
  schedule_notes?: Record<string, Array<{ time?: string; content?: string }>>
  limited_adjustments?: Record<string, string[]>
  suggestions?: TravelProduct[]
  follow_up_questions?: string[]
  product_id?: number | null
  room_options?: RoomOption[]
}

// 助手回答不止一段话：把「为什么推荐 / 时间怎么排 / 哪些改不了」结构化展示出来。
function nameFor(chat: Chat, id: string) {
  const found = (chat.suggestions || []).find((item) => String(item.id) === String(id))
  return found?.product_name || '推荐方案'
}

function reasonRows(chat: Chat) {
  return Object.entries(chat.reasons || {}).map(([id, text]) => ({ name: nameFor(chat, id), text: String(text) }))
}

function scheduleRows(chat: Chat) {
  return Object.entries(chat.schedule_notes || {})
    .map(([id, items]) => ({ key: id, name: nameFor(chat, id), items: Array.isArray(items) ? items : [] }))
    .filter((row) => row.items.length)
}

function limitRows(chat: Chat) {
  return Object.entries(chat.limited_adjustments || {})
    .map(([id, items]) => ({ name: nameFor(chat, id), text: Array.isArray(items) ? items.join('；') : String(items) }))
    .filter((row) => row.text)
}

const question = ref('')
const chats = ref<Chat[]>([])
const asking = ref(false)
const greeting = ref('你好，我可以按同行人、天气和当前在售的套餐帮你选路线。')
const starters = ref<string[]>([])
const scroller = ref<HTMLElement | null>(null)

const canAsk = computed(() => Boolean(question.value.trim()) && !asking.value)

// 按句号切段显示，避免一整段大白话，让「推荐理由」读起来更清楚。
function answerParagraphs(chat: Chat): string[] {
  return String(chat.answer || '')
    .split(/(?<=[。！？!?])/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function growInput(event: Event) {
  const el = event.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

async function loadIntro() {
  try {
    const response = await visitorApi.assistantIntro(props.productId ?? null)
    greeting.value = response.data.greeting
    starters.value = response.data.suggestions || []
  } catch {
    starters.value = ['下雨天还适合去吗？', '预算 700 左右有什么推荐？', '同一天还有哪些房型可选？']
  }
}

async function ask(text?: string) {
  const value = String(text ?? question.value).trim()
  if (!value || asking.value) return
  question.value = ''
  chats.value.push({ user: value })
  asking.value = true
  try {
    const response = await visitorApi.consult({
      product_id: props.productId ?? undefined,
      question: value,
      weather: props.weather || 'CLOUDY',
      conversation_id: visitorConversationId(),
    })
    chats.value.push({
      answer: String(response.data.answer || ''),
      safety_notes: String(response.data.safety_notes || ''),
      reasons: (response.data.reasons as Record<string, string>) || {},
      schedule_notes: (response.data.schedule_notes as Chat['schedule_notes']) || {},
      limited_adjustments: (response.data.limited_adjustments as Chat['limited_adjustments']) || {},
      suggestions: (response.data.suggestions as TravelProduct[]) || [],
      follow_up_questions: (response.data.follow_up_questions as string[]) || [],
      product_id: (response.data.product_id as number) ?? props.productId ?? null,
      room_options: (response.data.room_options as RoomOption[]) || [],
    })
  } catch (e) {
    chats.value.push({ answer: errorMessage(e) })
  } finally {
    asking.value = false
  }
}

async function scrollToEnd() {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => chats.value.length, scrollToEnd)
watch(asking, scrollToEnd)
onMounted(loadIntro)
</script>

<template>
  <section class="assistant">
    <div ref="scroller" class="assistant-scroll">
      <div v-if="!chats.length" class="assistant-intro">
        <p class="assistant-greeting">{{ greeting }}</p>
        <div class="assistant-starters">
          <button v-for="item in starters" :key="item" type="button" @click="ask(item)">{{ item }}</button>
        </div>
      </div>

      <div v-if="chats.length" class="assistant-chat">
        <template v-for="(chat, index) in chats" :key="index">
          <div v-if="chat.user" class="assistant-bubble is-user"><span>{{ chat.user }}</span></div>
          <div v-else class="assistant-answer">
            <p v-for="(paragraph, i) in answerParagraphs(chat)" :key="i" class="assistant-paragraph">{{ paragraph }}</p>
            <div v-if="chat.room_options?.length" class="assistant-rooms">
              <span class="assistant-rooms__label">可换房型 · 点一下直接切到该房型</span>
              <div class="assistant-rooms__list">
                <router-link
                  v-for="room in chat.room_options"
                  :key="room.room_inventory_id"
                  class="assistant-room"
                  :class="{ 'is-current': room.is_current, 'is-soldout': room.remaining <= 0 }"
                  :to="{ path: `/visitor/products/${chat.product_id}`, query: { room: String(room.room_inventory_id) } }"
                >
                  <b>{{ room.room_type }}<em v-if="room.is_current">当前</em></b>
                  <span>¥{{ room.price }}</span>
                  <small>可住 {{ room.max_guests }} 人 · {{ room.remaining > 0 ? `余 ${room.remaining}` : '已售完' }}</small>
                </router-link>
              </div>
            </div>
            <div v-if="chat.suggestions?.length" class="assistant-cards">
              <div v-for="item in chat.suggestions" :key="item.id" class="assistant-card">
                <ProductCard :product="item" public-view compact />
              </div>
            </div>
            <div v-if="reasonRows(chat).length" class="assistant-block">
              <b>为什么推荐</b>
              <ul>
                <li v-for="row in reasonRows(chat)" :key="`reason-${row.name}`"><strong>{{ row.name }}</strong>{{ row.text }}</li>
              </ul>
            </div>
            <div v-if="scheduleRows(chat).length" class="assistant-block">
              <b>时间怎么安排</b>
              <ul>
                <li v-for="row in scheduleRows(chat)" :key="`schedule-${row.key}`">
                  <strong>{{ row.name }}</strong>
                  <span v-for="(item, i) in row.items" :key="`slot-${row.key}-${i}`">{{ item.time ? `${item.time} ` : '' }}{{ item.content }}</span>
                </li>
              </ul>
            </div>
            <div v-if="limitRows(chat).length || chat.safety_notes" class="assistant-block assistant-block--note">
              <b>注意事项</b>
              <ul>
                <li v-for="row in limitRows(chat)" :key="`limit-${row.name}`"><strong>{{ row.name }}</strong>{{ row.text }}</li>
                <li v-if="chat.safety_notes"><strong>出行提示</strong>{{ chat.safety_notes }}</li>
              </ul>
            </div>
            <div v-if="chat.follow_up_questions?.length" class="assistant-followups">
              <button v-for="item in chat.follow_up_questions" :key="item" type="button" @click="ask(item)">{{ item }}</button>
            </div>
          </div>
        </template>
        <div v-if="asking" class="assistant-answer assistant-answer--pending">正在查询当前在售的套餐…</div>
      </div>
    </div>

    <form class="assistant-input" @submit.prevent="ask()">
      <textarea v-model="question" rows="1" placeholder="例如：下雨天带孩子去哪一组？" @input="growInput" @keydown.enter.exact.prevent="ask()" />
      <button type="submit" :disabled="!canAsk">发送</button>
    </form>
  </section>
</template>

<style scoped>
.assistant { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.assistant-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 4px 2px 12px; scrollbar-width: none; }
.assistant-scroll::-webkit-scrollbar { width: 0; height: 0; display: none; }
.assistant-intro { display: grid; gap: 12px; padding: 8px 0; }
.assistant-greeting { margin: 0; color: #4a5a54; font-size: 14px; line-height: 1.8; }
.assistant-starters { display: flex; flex-wrap: wrap; gap: 7px; }
.assistant-starters button { padding: 8px 12px; border: 1px solid #e6ded7; border-radius: 999px; background: #fff; color: #6f6259; font-size: 12px; cursor: pointer; }
.assistant-starters button:hover { border-color: #d56835; color: #d56835; }
.assistant-chat { display: grid; gap: 14px; }
.assistant-bubble { max-width: 82%; padding: 10px 13px; border-radius: 14px 14px 4px 14px; background: #eaf4ef; color: #23483d; font-size: 13px; line-height: 1.7; justify-self: end; }
.assistant-answer { max-width: 96%; color: #33403b; font-size: 14px; line-height: 1.8; }
.assistant-answer--pending { color: var(--muted); font-size: 13px; }
.assistant-paragraph { margin: 0 0 8px; }
.assistant-paragraph:last-child { margin-bottom: 0; }
.assistant-cards { display: grid; gap: 10px; margin-top: 12px; }
.assistant-rooms { margin-top: 12px; }
.assistant-rooms__label { display: block; margin-bottom: 7px; color: #9a8f87; font-size: 11px; }
.assistant-rooms__list { display: flex; flex-wrap: wrap; gap: 8px; }
.assistant-room { display: grid; gap: 2px; min-width: 132px; padding: 9px 12px; border: 1px solid #e7ded6; border-radius: 12px; background: #fff; color: #33302e; text-decoration: none; transition: border-color .18s, box-shadow .18s; }
.assistant-room:hover { border-color: #ff6a00; box-shadow: 0 6px 16px rgba(213, 104, 53, .12); }
.assistant-room b { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 650; }
.assistant-room b em { padding: 1px 6px; border-radius: 999px; background: #fff1e4; color: #d56835; font-size: 10px; font-style: normal; font-weight: 600; }
.assistant-room span { color: #d56835; font-size: 14px; font-weight: 700; }
.assistant-room small { color: #9a8f87; font-size: 10px; }
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
.assistant-cards :deep(.product-card--compact .product-card__hook) { min-height: 0; -webkit-line-clamp: 2; font-size: 11px; line-height: 1.5; }
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
</style>
