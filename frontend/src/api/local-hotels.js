import { requestJson } from './request.js'

function isLocalHotel(hotel, postcode) {
  return hotel && typeof hotel.place_id === 'string' && hotel.place_id.trim() !== '' &&
    (hotel.name === null || typeof hotel.name === 'string') &&
    (hotel.address === null || typeof hotel.address === 'string') &&
    Number.isFinite(hotel.latitude) && Math.abs(hotel.latitude) <= 90 &&
    Number.isFinite(hotel.longitude) && Math.abs(hotel.longitude) <= 180 &&
    Number.isInteger(hotel.distance_m) && hotel.distance_m >= 0 && hotel.distance_m <= 5000 &&
    hotel.location?.postcode === postcode && /^[0-9]{5}$/.test(postcode) &&
    hotel.location.country_code === 'us' &&
    Number.isFinite(hotel.location.latitude) && Math.abs(hotel.location.latitude) <= 90 &&
    Number.isFinite(hotel.location.longitude) && Math.abs(hotel.location.longitude) <= 180 &&
    (hotel.location.locality === null || typeof hotel.location.locality === 'string') &&
    Array.isArray(hotel.demo_nights) && hotel.demo_nights.every((night) =>
      /^\d{4}-\d{2}-\d{2}$/.test(night.stay_date) &&
      typeof night.nightly_rate_usd === 'string' && /^\d+\.\d{2}$/.test(night.nightly_rate_usd) &&
      Number.isInteger(night.rooms_available) && night.rooms_available >= 0)
}

export async function fetchLocalHotels(postcode) {
  const hotels = await requestJson(`/api/local-hotels?${new URLSearchParams({ postcode })}`)
  if (!Array.isArray(hotels) || !hotels.every((hotel) => isLocalHotel(hotel, postcode))) {
    throw new Error('Saved hotels returned an unexpected response. Please try again.')
  }
  return hotels
}

export async function fetchSavedHotelIds() {
  const ids = await requestJson('/api/local-hotels/ids')
  if (!Array.isArray(ids) || !ids.every((id) => typeof id === 'string' && id.trim() !== '')) {
    throw new Error('Saved hotel status returned an unexpected response. Please try again.')
  }
  return ids
}

export async function saveLocalHotel(hotel, location) {
  const { place_id, name, address, latitude, longitude, distance_m } = hotel
  const saved = await requestJson('/api/local-hotels', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hotel: { place_id, name, address, latitude, longitude, distance_m }, location }),
  })
  if (!isLocalHotel(saved, location.postcode) || saved.place_id !== place_id) {
    throw new Error('The save returned an unexpected response. Look up this ZIP again to check saved status.')
  }
  return saved
}

export async function removeLocalHotel(placeId) {
  await requestJson('/api/local-hotels', {
    method: 'DELETE', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ place_id: placeId }),
  })
}
