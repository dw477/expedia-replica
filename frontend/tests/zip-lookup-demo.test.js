import { after, test } from 'node:test'
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
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('No automatic lookup'))
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
  const fetch = t.mock.method(globalThis, 'fetch', (url, options) => {
    assert.equal(url, '/api/demo/zip-location')
    assert.equal(options.method ?? 'GET', 'GET')
    assert.equal(options.credentials, 'same-origin')
    return new Promise((resolve) => { finish = resolve })
  })
  const state = mount(t)
  state.location = location
  state.error = 'Earlier error'
  const pending = state.lookUpZip()
  assert.equal(state.location, null)
  assert.equal(state.error, '')
  assert.equal(state.isLoading, true)
  const loadingHtml = await render(state)
  assert.match(loadingHtml, /aria-busy="true"/)
  assert.match(loadingHtml, /<button[^>]* disabled/)
  assert.match(loadingHtml, /role="status"/)
  assert.match(loadingHtml, /Looking up ZIP 16802…/)
  assert.doesNotMatch(loadingHtml, /University Park|Earlier error/)
  await state.lookUpZip('02108')
  assert.equal(fetch.mock.callCount(), 1)

  finish(Response.json(location))
  await pending
  assert.deepEqual(state.location, location)
  assert.equal(state.isLoading, false)
  const html = await render(state)
  for (const value of ['Postcode', '16802', 'Locality', 'University Park', 'Latitude', '40.8', 'Longitude', '-77.86']) {
    assert.ok(html.includes(value))
  }
  assert.doesNotMatch(html, / disabled/)
})

test('successful response can omit locality and preserves zero coordinates', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({
    ...location, locality: null, latitude: 0, longitude: 0,
  }))
  const state = mount(t)
  await state.lookUpZip()
  const html = await render(state)
  assert.doesNotMatch(html, /Locality|University Park/)
  assert.match(html, /Latitude/)
  assert.equal((html.match(/<dd[^>]*>0<\/dd>/g) ?? []).length, 2)
})

test('backend errors are displayed and retry clears the previous error', async (t) => {
  let succeed = false
  t.mock.method(globalThis, 'fetch', async () => succeed
    ? Response.json(location)
    : Response.json({ detail: 'The location provider request failed.' }, { status: 502 }))
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
  assert.equal(state.error, '')
  await pending
  assert.deepEqual(state.location, location)
})

test('network errors and malformed success responses leave the button usable', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => { throw new Error('offline') })
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
  const fetch = t.mock.method(globalThis, 'fetch', (url, options) => {
    assert.equal(url, '/api/zip-location?postcode=02108')
    assert.equal(options.method ?? 'GET', 'GET')
    assert.equal(options.credentials, 'same-origin')
    return new Promise((resolve) => { finish = resolve })
  })
  const state = mount(t)
  state.location = location
  state.postcode = '02108'
  const pending = state.lookUpZip(state.postcode)
  const loadingHtml = await render(state)
  assert.match(loadingHtml, /Looking up ZIP 02108…/)
  assert.equal((loadingHtml.match(/<button[^>]* disabled/g) ?? []).length, 2)
  assert.match(loadingHtml, /<input[^>]* disabled/)
  assert.doesNotMatch(loadingHtml, /University Park/)
  await state.lookUpZip()
  assert.equal(fetch.mock.callCount(), 1)
  finish(Response.json(enteredLocation))
  await pending
  const html = await render(state)
  assert.equal((html.match(/<dl /g) ?? []).length, 1)
  assert.match(html, /Boston/)
  assert.match(html, /<dd[^>]*>02108<\/dd>/)
  assert.doesNotMatch(html, /University Park| disabled/)
})

test('invalid ZIP input shows a useful error without contacting the backend', async (t) => {
  t.mock.method(globalThis, 'fetch', () => assert.fail('Invalid ZIP must not be sent'))
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
  const fetch = t.mock.method(globalThis, 'fetch', async () =>
    Response.json({ detail: 'No matching U.S. location was found for ZIP 00000.' }, { status: 404 }))
  const state = mount(t)
  await state.lookUpZip('00000')
  assert.match(await render(state), /No matching U.S. location was found for ZIP 00000\./)
  assert.equal(state.isLoading, false)
  fetch.mock.mockImplementation(async (url) => {
    assert.equal(url, '/api/demo/zip-location')
    return Response.json(location)
  })
  await state.lookUpZip()
  assert.equal(state.error, '')
  assert.deepEqual(state.location, location)
})
