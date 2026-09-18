export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function validationMessage(error) {
  const field = error?.loc?.at(-1)
  if (field === 'username') {
    if (error.type === 'missing' || error.type === 'string_too_short') {
      return 'Enter a username with at least 3 characters.'
    }
    if (error.type === 'string_too_long' || error.type === 'string_pattern_mismatch') {
      return 'Username must be 3–64 letters, digits, dots, underscores, or hyphens and start with a letter or digit.'
    }
  }
  if (field === 'display_name' && ['missing', 'string_too_short'].includes(error.type)) {
    return 'Enter a display name.'
  }
  return typeof error?.msg === 'string' ? error.msg.replace(/^Value error, /, '') : undefined
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
    const entryMessage = Array.isArray(body?.detail) ? validationMessage(body.detail[0]) : undefined
    const message = typeof body?.detail === 'string' ? body.detail
      : typeof entryMessage === 'string' ? entryMessage
        : 'The request failed.'
    throw new ApiError(message, response.status)
  }

  return body
}
