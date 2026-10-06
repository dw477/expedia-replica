<script setup>
import { computed, nextTick, ref } from 'vue'
import { fetchLocalHotels, fetchSavedHotelIds, saveLocalHotel, removeLocalHotel } from '../api/local-hotels.js'
import { fetchNearbyHotels } from '../api/nearby-hotels.js'
import { fetchDemoZipLocation, fetchZipLocation } from '../api/zip-location.js'
import NearbyHotelsMap from './NearbyHotelsMap.vue'

const postcode = ref('')
const requestedPostcode = ref('')
const isLoading = ref(false)
const location = ref(null)
const error = ref('')
const hotels = ref([])
const hotelError = ref('')
const hasLoadedHotels = ref(false)
const selectedPlaceId = ref('')
const resultSource = ref('')
const savedIds = ref(new Set())
const pendingIds = ref(new Set())
const mutationNotice = ref('')
const mutationError = ref('')
const isBusy = computed(() => isLoading.value || pendingIds.value.size > 0)
const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

function displayName(hotel) {
  return hotel.name || 'Unnamed hotel'
}

async function addHotel(hotel) {
  if (isLoading.value || savedIds.value.has(hotel.place_id) || pendingIds.value.has(hotel.place_id)) return
  pendingIds.value.add(hotel.place_id)
  mutationNotice.value = ''
  mutationError.value = ''
  let saved = false
  try {
    await saveLocalHotel(hotel, location.value)
    savedIds.value.add(hotel.place_id)
    saved = true
    mutationNotice.value = `${displayName(hotel)} saved locally with simulated classroom nights.`
  } catch (requestError) {
    mutationError.value = requestError instanceof Error ? requestError.message : 'The hotel could not be saved.'
  } finally {
    pendingIds.value.delete(hotel.place_id)
  }
  if (saved) {
    await nextTick()
    if (typeof document !== 'undefined') document.getElementById(`local-remove-${hotel.place_id}`)?.focus()
  }
}

async function removeHotel(hotel) {
  if (isLoading.value || !savedIds.value.has(hotel.place_id) || pendingIds.value.has(hotel.place_id)) return
  pendingIds.value.add(hotel.place_id)
  mutationNotice.value = ''
  mutationError.value = ''
  let removed = false
  try {
    await removeLocalHotel(hotel.place_id)
    savedIds.value.delete(hotel.place_id)
    removed = true
    if (resultSource.value === 'Saved locally') {
      hotels.value = hotels.value.filter((item) => item.place_id !== hotel.place_id)
      if (selectedPlaceId.value === hotel.place_id) selectedPlaceId.value = ''
    }
    mutationNotice.value = `${displayName(hotel)} removed locally, including all ZIP associations and demo nights.`
  } catch (requestError) {
    mutationError.value = requestError instanceof Error ? requestError.message : 'The hotel could not be removed.'
  } finally {
    pendingIds.value.delete(hotel.place_id)
  }
  if (removed) {
    await nextTick()
    if (typeof document !== 'undefined') {
      const nextId = resultSource.value === 'Saved locally' ? hotels.value[0]?.place_id : hotel.place_id
      document.getElementById(nextId ? `nearby-hotel-${nextId}` : 'zip-postcode')?.focus()
    }
  }
}
const selectedHotel = computed(() => hotels.value.find((hotel) => hotel.place_id === selectedPlaceId.value))

async function selectHotel(placeId) {
  if (!hotels.value.some((hotel) => hotel.place_id === placeId)) return
  selectedPlaceId.value = placeId
  await nextTick()
  if (typeof document !== 'undefined') {
    document.getElementById(`nearby-hotel-${placeId}`)?.scrollIntoView({ block: 'nearest' })
  }
}

