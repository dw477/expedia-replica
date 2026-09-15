<script setup>
import { onMounted, ref } from 'vue'

import {
  createBooking,
  deleteBooking,
  fetchBookingHistory,
  fetchUsers,
  updateBookingStatus,
} from './api/bookings.js'
import { searchAvailableStays } from './api/stays.js'

const hotelName = ref('')
const searchError = ref('')
const hasSearched = ref(false)
const isSearchLoading = ref(false)
const stays = ref([])

const users = ref([])
const selectedUserId = ref('')
const selectedTripId = ref('')
const bookings = ref([])
const bookingError = ref('')
const bookingNotice = ref('')
const historyError = ref('')
const isBookingSaving = ref(false)
const isHistoryLoading = ref(false)
const mutatingBookingId = ref('')

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function formatCurrency(value) {
  return currencyFormatter.format(Number(value))
}

function selectedUserName() {
  return users.value.find((user) => user.user_id === selectedUserId.value)?.display_name ?? ''
}

async function submitSearch() {
  const searchHotelName = hotelName.value.trim()
  searchError.value = ''

  if (!searchHotelName) {
    stays.value = []
    hasSearched.value = false
    selectedTripId.value = ''
    searchError.value = 'Enter a hotel name before searching.'
    return
  }

  isSearchLoading.value = true
  try {
    stays.value = await searchAvailableStays(searchHotelName)
    hasSearched.value = true
    if (!stays.value.some((stay) => stay.trip_id === selectedTripId.value)) {
      selectedTripId.value = ''
    }
  } catch (requestError) {
    stays.value = []
    hasSearched.value = false
    selectedTripId.value = ''
    searchError.value = requestError instanceof Error ? requestError.message : 'Search failed.'
  } finally {
    isSearchLoading.value = false
  }
}

