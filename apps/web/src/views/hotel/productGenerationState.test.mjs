import test from 'node:test'
import assert from 'node:assert/strict'
import { prepareAdvisorResponse, primaryFromRefinedProduct, promoteCandidate, validationChangeNote } from './productGenerationState.mjs'

test('promoting a candidate retains the outgoing primary as a candidate', () => {
  const primary = { product_name: '城市慢享周末', price: 898, crowd: 'SOLO', party_size: 1 }
  const candidate = { key: 'proposal-17', source: 'proposal', product_id: 17, name: '静享双日假期', price: 968, crowd_label: '独自出行', party: 1, date: '2026-09-28', quantity: 3, experiences: ['晚餐体验'], raw: {} }
  const result = promoteCandidate(primary, [candidate], candidate.key)
  assert.equal(result.primary.product_name, '静享双日假期')
  assert.equal(result.primary.product_id, 17)
  assert.equal(result.candidates.length, 1)
  assert.equal(result.candidates[0].source, 'primary-snapshot')
  assert.equal(result.candidates[0].name, '城市慢享周末')
})

test('validation feedback explains that the current primary was retained', () => {
  const note = validationChangeNote({
    message: '9月27日已经过去，当前方案未修改',
    available_dates: ['2026-09-29', '2026-09-30'],
  })
  assert.match(note, /9月27日已经过去/)
  assert.match(note, /可选日期：2026-09-29、2026-09-30/)
})

test('validation response without a primary keeps the currently displayed card', () => {
  const previousPrimary = { product_name: '9月30日单人套餐', target_date: '2026-09-30', crowd: 'SOLO' }
  const currentAdvisor = { primary: previousPrimary, judgement: { plans: [{ name: '原推荐方向' }] } }
  const nextAdvisor = {
    validation_error: { message: '9月27日已经过去，当前方案未修改' },
    judgement: { plans: [] },
  }

  const result = prepareAdvisorResponse(currentAdvisor, previousPrimary, nextAdvisor)

  assert.equal(result.primary, previousPrimary)
  assert.equal(result.advisor.primary, previousPrimary)
  assert.deepEqual(result.advisor.judgement, currentAdvisor.judgement)
  assert.match(result.validationNote, /当前方案未修改/)
})

test('refined product replaces visible resources and refreshed itinerary', () => {
  const previous = {
    product_id: 8,
    product_name: '旧套餐',
    room_type: '旧房型',
    experiences: [{ name: '旧体验' }],
    services: [{ name: '旧权益' }],
    itinerary_days: [{ day_index: 1, items: [{ title: '旧体验' }] }],
  }
  const product = {
    id: 8,
    product_name: '更新套餐',
    target_date: '2026-09-30',
    target_crowd: 'FAMILY',
    party_size: 3,
    suggested_price: '688.00',
    unit_cost: '510.00',
    minimum_allowed_price: '637.50',
    gross_margin: '0.2587',
    sale_quantity: 4,
    resources: [
      { resource_type: 'ROOM', resource_name: '亲子房', resource_id: 3 },
      { resource_type: 'PARTNER_RESOURCE', resource_name: '夜间文化体验', resource_id: 17, start_time: '20:00:00', end_time: '21:00:00', quantity_per_package: 3, unit_cost: '35.00' },
      { resource_type: 'HOTEL_SERVICE', resource_name: '欢迎饮品', resource_id: 9, quantity_per_package: 3, unit_cost: '12.00' },
    ],
    day_plan: [{ day_index: 1, items: [{ title: '夜间文化体验' }] }],
    route_plan: [{ day_index: 1, legs: [] }],
  }
  const next = primaryFromRefinedProduct(product, previous)
  assert.equal(next.product_name, '更新套餐')
  assert.deepEqual(next.experiences.map((item) => item.name), ['夜间文化体验'])
  assert.deepEqual(next.services.map((item) => item.name), ['欢迎饮品'])
  assert.equal(next.margin, 25.9)
  assert.equal(next.itinerary_days[0].items[0].title, '夜间文化体验')
})
