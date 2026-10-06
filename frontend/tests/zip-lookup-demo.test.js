import { after, test } from 'node:test'
import { setImmediate } from 'node:timers'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createRenderer, createSSRApp, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'

const server = await createServer({
  configFile: false, plugins: [vue()],
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom',
})
after(() => server.close())
const { default: ZipLookupDemo } = await server.ssrLoadModule('/src/components/ZipLookupDemo.vue')
const renderer = createRenderer({
  createComment: () => ({}),
  insert() {}, remove() {}, parentNode: () => null, nextSibling: () => null,
})
const location = {
  postcode: '16802', country_code: 'us', locality: 'University Park',
  latitude: 40.8, longitude: -77.86,
}
const hotels = [
  {
    place_id: 'hotel-1', name: 'Scholar Hotel', address: '1 College Ave',
    latitude: 40.801, longitude: -77.86, distance_m: 111,
  },
  {
    place_id: 'hotel-2', name: 'Nittany Lion Inn', address: null,
    latitude: 40.802, longitude: -77.861, distance_m: 222,
  },
]

// Existing Part 1 rendering/selection assertions now follow an empty local lookup.
function backendFetch(t, implementation) {
  const wrap = (handler) => (url, options) => {
    if (url.startsWith('/api/local-hotels?')) return Promise.resolve(Response.json([]))
    if (url === '/api/local-hotels/ids') return Promise.resolve(Response.json([]))
    return handler(url, options)
  }
  const fetch = t.mock.method(globalThis, 'fetch', wrap(implementation))
  return {
    mock: {
      callCount: () => fetch.mock.callCount(),
      mockImplementation: (handler) => fetch.mock.mockImplementation(wrap(handler)),
    },
  }
}

function mount(t) {
  const app = renderer.createApp({ ...ZipLookupDemo, render: () => null })
  app.provide(ssrContextKey, {})
  const state = app.mount({}).$.setupState
  t.after(() => app.unmount())
  return state
}

function render(state) {
  return renderToString(createSSRApp({ ...ZipLookupDemo, setup: () => state }))
}

test('panel waits for a click and exposes the demo button and a labeled ZIP form', async (t) => {
  const fetch = backendFetch(t, () => assert.fail('No automatic lookup'))
  const state = mount(t)
  const html = await render(state)
  assert.equal(fetch.mock.callCount(), 0)
  assert.match(html, /ZIP lookup demonstration/)
  assert.match(html, /Look up ZIP 16802/)
  assert.equal((html.match(/<button /g) ?? []).length, 2)
  assert.match(html, /<form/)
  assert.match(html, /<label for="zip-postcode"[^>]*>ZIP code<\/label>/)
  assert.match(html, /type="text" inputmode="numeric"/)
  assert.match(html, /pattern="\[0-9\]\{5\}"/)
  assert.match(html, /<button[^>]*type="submit"/)
})

test('request uses the backend adapter; loading clears old content and blocks repeat clicks', async (t) => {
  let finish
  const fetch = backendFetch(t, (url, options) => {
    assert.equal(options.method ?? 'GET', 'GET')
    assert.equal(options.credentials, 'same-origin')
    if (url === '/api/zip-hotels?postcode=16802') return Promise.resolve(Response.json(hotels))
    assert.equal(url, '/api/demo/zip-location')
    return new Promise((resolve) => { finish = resolve })
  })
  const state = mount(t)
  state.location = location
  state.error = 'Earlier error'
  const pending = state.lookUpZip()
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(state.location, null)
  assert.equal(state.error, '')
  assert.equal(state.isLoading, true)
  const loadingHtml = await render(state)
  assert.match(loadingHtml, /aria-busy="true"/)
  assert.match(loadingHtml, /<button[^>]* disabled/)
  assert.match(loadingHtml, /role="status"/)
  assert.match(loadingHtml, /Looking up ZIP 16802 and nearby hotels…/)
  assert.doesNotMatch(loadingHtml, /University Park|Earlier error/)
  await state.lookUpZip('02108')
  assert.equal(fetch.mock.callCount(), 3)

  finish(Response.json(location))
  await pending
  assert.deepEqual(state.location, location)
  assert.deepEqual(state.hotels, hotels)
  assert.equal(state.isLoading, false)
  assert.equal(fetch.mock.callCount(), 4)
  const html = await render(state)
  for (const value of ['Postcode', '16802', 'Locality', 'University Park', 'Latitude', '40.8', 'Longitude', '-77.86']) {
    assert.ok(html.includes(value))
  }
  assert.doesNotMatch(html, / disabled/)
})

