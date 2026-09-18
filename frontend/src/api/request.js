export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function requestJson(url, options = {}) {
  let response
  try {
    const method = (options.method ?? 'GET').toUpperCase()
    const headers = new Headers(options.headers)
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      headers.set('X-Requested-With', 'XMLHttpRequest')
    }
    response = await fetch(url, { ...options, credentials: 'same-origin', headers })
  } catch {
    throw new Error('The server is unavailable. Please try again.')
  }

  if (response.status === 204) {
    return null
  }

  let body
  try {
    body = await response.json()
  } catch {
    throw new ApiError('The server returned an unexpected response.', response.status)
  }

  if (!response.ok) {
    const message = typeof body?.detail === 'string' ? body.detail : 'The request failed.'
    throw new ApiError(message, response.status)
  }

  return body
}
