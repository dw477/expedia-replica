<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'

import {
  createBooking,
  deleteBooking,
  fetchBookingHistory,
  updateBookingStatus,
} from './api/bookings.js'
import { searchAvailableStays } from './api/stays.js'

import StayCard from './components/StayCard.vue'
import SignInForm from './components/SignInForm.vue'
import CreateAccountForm from './components/CreateAccountForm.vue'
import { createAccount, fetchCurrentUser, signIn, signOut } from './api/authentication.js'
import { ApiError } from './api/request.js'
import { sortStays } from './utils/stays.js'

const hotelName = ref('')
const priceOrder = ref('recommended')
const searchError = ref('')
const hasSearched = ref(false)
const isSearchLoading = ref(false)
const stays = ref([])
let lastSearchHotelName = ''
let searchRevision = 0
const visibleStays = computed(() => sortStays(stays.value, priceOrder.value))

const currentUser = ref(null)
const authError = ref('')
const isCreatingAccount = ref(false)
const isAuthBusy = ref(true)
const isSessionChecking = ref(true)
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

function clearAccount() {
  searchRevision += 1
  stays.value = []
  hasSearched.value = false
  isSearchLoading.value = false
  lastSearchHotelName = ''
  currentUser.value = null
  bookings.value = []
  selectedTripId.value = ''
  bookingError.value = ''
  bookingNotice.value = ''
  historyError.value = ''
}

function handleAccountError(error, fallback) {
  if (error instanceof ApiError && error.status === 401) {
    clearAccount()
    authError.value = 'Your session ended. Sign in again to continue.'
  }
  return error instanceof Error ? error.message : fallback
}

async function restoreSession() {
  try {
    currentUser.value = await fetchCurrentUser()
    if (currentUser.value) await loadBookingHistory()
  } catch (error) {
    authError.value = error instanceof Error ? error.message : 'Your session could not be checked.'
  } finally {
    isAuthBusy.value = false
    isSessionChecking.value = false
  }
}

async function submitSignIn({ username, password }) {
  if (isAuthBusy.value) return
  authError.value = ''
  isAuthBusy.value = true
  try {
    currentUser.value = await signIn(username, password)
    await refreshSearchPrices()
    bookingError.value = ''
    bookingNotice.value = ''
    await loadBookingHistory()
  } catch (error) {
    authError.value = error instanceof Error ? error.message : 'Sign-in failed.'
  } finally {
    isAuthBusy.value = false
  }
}

async function switchAuthForm(create) {
  if (isAuthBusy.value) return
  isCreatingAccount.value = create
  authError.value = ''
  await nextTick()
  document.querySelector(create ? '#display-name' : '#username')?.focus()
}

async function submitCreateAccount({ username, displayName, password }) {
  if (isAuthBusy.value) return
  authError.value = ''
  isAuthBusy.value = true
  try {
    currentUser.value = await createAccount(username, displayName, password)
    await refreshSearchPrices()
    isCreatingAccount.value = false
    bookingError.value = ''
    bookingNotice.value = ''
    await loadBookingHistory()
  } catch (error) {
    authError.value = error instanceof Error ? error.message : 'Account creation failed.'
  } finally {
    isAuthBusy.value = false
  }
}

async function submitSignOut() {
  if (isAuthBusy.value) return
  authError.value = ''
  isAuthBusy.value = true
  try {
    await signOut()
    isAuthBusy.value = false
    clearAccount()
    await nextTick()
    document.querySelector('#username')?.focus()
  } catch (error) {
    authError.value = error instanceof Error ? error.message : 'Sign-out failed.'
  } finally {
    isAuthBusy.value = false
  }
}

async function submitSearch() {
  if (isSearchLoading.value || isAuthBusy.value) return
  const searchHotelName = hotelName.value.trim()
  searchError.value = ''

  if (!searchHotelName) {
    stays.value = []
    hasSearched.value = false
    selectedTripId.value = ''
    searchError.value = 'Enter a hotel name before searching.'
    return
  }

  lastSearchHotelName = searchHotelName
  await loadSearch(searchHotelName, true)
}

async function refreshSearchPrices() {
  if (lastSearchHotelName) await loadSearch(lastSearchHotelName, false)
}

async function loadSearch(searchHotelName, submitted) {
  const revision = ++searchRevision
  searchError.value = ''
  isSearchLoading.value = true
  try {
    const results = await searchAvailableStays(searchHotelName, { submitted })
    if (revision !== searchRevision) return
    stays.value = results
    hasSearched.value = true
    if (!stays.value.some((stay) => stay.trip_id === selectedTripId.value)) {
      selectedTripId.value = ''
    }
  } catch (requestError) {
    if (revision !== searchRevision) return
    stays.value = []
    hasSearched.value = false
    selectedTripId.value = ''
    searchError.value = handleAccountError(requestError, 'Search failed.')
  } finally {
    if (revision === searchRevision) isSearchLoading.value = false
  }
}

