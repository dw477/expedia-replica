import { ApiError, requestJson } from './request.js'

function requireUser(user) {
  if (!user || typeof user.user_id !== 'string' || typeof user.display_name !== 'string') {
    throw new Error('Sign-in returned an unexpected response.')
  }
  return user
}

export async function signIn(username, password) {
  return requireUser(
    await requestJson('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),
  )
}

export async function fetchCurrentUser() {
  try {
    return requireUser(await requestJson('/api/auth/me'))
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

export function signOut() {
  return requestJson('/api/auth/logout', { method: 'POST' })
}
