import { test } from 'node:test'
import assert from 'node:assert/strict'
import { sortStays } from '../src/utils/stays.js'

const stays = [
  { trip_id: 'T001', stay_price_usd: '900.00' },
  { trip_id: 'T002', stay_price_usd: '100.50' },
  { trip_id: 'T003', stay_price_usd: '1200.00' },
  { trip_id: 'T004', stay_price_usd: '100.50' },
]

test('low price order compares decimal API prices numerically and retains ties', () => {
  assert.deepEqual(
    sortStays(stays, 'low').map((stay) => stay.trip_id),
    ['T002', 'T004', 'T001', 'T003'],
  )
})

test('high price order compares decimal API prices numerically', () => {
  assert.deepEqual(
    sortStays(stays, 'high').map((stay) => stay.trip_id),
    ['T003', 'T001', 'T002', 'T004'],
  )
})

test('sorting preserves the original booking choices and original-order option', () => {
  const snapshot = structuredClone(stays)
  sortStays(stays, 'low')
  assert.deepEqual(stays, snapshot)
  assert.deepEqual(sortStays(stays, 'recommended'), snapshot)
  assert.notEqual(sortStays(stays, 'recommended'), stays)
  assert.deepEqual(sortStays([], 'low'), [])
})
