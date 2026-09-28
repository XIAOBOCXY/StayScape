import { onUnmounted, ref } from 'vue'

/** One shared one-second ticker for every countdown on the page. */
const now = ref(Date.now())
let timer: number | undefined
let subscribers = 0

function subscribe() {
  subscribers += 1
  if (timer === undefined) {
    timer = window.setInterval(() => { now.value = Date.now() }, 1000)
  }
}

function unsubscribe() {
  subscribers = Math.max(0, subscribers - 1)
  if (!subscribers && timer !== undefined) {
    window.clearInterval(timer)
    timer = undefined
  }
}

/** Sales for one departure close at 00:00 on the departure date. */
export function saleDeadline(targetDate: string | undefined | null): number | null {
  const value = String(targetDate || '')
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) return null
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 0, 0, 0).getTime()
}

export function formatRemaining(deadline: number | null, reference: number): string {
  if (deadline === null) return ''
  const diff = deadline - reference
  if (diff <= 0) return '已截止'
  const totalSeconds = Math.floor(diff / 1000)
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return days > 0
    ? `${days}天 ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
    : `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
}

/** Reactive countdown text for one departure date. */
export function useCountdown(targetDate: () => string | undefined | null) {
  subscribe()
  onUnmounted(unsubscribe)
  return {
    remaining: () => formatRemaining(saleDeadline(targetDate()), now.value),
    expired: () => {
      const deadline = saleDeadline(targetDate())
      return deadline !== null && deadline <= now.value
    },
  }
}
