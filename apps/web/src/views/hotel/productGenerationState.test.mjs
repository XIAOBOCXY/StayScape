import test from 'node:test'
import assert from 'node:assert/strict'
import { prepareAdvisorResponse, promoteCandidate, validationChangeNote } from './productGenerationState.mjs'

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
