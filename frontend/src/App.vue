<script setup>
import { ref } from 'vue'

import { searchAvailableStays } from './api/stays.js'

const hotelName = ref('')
const error = ref('')
const hasSearched = ref(false)
const isLoading = ref(false)
const stays = ref([])

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function formatCurrency(value) {
  return currencyFormatter.format(Number(value))
}

async function submitSearch() {
  const searchHotelName = hotelName.value.trim()
  error.value = ''

  if (!searchHotelName) {
    stays.value = []
    hasSearched.value = false
    error.value = 'Enter a hotel name before searching.'
    return
  }

  isLoading.value = true
  try {
    stays.value = await searchAvailableStays(searchHotelName)
    hasSearched.value = true
  } catch (requestError) {
    stays.value = []
    hasSearched.value = false
    error.value = requestError instanceof Error ? requestError.message : 'Search failed.'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <main class="page-shell">
    <section class="search-card" aria-labelledby="page-title">
      <p class="eyebrow">Expedia Lite</p>
      <h1 id="page-title">Find an available hotel stay</h1>
      <p class="intro">Search the supplied travel offers by hotel name.</p>

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
          <button type="submit" :disabled="isLoading">
            {{ isLoading ? 'Searching…' : 'Search' }}
          </button>
        </div>
      </form>

      <div class="error-area" role="alert" aria-live="assertive">
        <p v-if="error">{{ error }}</p>
      </div>
    </section>

    <section class="results-card" aria-labelledby="results-title" aria-live="polite">
      <div class="results-heading">
        <h2 id="results-title">Available stays</h2>
        <span v-if="hasSearched">{{ stays.length }} result{{ stays.length === 1 ? '' : 's' }}</span>
      </div>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Hotel</th>
              <th scope="col">Trip</th>
              <th scope="col">Check-in</th>
              <th scope="col">Check-out</th>
              <th scope="col">Nights</th>
              <th scope="col">Nightly rate</th>
              <th scope="col">Stay price</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="stay in stays" :key="stay.trip_id">
              <td>
                <strong>{{ stay.hotel_name }}</strong>
                <span>{{ stay.city }}, {{ stay.state }}</span>
              </td>
              <td>{{ stay.trip_name }}</td>
              <td>{{ stay.check_in }}</td>
              <td>{{ stay.check_out }}</td>
              <td>{{ stay.nights }}</td>
              <td>{{ formatCurrency(stay.nightly_rate_usd) }}</td>
              <td>{{ formatCurrency(stay.stay_price_usd) }}</td>
            </tr>
            <tr v-if="!stays.length">
              <td class="empty-result" colspan="7">
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
  </main>
</template>
