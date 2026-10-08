import { after, test } from 'node:test'
import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { createRenderer, createSSRApp, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'

import { sendChat } from '../src/api/chat.js'
import { ApiError } from '../src/api/request.js'

const server = await createServer({
  configFile: false, plugins: [vue()],
  optimizeDeps: { noDiscovery: true, include: [] },
  server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom',
})
after(() => server.close())
const { default: ChatAssistant } = await server.ssrLoadModule('/src/components/ChatAssistant.vue')
const renderer = createRenderer({
  createComment: () => ({}),
  insert() {}, remove() {}, parentNode: () => null, nextSibling: () => null,
})

function mount(t, { open = true } = {}) {
  const app = renderer.createApp({ ...ChatAssistant, render: () => null })
  app.provide(ssrContextKey, {})
  const state = app.mount({}).$.setupState
  state.isOpen = open
  t.after(() => app.unmount())
  return state
}

function render(state) {
  return renderToString(createSSRApp({ ...ChatAssistant, setup: () => state }))
}

test('chat is accessible and does not contact the LLM on mount', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('No automatic chat request'))
  const state = mount(t, { open: false })
  const closed = await render(state)
  assert.match(closed, /aria-expanded="false" aria-label="Open travel assistant"/)
  assert.doesNotMatch(closed, /role="dialog"/)
  await state.openChat()
  const html = await render(state)
  assert.equal(fetch.mock.callCount(), 0)
  assert.match(html, /aria-expanded="true" aria-label="Close travel assistant"/)
  assert.match(html, /role="dialog" aria-labelledby="chat-title"/)
  assert.match(html, /aria-label="Close chat popup"/)
  assert.match(html, /Your travel assistant/)
  assert.match(html, /role="log" aria-label="Travel assistant conversation" aria-live="polite"/)
  assert.match(html, /<label for="chat-message"[^>]*>Your message<\/label>/)
  assert.match(html, /<textarea[^>]*maxlength="8000"/)
  assert.doesNotMatch(html, /chat-help|chat-keyboard-help|Enter to send|Messages are saved by the server/)
  assert.match(html, /<button[^>]*type="submit"[^>]*disabled/)
})

test('popup restores focus to its opener and preserves its draft and conversation', async (t) => {
  const state = mount(t, { open: false })
  const focusOpener = t.mock.fn()
  const focusComposer = t.mock.fn()
  state.composer = { focus: focusComposer }
  state.messages = [{ role: 'user', content: 'Boston trip' }, { role: 'assistant', content: 'Visit a museum.' }]
  state.draft = 'Rainy day ideas?'
  await state.openChat({ currentTarget: { focus: focusOpener } })
  assert.equal(focusComposer.mock.callCount(), 1)
  state.closeChat()
  assert.equal(state.isOpen, false)
  assert.equal(focusOpener.mock.callCount(), 1)
  await state.openChat()
  assert.equal(state.draft, 'Rainy day ideas?')
  assert.equal(state.messages.length, 2)
  assert.match(await render(state), /Visit a museum/)
})

test('closing during a request retains the reply without stealing focus', async (t) => {
  let finish
  t.mock.method(globalThis, 'fetch', () => new Promise((resolve) => { finish = resolve }))
  const state = mount(t)
  const focusComposer = t.mock.fn()
  state.composer = { focus: focusComposer }
  state.draft = 'Boston trip'
  const pending = state.submitMessage()
  await setImmediate()
  state.closeChat()
  assert.equal(state.isOpen, false)
  finish(Response.json({ suggestions: [], reply: 'Visit a museum.' }))
  await pending
  assert.equal(state.messages.length, 2)
  assert.equal(focusComposer.mock.callCount(), 0)
  await state.openChat()
  assert.match(await render(state), /Visit a museum/)
})

test('reopening while busy focuses the popup instead of the disabled composer', async (t) => {
  const state = mount(t, { open: false })
  const focusPopup = t.mock.fn()
  const focusComposer = t.mock.fn()
  state.popup = { focus: focusPopup }
  state.composer = { focus: focusComposer }
  state.isLoading = true
  await state.openChat()
  assert.equal(state.isOpen, true)
  assert.equal(focusPopup.mock.callCount(), 1)
  assert.equal(focusComposer.mock.callCount(), 0)
})

