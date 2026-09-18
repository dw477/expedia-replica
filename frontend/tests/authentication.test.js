import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fetchCurrentUser, signIn, signOut } from '../src/api/authentication.js'
import { createBooking, fetchBookingHistory } from '../src/api/bookings.js'
import { ApiError, requestJson } from '../src/api/request.js'

const user = { user_id: 'U006', display_name: 'Demo Traveler 6' }

function mockResponse(t, body, status = 200) {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    return new Response(status === 204 ? null : JSON.stringify(body), { status })
  })
  return calls
}

test('sign-in sends unmodified passwords with cookie and CSRF support', async (t) => {
  const calls = mockResponse(t, user)
  assert.deepEqual(await signIn('traveler6', ' spaced password '), user)
  assert.equal(calls[0].url, '/api/auth/login')
  assert.deepEqual(JSON.parse(calls[0].options.body), { username: 'traveler6', password: ' spaced password ' })
  assert.equal(calls[0].options.credentials, 'same-origin')
  assert.equal(calls[0].options.headers.get('X-Requested-With'), 'XMLHttpRequest')
  assert.equal(calls[0].options.headers.get('Content-Type'), 'application/json')
})

test('session absence is distinct from server and network failures', async (t) => {
  mockResponse(t, { detail: 'Sign in to continue.' }, 401)
  assert.equal(await fetchCurrentUser(), null)
  t.mock.restoreAll()
  mockResponse(t, { detail: 'Storage unavailable.' }, 500)
  await assert.rejects(fetchCurrentUser(), { message: 'Storage unavailable.', status: 500 })
  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('offline') })
  await assert.rejects(fetchCurrentUser(), /server is unavailable/)
})

test('expired sessions preserve status for clearing private View state', async (t) => {
  mockResponse(t, { detail: 'Your session expired.' }, 401)
  await assert.rejects(fetchBookingHistory(), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 401)
    return true
  })
})

test('booking and history let the server determine the authenticated owner', async (t) => {
  const calls = mockResponse(t, { booking_id: 'B999', user_id: 'U006' })
  await createBooking('T001')
  assert.deepEqual(JSON.parse(calls[0].options.body), { trip_id: 'T001' })
  t.mock.restoreAll()
  const historyCalls = mockResponse(t, [])
  assert.deepEqual(await fetchBookingHistory(), [])
  assert.equal(historyCalls[0].url, '/api/bookings')
})

test('sign-out requests revocation and accepts an empty response', async (t) => {
  const calls = mockResponse(t, null, 204)
  assert.equal(await signOut(), null)
  assert.equal(calls[0].url, '/api/auth/logout')
  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.headers.get('X-Requested-With'), 'XMLHttpRequest')
})

test('malformed session responses fail explicitly', async (t) => {
  mockResponse(t, {})
  await assert.rejects(fetchCurrentUser(), /unexpected response/)
  t.mock.restoreAll()
  t.mock.method(globalThis, 'fetch', async () => new Response('not json', { status: 401 }))
  await assert.rejects(requestJson('/api/auth/me'), { status: 401 })
})

test('account creation sends exactly the agreed fields with cookie and CSRF support', async (t) => {
  const { createAccount } = await import('../src/api/authentication.js')
  const calls = mockResponse(t, user, 201)
  assert.deepEqual(await createAccount('newtraveler', 'New Traveler', 'Abcdef1!'), user)
  assert.equal(calls[0].url, '/api/auth/register')
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    username: 'newtraveler', display_name: 'New Traveler', password: 'Abcdef1!',
  })
  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.credentials, 'same-origin')
  assert.equal(calls[0].options.headers.get('X-Requested-With'), 'XMLHttpRequest')
})

test('registration preserves conflicts and displays validation messages', async (t) => {
  const { createAccount } = await import('../src/api/authentication.js')
  mockResponse(t, { detail: 'That username is already in use.' }, 409)
  await assert.rejects(createAccount('traveler6', 'Traveler', 'Abcdef1!'), { status: 409, message: 'That username is already in use.' })
  t.mock.restoreAll()
  mockResponse(t, { detail: [{ loc: ['body', 'password'], msg: 'Value error, Password must include an uppercase letter.' }] }, 422)
  await assert.rejects(createAccount('newtraveler', 'Traveler', 'abcdef1!'), { status: 422, message: 'Password must include an uppercase letter.' })
})

test('invalid account entries show clear field messages instead of schema errors', async (t) => {
  const { createAccount } = await import('../src/api/authentication.js')
  mockResponse(t, { detail: [{ loc: ['body', 'username'], type: 'string_pattern_mismatch', msg: 'String should match pattern' }] }, 422)
  await assert.rejects(createAccount('bad name', 'Traveler', 'Abcdef1!'), {
    status: 422, message: 'Username must be 3–64 letters, digits, dots, underscores, or hyphens and start with a letter or digit.',
  })
  t.mock.restoreAll()
  mockResponse(t, { detail: [{ loc: ['body', 'display_name'], type: 'string_too_short', msg: 'String should have at least 1 character' }] }, 422)
  await assert.rejects(createAccount('newtraveler', ' ', 'Abcdef1!'), { status: 422, message: 'Enter a display name.' })
})
