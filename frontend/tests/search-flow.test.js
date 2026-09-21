import { after, test } from 'node:test'
import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createRenderer, ssrContextKey } from 'vue'

const server = await createServer({
  configFile: false,
  plugins: [vue()],
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
})
after(() => server.close())
const { default: App } = await server.ssrLoadModule('/src/App.vue')
// Exercise the real View's interaction state without needing a browser DOM.
const renderer = createRenderer({
  createComment: () => ({}),
  insert() {},
  remove() {},
  parentNode: () => null,
  nextSibling: () => null,
})

const user = { user_id: 'U006', display_name: 'Demo Traveler 6' }
const stay = { trip_id: 'T001', nightly_rate_usd: '150', stay_price_usd: '300' }

async function mount(t) {
  const app = renderer.createApp({ ...App, render: () => null })
  app.provide(ssrContextKey, {})
  const state = app.mount({}).$.setupState
  t.after(() => app.unmount())
  await setImmediate()
  assert.equal(state.isAuthBusy, false)
  return state
}

test('sign-in refreshes existing results without submitting another search', async (t) => {
  const searches = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url === '/api/auth/me') return Response.json({ detail: 'Sign in' }, { status: 401 })
    if (url === '/api/auth/login') return Response.json(user)
    if (url === '/api/bookings') return Response.json([])
    searches.push({ url, method: options.method })
    return Response.json([{ ...stay, nightly_rate_usd: searches.length === 1 ? '150' : '180' }])
  })
  const state = await mount(t)
  state.hotelName = 'Harbor'
  await state.submitSearch()
  state.selectedTripId = 'T001'
  await state.submitSignIn({ username: 'traveler6', password: 'TravelDemo6!' })
  assert.deepEqual(searches, [
    { url: '/api/stays', method: 'POST' },
    { url: '/api/stays?hotel_name=Harbor', method: undefined },
  ])
  assert.equal(state.stays[0].nightly_rate_usd, '180')
  assert.equal(state.selectedTripId, 'T001')
})

test('blank input is not submitted and expiry clears private results and bookings', async (t) => {
  let submissions = 0
  t.mock.method(globalThis, 'fetch', async (url) => {
    if (url === '/api/auth/me') return Response.json(user)
    if (url === '/api/bookings') return Response.json([{ booking_id: 'B001' }])
    submissions += 1
    return Response.json({ detail: 'Session expired' }, { status: 401 })
  })
  const state = await mount(t)
  state.hotelName = '  '
  await state.submitSearch()
  assert.equal(submissions, 0)
  state.stays = [stay]
  state.hotelName = 'Harbor'
  await state.submitSearch()
  assert.equal(submissions, 1)
  assert.equal(state.currentUser, null)
  assert.deepEqual(state.stays, [])
  assert.deepEqual(state.bookings, [])
  assert.equal(state.isSearchLoading, false)
})

test('a pending personalized search cannot repopulate results after account clearing', async (t) => {
  let finishSearch
  t.mock.method(globalThis, 'fetch', async (url) => {
    if (url === '/api/auth/me') return Response.json(user)
    if (url === '/api/bookings') return Response.json([])
    return new Promise((resolve) => { finishSearch = resolve })
  })
  const state = await mount(t)
  state.hotelName = 'Harbor'
  const pending = state.submitSearch()
  state.clearAccount()
  finishSearch(Response.json([stay]))
  await pending
  assert.deepEqual(state.stays, [])
  assert.equal(state.hasSearched, false)
})
