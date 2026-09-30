import { test } from 'node:test'
import assert from 'node:assert/strict'

import { fetchNearbyHotels } from '../src/api/nearby-hotels.js'

const hotel = {
  place_id: 'geo-1', name: 'Scholar Hotel', address: null,
  latitude: 40.801, longitude: -77.86, distance_m: 112,
}

test('nearby hotel requests preserve the entered ZIP and return backend order', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/zip-hotels?postcode=02108')
    assert.equal(options.credentials, 'same-origin')
    return Response.json([hotel, { ...hotel, place_id: 'geo-2', name: 'Second Hotel' }])
  })

  const hotels = await fetchNearbyHotels('02108')
  assert.deepEqual(hotels.map((item) => item.place_id), ['geo-1', 'geo-2'])
  assert.equal(fetch.mock.callCount(), 1)
})

test('empty nearby results remain an empty list', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json([]))
  assert.deepEqual(await fetchNearbyHotels('16802'), [])
})

test('invalid hotel rows fail before reaching the map', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json([hotel, { ...hotel, latitude: '40.8' }]))
  await assert.rejects(fetchNearbyHotels('16802'), /unexpected response/)
  fetch.mock.mockImplementation(async () => Response.json({ hotels: [hotel] }))
  await assert.rejects(fetchNearbyHotels('16802'), /unexpected response/)
})