function chooseStay(stay) {
  selectedTripId.value = stay.trip_id
  bookingError.value = ''
  bookingNotice.value = `${stay.trip_name} selected. Complete the booking form below.`
  document.querySelector('#booking-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function loadUsers() {
  bookingError.value = ''
  try {
    users.value = await fetchUsers()
    if (users.value.length && !selectedUserId.value) {
      selectedUserId.value = users.value[0].user_id
      await loadBookingHistory()
    }
  } catch (requestError) {
    bookingError.value =
      requestError instanceof Error ? requestError.message : 'Travelers failed to load.'
  }
}

async function loadBookingHistory() {
  const requestedUserId = selectedUserId.value
  historyError.value = ''
  bookings.value = []
  if (!requestedUserId) return

  isHistoryLoading.value = true
  try {
    const history = await fetchBookingHistory(requestedUserId)
    if (requestedUserId === selectedUserId.value) {
      bookings.value = history
    }
  } catch (requestError) {
    historyError.value =
      requestError instanceof Error ? requestError.message : 'Booking history failed to load.'
  } finally {
    isHistoryLoading.value = false
  }
}

async function submitBooking() {
  bookingError.value = ''
  bookingNotice.value = ''
  if (!selectedUserId.value || !selectedTripId.value) {
    bookingError.value = 'Choose a traveler and a stay before booking.'
    return
  }

  isBookingSaving.value = true
  try {
    const booking = await createBooking(selectedUserId.value, selectedTripId.value)
    bookingNotice.value = `Booking ${booking.booking_id} was created.`
    selectedTripId.value = ''
    await loadBookingHistory()
  } catch (requestError) {
    bookingError.value = requestError instanceof Error ? requestError.message : 'Booking failed.'
  } finally {
    isBookingSaving.value = false
  }
}

async function cancelBooking(bookingId) {
  bookingError.value = ''
  bookingNotice.value = ''
  mutatingBookingId.value = bookingId
  try {
    await updateBookingStatus(bookingId, 'cancelled')
    bookingNotice.value = `Booking ${bookingId} was cancelled.`
    await loadBookingHistory()
  } catch (requestError) {
    bookingError.value =
      requestError instanceof Error ? requestError.message : 'Cancellation failed.'
  } finally {
    mutatingBookingId.value = ''
  }
}

async function removeBooking(bookingId) {
  const shouldDelete = window.confirm(
    `Delete booking ${bookingId}? This removes it permanently from the traveler's history.`,
  )
  if (!shouldDelete) return

  bookingError.value = ''
  bookingNotice.value = ''
  mutatingBookingId.value = bookingId
  try {
    await deleteBooking(bookingId)
    bookingNotice.value = `Booking ${bookingId} was deleted.`
    await loadBookingHistory()
  } catch (requestError) {
    bookingError.value = requestError instanceof Error ? requestError.message : 'Deletion failed.'
  } finally {
    mutatingBookingId.value = ''
  }
}

onMounted(loadUsers)
</script>

<template>
  <main class="page-shell">
    <header class="hero" aria-labelledby="page-title">
      <p class="eyebrow">Expedia Lite</p>
      <h1 id="page-title">Search, book, and manage a stay</h1>
      <p class="intro">Explore the travel offers stored in SQLite and manage demo bookings.</p>
    </header>

    <section class="card search-card" aria-labelledby="search-title">
      <div class="section-heading">
        <div>
          <p class="step-label">Step 1</p>
          <h2 id="search-title">Find a hotel stay</h2>
        </div>
      </div>

      <form class="search-form" @submit.prevent="submitSearch">
        <label for="hotel-name">Hotel name</label>
        <div class="search-controls">
          <input
            id="hotel-name"
            v-model="hotelName"
            name="hotel-name"
            type="search"
            placeholder="Try Harbor Lantern"
          />
          <button class="primary-button" type="submit" :disabled="isSearchLoading">
            {{ isSearchLoading ? 'Searching…' : 'Search' }}
          </button>
        </div>
      </form>

      <div class="message error-message" role="alert" aria-live="assertive">
        <p v-if="searchError">{{ searchError }}</p>
      </div>

      <div class="results-heading">
        <h3>Available stays</h3>
        <span v-if="hasSearched">{{ stays.length }} result{{ stays.length === 1 ? '' : 's' }}</span>
      </div>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Hotel</th>
              <th scope="col">Trip</th>
              <th scope="col">Dates</th>
              <th scope="col">Stay price</th>
              <th scope="col"><span class="visually-hidden">Booking action</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="stay in stays" :key="stay.trip_id">
              <td>
                <strong>{{ stay.hotel_name }}</strong>
                <span>{{ stay.city }}, {{ stay.state }}</span>
              </td>
              <td>
                {{ stay.trip_name }}
                <span>{{ stay.nights }} night{{ stay.nights === 1 ? '' : 's' }}</span>
              </td>
              <td>{{ stay.check_in }}–{{ stay.check_out }}</td>
              <td>
                <strong>{{ formatCurrency(stay.stay_price_usd) }}</strong>
                <span>{{ formatCurrency(stay.nightly_rate_usd) }} nightly</span>
              </td>
              <td class="action-cell">
                <button
                  class="secondary-button"
                  type="button"
                  :aria-pressed="selectedTripId === stay.trip_id"
                  @click="chooseStay(stay)"
                >
                  {{ selectedTripId === stay.trip_id ? 'Selected' : 'Book stay' }}
                </button>
              </td>
            </tr>
            <tr v-if="!stays.length">
              <td class="empty-result" colspan="5">
                {{
                  hasSearched
                    ? 'No available stays match that hotel name.'
                    : 'Search for a hotel name to see available stays.'
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="card booking-card" aria-labelledby="booking-title">
      <div class="section-heading">
        <div>
          <p class="step-label">Step 2</p>
          <h2 id="booking-title">Create a booking</h2>
        </div>
      </div>

      <form id="booking-form" class="booking-form" @submit.prevent="submitBooking">
        <div class="field">
          <label for="traveler">Traveler</label>
          <select
            id="traveler"
            v-model="selectedUserId"
            name="traveler"
            required
            :disabled="!users.length"
            @change="loadBookingHistory"
          >
            <option value="" disabled>Choose a traveler</option>
            <option v-for="user in users" :key="user.user_id" :value="user.user_id">
              {{ user.display_name }}
            </option>
          </select>
        </div>

        <div class="field">
          <label for="selected-stay">Stay</label>
          <select id="selected-stay" v-model="selectedTripId" name="selected-stay" required>
            <option value="" disabled>Search and choose a stay</option>
            <option v-for="stay in stays" :key="stay.trip_id" :value="stay.trip_id">
              {{ stay.hotel_name }} · {{ stay.check_in }} to {{ stay.check_out }}
            </option>
          </select>
        </div>

        <button
          class="primary-button booking-submit"
          type="submit"
          :disabled="isBookingSaving || !users.length"
        >
          {{ isBookingSaving ? 'Creating…' : 'Create booking' }}
        </button>
      </form>

      <div class="message-stack" aria-live="polite">
        <p v-if="bookingError" class="message-text error-text" role="alert">{{ bookingError }}</p>
        <p v-if="bookingNotice" class="message-text success-text">{{ bookingNotice }}</p>
      </div>
    </section>

    <section class="card history-card" aria-labelledby="history-title" aria-live="polite">
      <div class="section-heading history-heading">
        <div>
          <p class="step-label">Step 3</p>
          <h2 id="history-title">Booking history</h2>
        </div>
        <span v-if="selectedUserId">{{ selectedUserName() }}</span>
      </div>

      <p v-if="isHistoryLoading" class="loading-message">Loading booking history…</p>
      <p v-else-if="historyError" class="message-text error-text" role="alert">
        {{ historyError }}
      </p>

      <div v-else class="booking-list">
        <article v-for="booking in bookings" :key="booking.booking_id" class="booking-item">
          <div class="booking-summary">
            <div>
              <div class="booking-id-row">
                <strong>{{ booking.hotel_name }}</strong>
                <span class="status-pill" :class="`status-${booking.status}`">
                  {{ booking.status }}
                </span>
              </div>
              <p>{{ booking.trip_name }} · {{ booking.city }}, {{ booking.state }}</p>
              <p>{{ booking.check_in }}–{{ booking.check_out }} · {{ booking.nights }} nights</p>
            </div>
            <div class="booking-price">
              <strong>{{ formatCurrency(booking.stay_price_usd) }}</strong>
              <span>Booked {{ booking.booked_on }}</span>
              <span>{{ booking.booking_id }}</span>
            </div>
          </div>
          <div class="booking-actions">
            <button
              v-if="booking.status === 'confirmed'"
              class="secondary-button"
              type="button"
              :disabled="mutatingBookingId === booking.booking_id"
              @click="cancelBooking(booking.booking_id)"
            >
              Cancel booking
            </button>
            <button
              class="danger-button"
              type="button"
              :disabled="mutatingBookingId === booking.booking_id"
              @click="removeBooking(booking.booking_id)"
            >
              Delete
            </button>
          </div>
        </article>

        <p v-if="!bookings.length" class="empty-history">
          {{
            selectedUserId
              ? 'This traveler has no bookings.'
              : 'Choose a traveler to view history.'
          }}
        </p>
      </div>
    </section>
  </main>
</template>
