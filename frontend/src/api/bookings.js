import { requestJson } from './request.js'

const bookingsEndpoint = '/api/bookings'

export async function fetchUsers() {
  const users = await requestJson('/api/users')
  if (!Array.isArray(users)) {
    throw new Error('The traveler list returned an unexpected response.')
  }
  return users
}

export async function fetchBookingHistory() {
  const bookings = await requestJson(bookingsEndpoint)
  if (!Array.isArray(bookings)) {
    throw new Error('Booking history returned an unexpected response.')
  }
  return bookings
}

export function createBooking(tripId) {
  return requestJson(bookingsEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trip_id: tripId }),
  })
}

export function updateBookingStatus(bookingId, status) {
  return requestJson(`${bookingsEndpoint}/${encodeURIComponent(bookingId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export function deleteBooking(bookingId) {
  return requestJson(`${bookingsEndpoint}/${encodeURIComponent(bookingId)}`, {
    method: 'DELETE',
  })
}
