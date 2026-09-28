import test from 'node:test'
import assert from 'node:assert/strict'
import { promoteCandidate } from './productGenerationState.mjs'

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