async function lookUpZip(enteredPostcode) {
  if (isBusy.value) return
  location.value = null
  error.value = ''
  hotels.value = []
  hotelError.value = ''
  hasLoadedHotels.value = false
  selectedPlaceId.value = ''
  resultSource.value = ''
  savedIds.value = new Set()
  mutationNotice.value = ''
  mutationError.value = ''
  const zip = enteredPostcode ?? '16802'
  if (typeof zip !== 'string' || zip.length !== 5 || !/^[0-9]{5}$/.test(zip)) {
    error.value = 'Enter a ZIP code containing exactly five digits.'
    return
  }
  requestedPostcode.value = zip
  isLoading.value = true
  try {
    const local = await fetchLocalHotels(zip)
    if (local.length) {
      hotels.value = local
      location.value = local[0].location
      savedIds.value = new Set(local.map((hotel) => hotel.place_id))
      resultSource.value = 'Saved locally'
      hasLoadedHotels.value = true
      return
    }
    // Verify status globally: a provider hotel may already be saved for another ZIP.
    savedIds.value = new Set(await fetchSavedHotelIds())
    location.value = enteredPostcode === undefined
      ? await fetchDemoZipLocation()
      : await fetchZipLocation(zip)
    try {
      hotels.value = await fetchNearbyHotels(zip)
      hasLoadedHotels.value = true
      resultSource.value = 'API results'
    } catch (requestError) {
      hotelError.value = requestError instanceof Error
        ? requestError.message
        : 'Nearby hotel search failed.'
    }
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : 'ZIP lookup failed.'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <section class="zip-demo" aria-labelledby="zip-demo-title" :aria-busy="isLoading">
    <div class="zip-demo-heading">
      <h2 id="zip-demo-title">ZIP lookup demonstration</h2>
      <button class="secondary-button" type="button" :disabled="isBusy" @click="lookUpZip()">
        Look up ZIP 16802
      </button>
    </div>
    <form class="zip-lookup-form" @submit.prevent="lookUpZip(postcode)">
      <div class="zip-field">
        <label for="zip-postcode">ZIP code</label>
        <input
          id="zip-postcode"
          v-model="postcode"
          name="postcode"
          type="text"
          inputmode="numeric"
          autocomplete="postal-code"
          pattern="[0-9]{5}"
          minlength="5"
          maxlength="5"
          required
          aria-describedby="zip-hint"
          :disabled="isBusy"
        />
        <small id="zip-hint">Enter a five-digit U.S. ZIP code.</small>
      </div>
      <button class="primary-button" type="submit" :disabled="isBusy">Look up ZIP</button>
    </form>
    <div aria-live="polite" aria-atomic="true">
      <p v-if="isLoading" class="message-text" role="status">Looking up ZIP {{ requestedPostcode }} and nearby hotels…</p>
      <dl v-else-if="location" class="zip-location">
        <div><dt>Postcode</dt><dd>{{ location.postcode }}</dd></div>
        <div v-if="location.locality"><dt>Locality</dt><dd>{{ location.locality }}</dd></div>
        <div><dt>Latitude</dt><dd>{{ location.latitude }}</dd></div>
        <div><dt>Longitude</dt><dd>{{ location.longitude }}</dd></div>
      </dl>
    </div>
    <p v-if="error" class="message-text error-text" role="alert">{{ error }}</p>
    <p v-if="mutationNotice" class="message-text success-text" role="status">{{ mutationNotice }}</p>
    <p v-if="mutationError" class="message-text error-text" role="alert">{{ mutationError }}</p>
    <p v-if="hotelError" class="message-text error-text" role="alert">{{ hotelError }}</p>
    <section v-if="location && hasLoadedHotels" class="nearby-hotels" aria-labelledby="nearby-hotels-title">
      <div class="nearby-heading">
        <div>
          <p class="nearby-eyebrow">Explore the area</p>
          <h3 id="nearby-hotels-title">{{ resultSource === 'Saved locally' ? 'Saved hotels for ZIP' : 'Hotels within 5 km of ZIP' }} {{ location.postcode }}</h3>
        </div>
        <span class="nearby-count">{{ hotels.length }} hotel{{ hotels.length === 1 ? '' : 's' }}</span>
      </div>
      <p class="nearby-description">
        <strong>{{ resultSource }}</strong> ·
        {{ resultSource === 'Saved locally'
          ? 'This is your saved subset, not a complete list of hotels in the area. Rates and rooms below are simulated classroom data.'
          : 'Live hotel locations. Room availability and prices are not supplied by the API.' }}
      </p>
      <p v-if="selectedHotel" class="selected-hotel-status" role="status">Selected {{ displayName(selectedHotel) }}</p>
      <div class="nearby-layout">
        <div class="nearby-list-panel">
          <ul v-if="hotels.length" class="nearby-list" aria-label="Nearby hotels">
            <li v-for="hotel in hotels" :key="hotel.place_id">
              <button
                :id="`nearby-hotel-${hotel.place_id}`"
                type="button"
                class="nearby-hotel-button"
                :class="{ 'is-selected': selectedPlaceId === hotel.place_id }"
                :aria-pressed="selectedPlaceId === hotel.place_id"
                @click="selectHotel(hotel.place_id)"
              >
                <span class="nearby-hotel-name">{{ displayName(hotel) }}</span>
                <span v-if="hotel.address" class="nearby-hotel-address">{{ hotel.address }}</span>
                <span class="nearby-hotel-distance">{{ (hotel.distance_m / 1000).toFixed(1) }} km from ZIP point</span>
              </button>
              <div class="local-hotel-actions">
                <button
                  class="secondary-button" type="button"
                  :disabled="savedIds.has(hotel.place_id) || pendingIds.has(hotel.place_id)"
                  :aria-label="`Add ${displayName(hotel)} to local storage`"
                  @click="addHotel(hotel)"
                >{{ pendingIds.has(hotel.place_id) && !savedIds.has(hotel.place_id) ? 'Saving…' : 'Add to Local' }}</button>
                <span v-if="savedIds.has(hotel.place_id)">Saved locally</span>
                <button
                  v-if="savedIds.has(hotel.place_id)"
                  :id="`local-remove-${hotel.place_id}`"
                  class="danger-button" type="button"
                  :disabled="pendingIds.has(hotel.place_id)"
                  :aria-label="`Remove ${displayName(hotel)} from local storage`"
                  @click="removeHotel(hotel)"
                >{{ pendingIds.has(hotel.place_id) ? 'Removing…' : 'Remove from Local' }}</button>
              </div>
              <div v-if="resultSource === 'Saved locally'" class="demo-nights">
                <p><strong>Simulated classroom data</strong></p>
                <ul :aria-label="`Demo nights for ${displayName(hotel)}`">
                  <li v-for="night in hotel.demo_nights" :key="night.stay_date">
                    {{ night.stay_date }} · {{ currency.format(Number(night.nightly_rate_usd)) }}/night ·
                    {{ night.rooms_available }} rooms available
                  </li>
                </ul>
                <p v-if="!hotel.demo_nights.length">No demo nights stored.</p>
              </div>
            </li>
          </ul>
          <p v-else class="nearby-empty">{{ resultSource === 'Saved locally'
            ? 'No saved hotels remain in these results. Look up the ZIP again to search the API.'
            : 'No hotels were found within 5 km of this ZIP point.' }}</p>
        </div>
        <NearbyHotelsMap
          :center="location"
          :hotels="hotels"
          :selected-place-id="selectedPlaceId"
          @select="selectHotel"
        />
      </div>
    </section>
  </section>
</template>

<style scoped>
.zip-demo {
  margin: 24px 0;
  padding: 24px;
  border: 1px solid #dedde1;
  border-radius: 18px;
  background: #fff;
}
.zip-demo-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.zip-demo-heading h2 {
  margin: 0;
  font-size: 20px;
}
.zip-lookup-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  margin-top: 24px;
}
.zip-field {
  display: grid;
  gap: 8px;
  flex: 1 1 220px;
  min-width: 0;
}
.zip-field label {
  font-weight: 700;
}
.zip-field input {
  width: 100%;
  padding: 12px;
  border: 1px solid #8b8792;
  border-radius: 8px;
}
.zip-location {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
  gap: 16px;
  margin: 24px 0 0;
}
.zip-location dt {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
}
.zip-location dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.nearby-hotels {
  margin-top: 28px;
  border-top: 1px solid #dedde1;
  padding-top: 24px;
}

.nearby-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.nearby-eyebrow {
  margin: 0 0 6px;
  color: #5e687c;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.nearby-heading h3 {
  margin: 0;
  font-size: 20px;
}

.nearby-count {
  color: #42516a;
  font-weight: 700;
}

.nearby-description {
  color: #5e687c;
  margin: 10px 0 16px;
}

.selected-hotel-status {
  margin: 0 0 12px;
  color: #253a68;
  font-weight: 700;
}

.nearby-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
  gap: 16px;
  align-items: start;
}