test('successful response can omit locality and preserves zero coordinates', async (t) => {
  backendFetch(t, async (url) => url.startsWith('/api/zip-hotels')
    ? Response.json([])
    : Response.json({ ...location, locality: null, latitude: 0, longitude: 0 }))
  const state = mount(t)
  await state.lookUpZip()
  const html = await render(state)
  assert.doesNotMatch(html, /Locality|University Park/)
  assert.match(html, /Latitude/)
  assert.equal((html.match(/<dd[^>]*>0<\/dd>/g) ?? []).length, 2)
})

test('backend errors are displayed and retry clears the previous error', async (t) => {
  let succeed = false
  backendFetch(t, async (url) => {
    if (url.startsWith('/api/zip-hotels')) return Response.json([])
    return succeed
      ? Response.json(location)
      : Response.json({ detail: 'The location provider request failed.' }, { status: 502 })
  })
  const state = mount(t)
  state.location = location
  await state.lookUpZip()
  assert.equal(state.location, null)
  assert.equal(state.isLoading, false)
  const html = await render(state)
  assert.match(html, /role="alert"/)
  assert.match(html, /The location provider request failed\./)
  assert.doesNotMatch(html, /University Park/)
  succeed = true
  const pending = state.lookUpZip()
  await new Promise((resolve) => setImmediate(resolve))
  assert.equal(state.error, '')
  await pending
  assert.deepEqual(state.location, location)
})

test('network errors and malformed success responses leave the button usable', async (t) => {
  const fetch = backendFetch(t, async () => { throw new Error('offline') })
  const state = mount(t)
  await state.lookUpZip()
  assert.equal(state.error, 'The server is unavailable. Please try again.')
  assert.equal(state.isLoading, false)
  fetch.mock.mockImplementation(async () => Response.json({ postcode: '16802' }))
  await state.lookUpZip()
  assert.equal(state.error, 'The ZIP lookup returned an unexpected response.')
  assert.equal(state.isLoading, false)
  assert.equal(state.location, null)
})

test('entered ZIP preserves leading zeros and replaces the demo result in the same panel', async (t) => {
  let finish
  const enteredLocation = { ...location, postcode: '02108', locality: 'Boston' }
  const fetch = backendFetch(t, (url, options) => {
    assert.equal(options.method ?? 'GET', 'GET')
    assert.equal(options.credentials, 'same-origin')
    if (url === '/api/zip-hotels?postcode=02108') return Promise.resolve(Response.json(hotels))
    assert.equal(url, '/api/zip-location?postcode=02108')
    return new Promise((resolve) => { finish = resolve })
  })
  const state = mount(t)
  state.location = location
  state.postcode = '02108'
  const pending = state.lookUpZip(state.postcode)
  await new Promise((resolve) => setImmediate(resolve))
  const loadingHtml = await render(state)
  assert.match(loadingHtml, /Looking up ZIP 02108 and nearby hotels…/)
  assert.equal((loadingHtml.match(/<button[^>]* disabled/g) ?? []).length, 2)
  assert.match(loadingHtml, /<input[^>]* disabled/)
  assert.doesNotMatch(loadingHtml, /University Park/)
  await state.lookUpZip()
  assert.equal(fetch.mock.callCount(), 3)
  finish(Response.json(enteredLocation))
  await pending
  assert.equal(fetch.mock.callCount(), 4)
  const html = await render(state)
  assert.equal((html.match(/<dl /g) ?? []).length, 1)
  assert.match(html, /Boston/)
  assert.match(html, /<dd[^>]*>02108<\/dd>/)
  assert.doesNotMatch(html, /University Park| disabled/)
})

test('invalid ZIP input shows a useful error without contacting the backend', async (t) => {
  backendFetch(t, () => assert.fail('Invalid ZIP must not be sent'))
  const state = mount(t)
  for (const postcode of ['', '1234', '123456', 'abcde', '１２３４５', ' 16802', '16802\n']) {
    await state.lookUpZip(postcode)
    assert.equal(state.error, 'Enter a ZIP code containing exactly five digits.')
    assert.equal(state.isLoading, false)
    assert.equal(state.location, null)
  }
  assert.match(await render(state), /role="alert"/)
})

