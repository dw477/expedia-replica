const staysEndpoint = '/api/stays'

export async function searchAvailableStays(hotelName) {
  const query = new URLSearchParams({ hotel_name: hotelName })
  const response = await fetch(`${staysEndpoint}?${query}`)

  if (!response.ok) {
    throw new Error('The hotel search is unavailable. Please try again.')
  }

  const results = await response.json()
  if (!Array.isArray(results)) {
    throw new Error('The hotel search returned an unexpected response.')
  }

  return results
}