.nearby-list-panel {
  min-width: 0;
}

.nearby-list {
  display: grid;
  gap: 8px;
  list-style: none;
  padding: 0 6px 0 0;
  margin: 0;
  max-height: 380px;
  overflow-y: auto;
}

.nearby-hotel-button {
  display: grid;
  gap: 5px;
  width: 100%;
  padding: 13px 14px;
  text-align: left;
  border: 1px solid #dedde1;
  border-radius: 10px;
  background: #fff;
  color: #1a2944;
  cursor: pointer;
}

.nearby-hotel-button:hover,
.nearby-hotel-button.is-selected {
  border-color: #253a68;
  background: #f3f6fb;
}

.nearby-hotel-button:focus-visible {
  outline: 3px solid #d47717;
  outline-offset: 2px;
}

.nearby-hotel-name {
  font-weight: 700;
}

.nearby-hotel-address {
  color: #5e687c;
  overflow-wrap: anywhere;
}

.nearby-hotel-distance {
  color: #253a68;
  font-size: 13px;
  font-weight: 700;
}

.local-hotel-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}

.demo-nights {
  padding: 8px 12px;
  background: #f3f6fb;
  border-radius: 8px;
  font-size: 13px;
}

.demo-nights ul {
  padding-left: 18px;
}

.nearby-empty {
  margin: 0;
  padding: 20px;
  border: 1px solid #dedde1;
  border-radius: 10px;
}

@media (max-width: 760px) {
  .nearby-layout {
    grid-template-columns: 1fr;
  }

  .nearby-list {
    max-height: 320px;
    padding-right: 0;
  }
}
</style>
