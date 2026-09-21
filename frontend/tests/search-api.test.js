import { test } from 'node:test'
import assert from 'node:assert/strict'
import { searchAvailableStays } from '../src/api/stays.js'

test('submitted searches use POST with cookies and CSRF protection', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    return Response.json([{ trip_id: 'T001', nightly_rate_usd: '180.00' }])
  })
  const results = await searchAvailableStays(' HARBOR  Lantern ')
  assert.equal(results[0].nightly_rate_usd, '180.00')
  assert.equal(calls[0].url, '/api/stays')
  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.credentials, 'same-origin')
  assert.equal(calls[0].options.headers.get('X-Requested-With'), 'XMLHttpRequest')
  assert.deepEqual(JSON.parse(calls[0].options.body), { hotel_name: ' HARBOR  Lantern ' })
})

test('price refreshes use GET so they cannot count as submissions', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/stays?hotel_name=Harbor+Lantern')
    assert.equal(options.method, undefined)
    assert.equal(options.credentials, 'same-origin')
    return Response.json([])
  })
  assert.deepEqual(await searchAvailableStays('Harbor Lantern', { submitted: false }), [])
})

test('search expiry and invalid responses reach the View as errors', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Session expired' }, { status: 401 }))
  await assert.rejects(searchAvailableStays('Harbor'), { status: 401 })
  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () => Response.json({}))
  await assert.rejects(searchAvailableStays('Harbor'), /unexpected response/)
})