test('adapter sends only bounded message context with cookies and CSRF header', async (t) => {
  let sent
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/chat')
    assert.equal(options.method, 'POST')
    assert.equal(options.credentials, 'same-origin')
    assert.equal(options.headers.get('X-Requested-With'), 'XMLHttpRequest')
    assert.equal(options.headers.get('Content-Type'), 'application/json')
    sent = JSON.parse(options.body)
    return Response.json({ suggestions: [], reply: '  Take a weekend trip.  ' })
  })
  const messages = Array.from({ length: 25 }, (_, index) => ({
    role: index % 2 === 0 ? 'user' : 'assistant', content: `Message ${index}`, privateField: 'exclude',
  }))
  assert.deepEqual(await sendChat(messages), { reply: 'Take a weekend trip.', suggestions: [] })
  assert.equal(sent.messages.length, 21)
  assert.deepEqual(sent.messages[0], { role: 'user', content: 'Message 4' })
  assert.equal(sent.messages.at(-1).content, 'Message 24')
  assert.equal(messages.length, 25)
})

test('adapter drops complete oldest exchanges to respect total context size', async (t) => {
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    const { messages } = JSON.parse(options.body)
    assert.equal(messages.length, 3)
    assert.deepEqual(messages.map(({ role }) => role), ['user', 'assistant', 'user'])
    assert.equal(messages[0].content.at(0), '2')
    return Response.json({ suggestions: [], reply: 'Hi' })
  })
  await sendChat(Array.from({ length: 5 }, (_, index) => ({
    role: index % 2 === 0 ? 'user' : 'assistant', content: String(index).repeat(8000),
  })))
})

test('submit shows the pending user message and prevents duplicate requests and reset', async (t) => {
  let finish
  const fetch = t.mock.method(globalThis, 'fetch', () => new Promise((resolve) => { finish = resolve }))
  const state = mount(t)
  state.draft = '  Plan a weekend in Boston  '
  const pending = state.submitMessage()
  await setImmediate()
  assert.equal(state.isLoading, true)
  assert.equal(state.draft, '')
  assert.deepEqual(state.messages, [{ role: 'user', content: 'Plan a weekend in Boston' }])
  const html = await render(state)
  assert.match(html, /aria-busy="true"/)
  assert.match(html, /<textarea[^>]*disabled/)
  assert.match(html, /role="status"[^>]*>Travel assistant is thinking/)
  assert.match(html, /<button[^>]*disabled[^>]*>New chat/)
  await state.submitMessage()
  state.startNewChat()
  state.useSuggestion('Another request')
  assert.equal(fetch.mock.callCount(), 1)
  finish(Response.json({ suggestions: [], reply: 'Visit the waterfront.' }))
  await pending
  assert.equal(state.isLoading, false)
  assert.equal(state.messages.at(-1).content, 'Visit the waterfront.')
  assert.match(await render(state), /Travel assistant<\/span>/)
})

test('follow-up includes previous answers and messages are rendered as escaped text', async (t) => {
  const bodies = []
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    bodies.push(JSON.parse(options.body))
    return Response.json({ suggestions: [], reply: '<script>alert(1)</script>\nTry a museum.' })
  })
  const state = mount(t)
  state.draft = 'Boston for a weekend'
  await state.submitMessage()
  state.draft = 'What about a rainy day?'
  await state.submitMessage()
  assert.deepEqual(bodies[1].messages, [
    { role: 'user', content: 'Boston for a weekend' },
    { role: 'assistant', content: '<script>alert(1)</script>\nTry a museum.' },
    { role: 'user', content: 'What about a rainy day?' },
  ])
  assert.match(bodies[0].conversation_id, /^[0-9a-f-]{36}$/)
  assert.equal(bodies[1].conversation_id, bodies[0].conversation_id)
  const html = await render(state)
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/)
  assert.doesNotMatch(html, /<script>/)
})

