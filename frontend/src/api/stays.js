import { requestJson } from './request.js'

const staysEndpoint = '/api/stays'

export async function searchAvailableStays(hotelName) {
  const query = new URLSearchParams({ hotel_name: hotelName })
  const results = await requestJson(`${staysEndpoint}?${query}`)
  if (!Array.isArray(results)) {
    throw new Error('The hotel search returned an unexpected response.')
  }

  return results
}
