export async function requestJson(url, options = {}) {
  let response
  try {
    response = await fetch(url, options)
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
    throw new Error('The server returned an unexpected response.')
  }

  if (!response.ok) {
    const message = typeof body?.detail === 'string' ? body.detail : 'The request failed.'
    throw new Error(message)
  }

  return body
}