test('failure keeps successful history and restores the failed draft for retry', async (t) => {
  let count = 0
  const identifiers = []
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    identifiers.push(JSON.parse(options.body).conversation_id)
    count += 1
    return count === 2
      ? Response.json({ detail: 'The travel assistant could not reply. Please try again.' }, { status: 502 })
      : Response.json({ suggestions: [], reply: 'Visit a museum.' })
  })
  const state = mount(t)
  state.draft = 'Boston trip'
  await state.submitMessage()
  state.draft = 'Rainy day ideas?'
  await state.submitMessage()
  assert.equal(state.isLoading, false)
  assert.equal(state.messages.length, 2)
  assert.equal(state.draft, 'Rainy day ideas?')
  assert.match(await render(state), /role="alert"[^>]*>The travel assistant could not reply/)
  assert.match(await render(state), /Try again/)
  await state.submitMessage()
  assert.equal(state.messages.length, 4)
  assert.equal(state.error, '')
  assert.equal(new Set(identifiers).size, 1)
})

test('unavailable configuration and network errors are readable', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Configure GEMINI_API_KEY and restart the backend.' }, { status: 503 }))
  await assert.rejects(sendChat([{ role: 'user', content: 'Hello' }]), (error) => error instanceof ApiError && error.status === 503)
  fetch.mock.mockImplementation(async () => { throw new Error('raw transport details') })
  const state = mount(t)
  state.draft = 'Hello'
  await state.submitMessage()
  assert.equal(state.error, 'The server is unavailable. Please try again.')
  assert.equal(state.draft, 'Hello')
  assert.equal(state.messages.length, 0)
})

test('provider outages and timeouts show the backend explanation and preserve the draft', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({}))
  const state = mount(t)
  for (const detail of [
    'Gemini is temporarily unavailable. Please try again in a moment.',
    'Gemini took too long to reply. Please try again.',
  ]) {
    fetch.mock.mockImplementation(async () => Response.json({ detail }, { status: 502 }))
    state.draft = 'Help me plan a weekend getaway'
    await state.submitMessage()
    assert.equal(state.error, detail)
    assert.equal(state.draft, 'Help me plan a weekend getaway')
    assert.equal(state.messages.length, 0)
    assert.match(await render(state), /role="alert"[^>]*>Gemini/)
  }
})

test('malformed provider responses cannot enter the transcript', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({}))
  for (const body of [{}, { reply: null }, { reply: 123 }, { reply: '  ' }, { reply: 'a'.repeat(8001) }]) {
    fetch.mock.mockImplementation(async () => Response.json(body))
    await assert.rejects(sendChat([{ role: 'user', content: 'Hello' }]), /unexpected reply/)
  }
})

test('blank and oversized messages never reach the backend', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('Invalid input cannot be sent'))
  const state = mount(t)
  state.draft = '  \n'
  await state.submitMessage()
  assert.match(state.error, /non-empty|Enter a message/)
  state.draft = 'a'.repeat(8001)
  await state.submitMessage()
  assert.match(state.error, /8000 characters/)
  assert.equal(fetch.mock.callCount(), 0)
})

test('new chat clears the conversation, draft and error without a provider request', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('Reset is local'))
  const state = mount(t)
  state.messages = [{ role: 'user', content: 'Hello' }, { role: 'assistant', content: 'Hi' }]
  state.draft = 'Next question'
  state.error = 'Earlier error'
  const previousId = state.conversationId
  state.startNewChat()
  assert.notEqual(state.conversationId, previousId)
  assert.deepEqual(state.messages, [])
  assert.equal(state.draft, '')
  assert.equal(state.error, '')
  assert.equal(fetch.mock.callCount(), 0)
})

test('removed help and footer leave no stale accessibility references', async (t) => {
  const state = mount(t)
  const html = await render(state)
  assert.doesNotMatch(html, /chat-help|chat-keyboard-help|simulated classroom data|Messages are saved by the server/)
  assert.match(html, /Which saved hotels in ZIP 02108/)
})