test('entered ZIP provider errors allow retry and switching back to the demo', async (t) => {
  const fetch = backendFetch(t, async () =>
    Response.json({ detail: 'No matching U.S. location was found for ZIP 00000.' }, { status: 404 }))
  const state = mount(t)
  await state.lookUpZip('00000')
  assert.match(await render(state), /No matching U.S. location was found for ZIP 00000\./)
  assert.equal(state.isLoading, false)
  fetch.mock.mockImplementation(async (url) => {
    if (url === '/api/demo/zip-location') return Response.json(location)
    assert.equal(url, '/api/zip-hotels?postcode=16802')
    return Response.json([])
  })
  await state.lookUpZip()
  assert.equal(state.error, '')
  assert.deepEqual(state.location, location)
})

test('nearby hotel list and map share the selected hotel', async (t) => {
  backendFetch(t, async (url) => url.startsWith('/api/zip-hotels')
    ? Response.json(hotels)
    : Response.json(location))
  const state = mount(t)
  await state.lookUpZip()
  let html = await render(state)
  assert.match(html, /Hotels within 5 km of ZIP 16802/)
  assert.match(html, /Map of nearby hotels/)
  assert.match(html, /Scholar Hotel/)
  assert.match(html, /Nittany Lion Inn/)
  assert.match(html, /2 hotels/)
  assert.equal((html.match(/aria-pressed="false"/g) ?? []).length, 2)

  state.selectHotel('hotel-2')
  assert.equal(state.selectedPlaceId, 'hotel-2')
  html = await render(state)
  assert.match(html, /Selected Nittany Lion Inn/)
  assert.equal((html.match(/aria-pressed="true"/g) ?? []).length, 1)
})

test('new ZIP clears prior hotels and selection; hotel errors keep the resolved location', async (t) => {
  let failHotels = false
  backendFetch(t, async (url) => {
    if (url.startsWith('/api/zip-hotels')) {
      return failHotels
        ? Response.json({ detail: 'The hotel provider request failed.' }, { status: 502 })
        : Response.json(hotels)
    }
    return Response.json(location)
  })
  const state = mount(t)
  await state.lookUpZip()
  state.selectHotel('hotel-1')
  failHotels = true
  await state.lookUpZip()
  assert.deepEqual(state.location, location)
  assert.deepEqual(state.hotels, [])
  assert.equal(state.selectedPlaceId, '')
  assert.equal(state.hasLoadedHotels, false)
  assert.match(await render(state), /The hotel provider request failed\./)
})

const localHotel = {
  ...hotels[0], location,
  demo_nights: [{ stay_date: '2026-10-10', nightly_rate_usd: '100.00', rooms_available: 20 }],
}

test('local-first lookup uses stored context and shows the saved subset with classroom nights', async (t) => {
  const urls = []
  t.mock.method(globalThis, 'fetch', async (url) => {
    urls.push(url)
    assert.equal(url, '/api/local-hotels?postcode=16802')
    return Response.json([localHotel])
  })
  const state = mount(t)
  await state.lookUpZip()
  assert.deepEqual(urls, ['/api/local-hotels?postcode=16802'])
  assert.deepEqual(state.location, location)
  assert.equal(state.savedIds.has('hotel-1'), true)
  const html = await render(state)
  assert.match(html, /Saved locally/)
  assert.match(html, /not a complete list/)
  assert.match(html, /Simulated classroom data/)
  assert.match(html, /2026-10-10 · \$100\.00\/night · 20 rooms available/)
  assert.match(html, /Remove from Local/)
  assert.match(html, /<button[^>]*disabled[^>]*>Add to Local/)
})

test('local errors stop lookup without contacting either provider endpoint', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async (url) => {
    assert.equal(url, '/api/local-hotels?postcode=02108')
    return Response.json({ detail: 'Saved hotels could not be loaded. Please try again.' }, { status: 500 })
  })
  const state = mount(t)
  await state.lookUpZip('02108')
  assert.equal(fetch.mock.callCount(), 1)
  assert.equal(state.hotels.length, 0)
  assert.equal(state.location, null)
  assert.match(await render(state), /role="alert".*Saved hotels could not be loaded/s)
})

test('empty local lookup falls back in order and restores saved status globally by ID', async (t) => {
  const urls = []
  t.mock.method(globalThis, 'fetch', async (url) => {
    urls.push(url)
    if (url.startsWith('/api/local-hotels?')) return Response.json([])
    if (url.endsWith('/ids')) return Response.json(['hotel-1'])
    if (url === '/api/demo/zip-location') return Response.json(location)
    if (url.startsWith('/api/zip-hotels?')) return Response.json(hotels)
    assert.fail(url)
  })
  const state = mount(t)
  await state.lookUpZip()
  assert.deepEqual(urls, ['/api/local-hotels?postcode=16802', '/api/local-hotels/ids', '/api/demo/zip-location', '/api/zip-hotels?postcode=16802'])
  assert.equal(state.resultSource, 'API results')
  assert.equal(state.savedIds.has('hotel-1'), true)
  assert.equal(state.savedIds.has('hotel-2'), false)
  assert.equal((await render(state)).match(/Remove from Local/g).length, 1)
})

