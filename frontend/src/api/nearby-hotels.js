import { requestJson } from './request.js'

export async function fetchNearbyHotels(postcode) {
  const query = new URLSearchParams({ postcode })
  const hotels = await requestJson(`/api/zip-hotels?${query}`)
  if (!Array.isArray(hotels) || !hotels.every(isHotel)) {
    throw new Error('The nearby hotel search returned an unexpected response.')
  }
  return hotels
}

function isHotel(hotel) {
  return hotel &&
    typeof hotel.place_id === 'string' && hotel.place_id.trim() !== '' &&
    typeof hotel.name === 'string' && hotel.name.trim() !== '' &&
    (hotel.address === null || typeof hotel.address === 'string') &&
    Number.isFinite(hotel.latitude) && Math.abs(hotel.latitude) <= 90 &&
    Number.isFinite(hotel.longitude) && Math.abs(hotel.longitude) <= 180 &&
    Number.isInteger(hotel.distance_m) && hotel.distance_m >= 0 && hotel.distance_m <= 5000
}