test('Shift Enter and composition preserve text while Enter sends through the adapter', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ suggestions: [], reply: 'Hi' }))
  const state = mount(t)
  state.draft = 'Hello'
  const preventDefault = t.mock.fn()
  state.handleEnter({ shiftKey: true, preventDefault })
  state.handleEnter({ isComposing: true, preventDefault })
  assert.equal(preventDefault.mock.callCount(), 0)
  assert.equal(fetch.mock.callCount(), 0)
  state.handleEnter({ preventDefault })
  await setImmediate()
  assert.equal(preventDefault.mock.callCount(), 1)
  assert.equal(fetch.mock.callCount(), 1)
  assert.equal(state.messages.length, 2)
})

test('suggestions refresh from the latest answer and clicking sends a normal follow-up', async (t) => {
  const bodies = []
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    bodies.push(JSON.parse(options.body))
    return bodies.length === 1
      ? Response.json({ reply: 'Cheap has rooms in ZIP 02108.', suggestions: ['Compare Cheap and Costly in ZIP 02108', 'What about two rooms?'] })
      : Response.json({ reply: 'Here is the comparison.', suggestions: ['Which is cheapest for October 10–12?'] })
  })
  const state = mount(t)
  state.draft = 'Which hotels have rooms in ZIP 02108?'
  await state.submitMessage()
  assert.deepEqual(state.suggestions, ['Compare Cheap and Costly in ZIP 02108', 'What about two rooms?'])
  const first = await render(state)
  assert.match(first, /Keep exploring/)
  assert.match(first, /Compare Cheap and Costly in ZIP 02108/)
  assert.doesNotMatch(first, /Show the cheapest saved hotels for/)
  state.useSuggestion(state.suggestions[0])
  await setImmediate()
  assert.equal(bodies[1].messages.at(-1).content, 'Compare Cheap and Costly in ZIP 02108')
  assert.deepEqual(state.suggestions, ['Which is cheapest for October 10–12?'])
  assert.equal(state.messages.length, 4)
  assert.doesNotMatch(await render(state), /What about two rooms/)
})

test('busy hides suggestions; failure and reopen preserve the last successful suggestions', async (t) => {
  let fail
  t.mock.method(globalThis, 'fetch', () => new Promise((resolve) => { fail = resolve }))
  const state = mount(t)
  state.messages = [{ role: 'user', content: 'ZIP 02108?' }, { role: 'assistant', content: 'Two saved hotels.' }]
  state.suggestions = ['Compare the two saved hotels']
  state.draft = 'What about October 11?'
  const pending = state.submitMessage()
  await setImmediate()
  assert.doesNotMatch(await render(state), /aria-label="Suggested questions"/)
  fail(Response.json({ detail: 'Try again later.' }, { status: 502 }))
  await pending
  assert.deepEqual(state.suggestions, ['Compare the two saved hotels'])
  state.closeChat()
  await state.openChat()
  assert.match(await render(state), /Compare the two saved hotels/)
  state.startNewChat()
  assert.match(await render(state), /Which saved hotels in ZIP 02108/)
  assert.doesNotMatch(await render(state), /Compare the two saved hotels/)
})

test('suggestions are validated at the boundary and rendered as escaped text', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({}))
  for (const suggestions of [undefined, null, 'question', [' '], [123], ['x'.repeat(161)], ['One', 'Two', 'Three', 'Four'], ['One', 'one']]) {
    fetch.mock.mockImplementation(async () => Response.json({ reply: 'Good reply', suggestions }))
    await assert.rejects(sendChat([{ role: 'user', content: 'Hello' }]), /unexpected suggestions/)
  }
  fetch.mock.mockImplementation(async () => Response.json({ reply: 'Good reply', suggestions: ['<img src=x onerror=alert(1)>?'] }))
  const state = mount(t)
  state.draft = 'ZIP 02108?'
  await state.submitMessage()
  const html = await render(state)
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/)
  assert.doesNotMatch(html, /<img src=x/)
})

test('an empty suggestion list clears previous actions without losing the reply', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ reply: 'Please specify a ZIP.', suggestions: [] }))
  const state = mount(t)
  state.draft = 'Hello'
  await state.submitMessage()
  assert.equal(state.messages.at(-1).content, 'Please specify a ZIP.')
  assert.deepEqual(state.suggestions, [])
  assert.doesNotMatch(await render(state), /aria-label="Suggested questions"/)
})
