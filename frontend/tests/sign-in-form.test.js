import { after, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

const server = await createServer({
  configFile: false, plugins: [vue()],
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom',
})
after(() => server.close())
const { default: SignInForm } = await server.ssrLoadModule('/src/components/SignInForm.vue')
const { default: App } = await server.ssrLoadModule('/src/App.vue')

function renderForm(props = {}) {
  return renderToString(createSSRApp(SignInForm, props))
}

test('sign-in fields have labels, required constraints, and password manager hints', async () => {
  const html = await renderForm()
  assert.match(html, /for="username"/)
  assert.match(html, /for="password"/)
  assert.match(html, /type="password"/)
  assert.match(html, /autocomplete="username"/)
  assert.match(html, /autocomplete="current-password"/)
  assert.equal((html.match(/ required/g) ?? []).length, 2)
})

test('sign-in errors are announced and associated with inputs', async () => {
  const html = await renderForm({ error: 'Invalid username or password.' })
  assert.match(html, /role="alert"/)
  assert.match(html, /aria-describedby="auth-error"/)
  assert.match(html, /aria-invalid="true"/)
  assert.match(html, /Invalid username or password\./)
})

test('session checking disables inputs and communicates progress', async () => {
  const html = await renderForm({ busy: true, checking: true })
  assert.match(html, /aria-busy="true"/)
  assert.match(html, /Checking session…/)
  assert.equal((html.match(/ disabled/g) ?? []).length, 3)
})

test('signed-out View requires sign-in for booking and removes the traveler picker', async () => {
  const html = await renderToString(createSSRApp(App))
  assert.match(html, /Sign in to book a stay/)
  assert.match(html, /Sign in to view your bookings/)
  assert.doesNotMatch(html, /id="traveler"/)
  assert.doesNotMatch(html, /Create booking/)
})