async function chooseStay(stay) {
  selectedTripId.value = stay.trip_id
  bookingError.value = ''
  bookingNotice.value = currentUser.value
    ? `${stay.trip_name} selected. Complete the booking form.`
    : `${stay.trip_name} selected. Sign in to book this stay.`
  await nextTick()
  const bookingForm = document.querySelector(currentUser.value ? '#booking-form' : isCreatingAccount.value ? '#create-account-form' : '#sign-in-form')
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  bookingForm?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' })
  document.querySelector(currentUser.value ? '#selected-stay' : isCreatingAccount.value ? '#display-name' : '#username')?.focus({ preventScroll: true })
}

async function loadBookingHistory() {
  const requestedUserId = currentUser.value?.user_id
  historyError.value = ''
  bookings.value = []
  if (!requestedUserId) return

  isHistoryLoading.value = true
  try {
    const history = await fetchBookingHistory()
    if (requestedUserId === currentUser.value?.user_id) {
      bookings.value = history
    }
  } catch (requestError) {
    if (requestedUserId === currentUser.value?.user_id) {
      historyError.value = handleAccountError(requestError, 'Booking history failed to load.')
    }
  } finally {
    isHistoryLoading.value = false
  }
}

async function submitBooking() {
  if (isBookingSaving.value || isAuthBusy.value || isSearchLoading.value) return
  bookingError.value = ''
  bookingNotice.value = ''
  if (!currentUser.value || !selectedTripId.value) {
    bookingError.value = 'Sign in and choose a stay before booking.'
    return
  }

  const requestedUserId = currentUser.value.user_id
  isBookingSaving.value = true
  try {
    const booking = await createBooking(selectedTripId.value)
    if (requestedUserId !== currentUser.value?.user_id) return
    bookingNotice.value = `Booking ${booking.booking_id} was created.`
    selectedTripId.value = ''
    await loadBookingHistory()
  } catch (requestError) {
    if (requestedUserId === currentUser.value?.user_id) {
      bookingError.value = handleAccountError(requestError, 'Booking failed.')
    }
  } finally {
    isBookingSaving.value = false
  }
}

