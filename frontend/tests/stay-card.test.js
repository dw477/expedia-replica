import { after, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

const server = await createServer({
  configFile: false,
  plugins: [vue()],
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { middlewareMode: true },
  appType: 'custom',
})
after(() => server.close())
const { default: StayCard } = await server.ssrLoadModule('/src/components/StayCard.vue')

const stay = {
  trip_id: 'T003',
  hotel_name: 'Metro Garden Hotel',
  city: 'New York',
  state: 'NY',
  trip_name: 'New York Museum Weekend',
  check_in: '2026-09-25',
  check_out: '2026-09-27',
  nights: 2,
  stay_price_usd: '400.00',
  nightly_rate_usd: '200.00',
}

function renderCard(props) {
  return renderToString(createSSRApp(StayCard, props))
}

test('responsive card retains API dates and distinguishes the total from the nightly price', async () => {
  const html = await renderCard({ stay })
  assert.match(html, /Metro Garden Hotel/)
  assert.match(html, /New York, NY/)
  assert.match(html, /Sep 25, 2026/)
  assert.match(html, /Sep 27, 2026/)
  assert.match(html, /\$400\.00<\/strong>/)
  assert.match(html, /stay total/)
  assert.match(html, /\$200\.00 per night/)
  assert.match(html, /2 nights away/)
})

test('card communicates placeholder imagery and an accessible selected state', async () => {
  const html = await renderCard({ stay, selected: true })
  assert.match(html, /aria-label="Photo placeholder for Metro Garden Hotel"/)
  assert.match(html, /aria-pressed="true"/)
  assert.match(html, /Selected/)
})

test('unselected single-night stays retain the choose action and singular night label', async () => {
  const html = await renderCard({ stay: { ...stay, nights: 1 } })
  assert.match(html, /aria-pressed="false"/)
  assert.match(html, /Choose stay/)
  assert.match(html, /1 night away/)
})
