import { requestJson } from './request.js'

const staysEndpoint = '/api/stays'

export async function searchAvailableStays(hotelName, { submitted = true } = {}) {
  const query = new URLSearchParams({ hotel_name: hotelName })
  const results = submitted
    ? await requestJson(staysEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hotel_name: hotelName }),
    })
    : await requestJson(`${staysEndpoint}?${query}`)
  if (!Array.isArray(results)) {
    throw new Error('The hotel search returned an unexpected response.')
  }

  return results
}