test('Add stays pending until success, sends current context, blocks duplicate clicks and ZIP changes', async (t) => {
  let finish
  const fetch = t.mock.method(globalThis, 'fetch', (url, options) => {
    assert.equal(url, '/api/local-hotels')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers.get('X-Requested-With'), 'XMLHttpRequest')
    assert.deepEqual(JSON.parse(options.body), { hotel: hotels[0], location })
    return new Promise((resolve) => { finish = resolve })
  })
  const state = mount(t)
  state.location = location
  state.hotels = hotels
  state.resultSource = 'API results'
  state.hasLoadedHotels = true
  state.selectedPlaceId = 'hotel-1'
  const pending = state.addHotel(hotels[0])
  assert.equal(state.savedIds.has('hotel-1'), false)
  assert.equal(state.pendingIds.has('hotel-1'), true)
  const html = await render(state)
  assert.match(html, /Saving…/)
  assert.match(html, /<input[^>]*disabled/)
  await state.addHotel(hotels[0])
  await state.lookUpZip('02108')
  assert.equal(fetch.mock.callCount(), 1)
  finish(Response.json(localHotel, { status: 201 }))
  await pending
  assert.equal(state.savedIds.has('hotel-1'), true)
  assert.equal(state.pendingIds.size, 0)
  assert.equal(state.selectedPlaceId, 'hotel-1')
  assert.match(await render(state), /saved locally with simulated classroom nights/)
})

test('failed Add keeps hotel unsaved and available to retry', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'The hotel could not be saved.' }, { status: 500 }))
  const state = mount(t)
  state.location = location
  state.hotels = hotels
  await state.addHotel(hotels[0])
  assert.equal(state.savedIds.has('hotel-1'), false)
  assert.equal(state.pendingIds.size, 0)
  assert.match(await render(state), /The hotel could not be saved/)
})

test('Remove keeps saved cards until success, then removes only that local result and selection', async (t) => {
  let finish
  t.mock.method(globalThis, 'fetch', (url, options) => {
    assert.equal(options.method, 'DELETE')
    assert.equal(url, '/api/local-hotels')
    assert.equal(options.headers.get('X-Requested-With'), 'XMLHttpRequest')
    assert.deepEqual(JSON.parse(options.body), { place_id: 'hotel-1' })
    return new Promise((resolve) => { finish = resolve })
  })
  const state = mount(t)
  state.location = location
  state.hotels = [localHotel, { ...localHotel, place_id: 'hotel-2' }]
  state.savedIds = new Set(['hotel-1', 'hotel-2'])
  state.resultSource = 'Saved locally'
  state.hasLoadedHotels = true
  state.selectedPlaceId = 'hotel-1'
  const pending = state.removeHotel(localHotel)
  assert.equal(state.hotels.length, 2)
  assert.equal(state.savedIds.has('hotel-1'), true)
  assert.match(await render(state), /Removing…/)
  finish(new Response(null, { status: 204 }))
  await pending
  assert.deepEqual(state.hotels.map((hotel) => hotel.place_id), ['hotel-2'])
  assert.equal(state.savedIds.has('hotel-1'), false)
  assert.equal(state.selectedPlaceId, '')
})

test('failed Remove preserves saved state, result and selection; API removal keeps the API card', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'The hotel could not be removed.' }, { status: 500 }))
  const state = mount(t)
  state.location = location
  state.hotels = [localHotel]
  state.savedIds = new Set(['hotel-1'])
  state.selectedPlaceId = 'hotel-1'
  state.resultSource = 'Saved locally'
  await state.removeHotel(localHotel)
  assert.equal(state.savedIds.has('hotel-1'), true)
  assert.equal(state.hotels.length, 1)
  assert.equal(state.selectedPlaceId, 'hotel-1')
  assert.equal(state.pendingIds.size, 0)
  assert.match(await render(state), /The hotel could not be removed/)
  fetch.mock.mockImplementation(async () => new Response(null, { status: 204 }))
  state.resultSource = 'API results'
  await state.removeHotel(localHotel)
  assert.equal(state.savedIds.has('hotel-1'), false)
  assert.equal(state.hotels.length, 1)
  assert.equal(state.selectedPlaceId, 'hotel-1')
})
