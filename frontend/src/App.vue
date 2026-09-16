<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'

import {
  createBooking,
  deleteBooking,
  fetchBookingHistory,
  fetchUsers,
  updateBookingStatus,
} from './api/bookings.js'
import { searchAvailableStays } from './api/stays.js'

import StayCard from './components/StayCard.vue'
import { sortStays } from './utils/stays.js'

const hotelName = ref('')
const priceOrder = ref('recommended')
const searchError = ref('')
const hasSearched = ref(false)
const isSearchLoading = ref(false)
const stays = ref([])
const visibleStays = computed(() => sortStays(stays.value, priceOrder.value))

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

async function chooseStay(stay) {
  selectedTripId.value = stay.trip_id
  bookingError.value = ''
  bookingNotice.value = `${stay.trip_name} selected. Complete the booking form below.`
  await nextTick()
  const bookingForm = document.querySelector('#booking-form')
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  bookingForm?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' })
  document.querySelector('#selected-stay')?.focus({ preventScroll: true })
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

function searchHotel(name) {
  hotelName.value = name
  submitSearch()
}

function focusSearch() {
  document.querySelector('#hotel-name')?.focus()
}

onMounted(loadUsers)
</script>

<template>
  <main class="page-shell">
    <header class="hero" aria-labelledby="page-title">
      <p class="eyebrow">Expedia Lite</p>
      <h1 id="page-title">Find your next<br />hotel stay.</h1>
      <p class="intro">A little getaway. A great place to stay.</p>
    </header>

    <div class="phone-frame">
      <div class="phone-screen">
        <header class="app-header">
          <button
            class="back-button"
            type="button"
            aria-label="Go to hotel search"
            @click="focusSearch"
          >
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="m15 4-8 8 8 8" />
            </svg>
          </button>
          <div>
            <h2>Choose stay</h2>
            <p>Find a hotel. Make it a getaway.</p>
          </div>
          <a class="trips-link" href="#history-title" aria-label="Go to booking history">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect x="4" y="7" width="16" height="14" rx="3" />
              <path d="M9 7V5a3 3 0 0 1 6 0v2M9 11v6m6-6v6" />
            </svg>
          </a>
        </header>

        <section class="search-section" aria-labelledby="search-title">
          <h2 id="search-title" class="visually-hidden">Find a hotel stay</h2>
          <form class="search-form" @submit.prevent="submitSearch">
            <label for="hotel-name">Hotel name</label>
            <div class="search-controls">
              <input
                id="hotel-name"
                v-model="hotelName"
                name="hotel-name"
                type="search"
                placeholder="Try Harbor Lantern"
                :aria-invalid="Boolean(searchError)"
                :aria-describedby="searchError ? 'search-error' : undefined"
              />
              <button class="primary-button" type="submit" :disabled="isSearchLoading">
                {{ isSearchLoading ? 'Searching…' : 'Search' }}
              </button>
            </div>
          </form>
          <p v-if="searchError" id="search-error" class="message-text error-text" role="alert">
            {{ searchError }}
          </p>
          <div class="filter-row">
            <label class="sort-control" for="price-order">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M4 7h16M4 17h16" />
                <circle cx="9" cy="7" r="3" />
                <circle cx="15" cy="17" r="3" />
              </svg>
              <select id="price-order" v-model="priceOrder" aria-label="Sort stays by price">
                <option value="recommended">Original order</option>
                <option value="low">Price: low to high</option>
                <option value="high">Price: high to low</option>
              </select>
            </label>
            <span class="filter-note">Hotel stays</span>
          </div>
        </section>

        <section class="stays-section" aria-labelledby="results-title" :aria-busy="isSearchLoading">
          <div class="results-heading">
            <h2 id="results-title">
              {{ hasSearched ? 'Available stays' : 'Your getaway starts here' }}
            </h2>
            <span v-if="hasSearched" role="status"
              >{{ stays.length }} result{{ stays.length === 1 ? '' : 's' }}</span
            >
          </div>
          <p v-if="isSearchLoading" class="loading-message" role="status">Finding your stays…</p>
          <div v-else-if="hasSearched && stays.length" class="stay-list">
            <StayCard
              v-for="stay in visibleStays"
              :key="stay.trip_id"
              :stay="stay"
              :selected="selectedTripId === stay.trip_id"
              @choose="chooseStay(stay)"
            />
          </div>
          <div v-else class="empty-search">
            <div class="empty-illustration" aria-hidden="true">
              <svg viewBox="0 0 80 80" fill="none">
                <path
                  d="M18 63V24h44v39M12 63h56M30 63V49h20v14M27 34h5m16 0h5M27 42h5m16 0h5M34 24v-8h12v8"
                />
              </svg>
            </div>
            <h3>{{ hasSearched ? 'No stays found' : 'Somewhere new is calling.' }}</h3>
            <p>
              {{
                hasSearched
                  ? 'Try another hotel name to find an available stay.'
                  : 'Search by hotel name to explore available dates and prices.'
              }}
            </p>
            <div class="search-suggestions" aria-label="Hotel search shortcuts">
              <button type="button" @click="searchHotel('Harbor Lantern')">
                Harbor Lantern <span aria-hidden="true">↗</span>
              </button>
              <button type="button" @click="searchHotel('Maple Square')">
                Maple Square <span aria-hidden="true">↗</span>
              </button>
            </div>
          </div>
        </section>

        <section class="booking-section" aria-labelledby="booking-title">
          <div class="section-heading">
            <p class="step-label">Make it yours</p>
            <h2 id="booking-title">Book your stay</h2>
            <p>Choose your traveler and preferred dates.</p>
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
              <label for="selected-stay">Stay &amp; dates</label>
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
              <span aria-hidden="true">→</span>
            </button>
          </form>
          <div class="message-stack" aria-live="polite">
            <p v-if="bookingError" class="message-text error-text" role="alert">
              {{ bookingError }}
            </p>
            <p v-if="bookingNotice" class="message-text success-text">{{ bookingNotice }}</p>
          </div>
        </section>

        <section class="history-section" aria-labelledby="history-title" aria-live="polite">
          <div class="section-heading history-heading">
            <p class="step-label">Your travel plans</p>
            <h2 id="history-title" tabindex="-1">My bookings</h2>
            <p v-if="selectedUserId">{{ selectedUserName() }}</p>
          </div>
          <p v-if="isHistoryLoading" class="loading-message">Loading booking history…</p>
          <p v-else-if="historyError" class="message-text error-text" role="alert">
            {{ historyError }}
          </p>
          <div v-else class="booking-list">
            <article v-for="booking in bookings" :key="booking.booking_id" class="booking-item">
              <div class="booking-id-row">
                <span class="status-pill" :class="`status-${booking.status}`">{{
                  booking.status
                }}</span>
                <span class="booking-reference">{{ booking.booking_id }}</span>
              </div>
              <h3>{{ booking.hotel_name }}</h3>
              <p>{{ booking.trip_name }} · {{ booking.city }}, {{ booking.state }}</p>
              <p>{{ booking.check_in }}–{{ booking.check_out }} · {{ booking.nights }} nights</p>
              <div class="booking-price">
                <strong>{{ formatCurrency(booking.stay_price_usd) }}</strong>
                <span>Booked {{ booking.booked_on }}</span>
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
                  ? 'This traveler has no bookings yet.'
                  : 'Choose a traveler to view history.'
              }}
            </p>
          </div>
        </section>
        <footer class="app-footer">
          A stay to look forward to. <span aria-hidden="true">✦</span>
        </footer>
      </div>
    </div>
  </main>
</template>