async function cancelBooking(bookingId) {
  bookingError.value = ''
  bookingNotice.value = ''
  const requestedUserId = currentUser.value?.user_id
  mutatingBookingId.value = bookingId
  try {
    await updateBookingStatus(bookingId, 'cancelled')
    if (requestedUserId !== currentUser.value?.user_id) return
    bookingNotice.value = `Booking ${bookingId} was cancelled.`
    await loadBookingHistory()
  } catch (requestError) {
    if (requestedUserId === currentUser.value?.user_id) {
      bookingError.value = handleAccountError(requestError, 'Cancellation failed.')
    }
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
  const requestedUserId = currentUser.value?.user_id
  mutatingBookingId.value = bookingId
  try {
    await deleteBooking(bookingId)
    if (requestedUserId !== currentUser.value?.user_id) return
    bookingNotice.value = `Booking ${bookingId} was deleted.`
    await loadBookingHistory()
  } catch (requestError) {
    if (requestedUserId === currentUser.value?.user_id) {
      bookingError.value = handleAccountError(requestError, 'Deletion failed.')
    }
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

onMounted(restoreSession)
</script>

<template>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="#page-title" aria-label="Expedia Lite home">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <rect x="4" y="7" width="16" height="14" rx="3" />
            <path d="M9 7V5a3 3 0 0 1 6 0v2M9 11v6m6-6v6" />
          </svg>
        </span>
        Expedia <span class="brand-lite">Lite</span>
      </a>
      <nav class="site-nav" aria-label="Main navigation">
        <a href="#search-title" @click.prevent="focusSearch">Find a stay</a>
        <a href="#history-title">My bookings <span aria-hidden="true">↗</span></a>
        <template v-if="currentUser">
          <span class="account-name">{{ currentUser.display_name }}</span>
          <button class="secondary-button" type="button" :disabled="isAuthBusy" @click="submitSignOut">
            {{ isAuthBusy ? 'Please wait…' : 'Sign out' }}
          </button>
        </template>
        <a v-else href="#auth-title">Sign in</a>
      </nav>
    </div>
  </header>

  <main id="main-content" class="page-shell" tabindex="-1">
    <header class="hero" aria-labelledby="page-title">
      <p class="eyebrow"><span aria-hidden="true">✦</span> A little getaway starts here</p>
      <h1 id="page-title">Find your next<br /><span>hotel stay.</span></h1>
      <p class="intro">A great place to stay. Something to look forward to.</p>
    </header>

    <CreateAccountForm
      v-if="!currentUser && isCreatingAccount"
      :busy="isAuthBusy"
      :error="authError"
      @create-account="submitCreateAccount"
      @sign-in="switchAuthForm(false)"
    />
    <SignInForm
      v-else-if="!currentUser"
      :busy="isAuthBusy"
      :checking="isSessionChecking"
      :error="authError"
      @sign-in="submitSignIn"
      @create-account="switchAuthForm(true)"
    />
    <p v-else-if="authError" class="message-text error-text" role="alert">{{ authError }}</p>

    <section class="search-section" aria-labelledby="search-title">
      <h2 id="search-title" class="visually-hidden">Find a hotel stay</h2>
      <form class="search-form" @submit.prevent="submitSearch">
        <div class="search-field">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="10" cy="10" r="6" />
            <path d="m15 15 5 5" />
          </svg>
          <div>
            <label for="hotel-name">Where would you like to stay?</label>
            <input
              id="hotel-name"
              v-model="hotelName"
              name="hotel-name"
              type="search"
              aria-label="Hotel name"
              placeholder="Enter a hotel name, e.g. Harbor Lantern"
              :aria-invalid="Boolean(searchError)"
              :aria-describedby="searchError ? 'search-error' : 'search-help'"
            />
          </div>
        </div>
        <button class="primary-button search-submit" type="submit" :disabled="isSearchLoading || isAuthBusy">
          {{ isSearchLoading ? 'Searching…' : 'Search' }} <span aria-hidden="true">→</span>
        </button>
      </form>
      <p v-if="searchError" id="search-error" class="message-text error-text" role="alert">
        {{ searchError }}
      </p>
      <p id="search-help" class="search-help">
        Search by hotel name. Explore available dates and prices.
      </p>
    </section>

    <div class="stay-workspace">
      <section class="stays-section" aria-labelledby="results-title" :aria-busy="isSearchLoading">
        <div class="results-heading">
          <div>
            <p class="step-label">Find your place</p>
            <h2 id="results-title">
              {{ hasSearched ? 'Choose your stay' : 'Your getaway starts here' }}
            </h2>
            <span v-if="hasSearched" class="result-count" role="status"
              >{{ stays.length }} available stay{{ stays.length === 1 ? '' : 's' }}</span
            >
          </div>
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
          <p class="step-label">A change of scenery</p>
          <h3>{{ hasSearched ? 'No stays found' : 'Somewhere new is calling.' }}</h3>
          <p>
            {{
              hasSearched
                ? 'Try another hotel name to find an available stay.'
                : 'Find the right hotel, choose your dates, and make that little getaway happen.'
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
          <p class="step-label">Your next getaway</p>
          <h2 id="booking-title">Book your stay</h2>
          <p>Choose an available stay for your account.</p>
        </div>
        <form v-if="currentUser" id="booking-form" class="booking-form" @submit.prevent="submitBooking">
          <p class="booking-traveler">Booking for <strong>{{ currentUser.display_name }}</strong></p>
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
            :disabled="isBookingSaving || isAuthBusy || isSearchLoading"
          >
            {{ isBookingSaving ? 'Creating…' : 'Create booking' }}
            <span aria-hidden="true">→</span>
          </button>
        </form>
        <p v-else class="empty-history"><a href="#auth-title">Sign in</a> to create a booking.</p>
        <div class="message-stack" aria-live="polite">
          <p v-if="bookingError" class="message-text error-text" role="alert">
            {{ bookingError }}
          </p>
          <p v-if="bookingNotice" class="message-text success-text">{{ bookingNotice }}</p>
        </div>
      </section>
    </div>

    <section class="history-section" aria-labelledby="history-title" aria-live="polite">
      <div class="section-heading history-heading">
        <p class="step-label">Your travel plans</p>
        <h2 id="history-title" tabindex="-1">My bookings</h2>
        <p v-if="currentUser">{{ currentUser.display_name }}</p>
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
            currentUser
              ? 'You have no bookings yet.'
              : 'Sign in to view your bookings.'
          }}
        </p>
      </div>
    </section>

    <footer class="site-footer">
      <span class="footer-brand">Expedia Lite</span>
      <p>A stay to look forward to. <span aria-hidden="true">✦</span></p>
      <a href="#page-title">Back to top <span aria-hidden="true">↑</span></a>
    </footer>
  </main>
</template>
