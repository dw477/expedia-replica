<script setup>
import { ref } from 'vue'
import { fetchDemoZipLocation, fetchZipLocation } from '../api/zip-location.js'

const postcode = ref('')
const requestedPostcode = ref('')
const isLoading = ref(false)
const location = ref(null)
const error = ref('')

async function lookUpZip(enteredPostcode) {
  if (isLoading.value) return
  location.value = null
  error.value = ''
  const zip = enteredPostcode ?? '16802'
  if (typeof zip !== 'string' || zip.length !== 5 || !/^[0-9]{5}$/.test(zip)) {
    error.value = 'Enter a ZIP code containing exactly five digits.'
    return
  }
  requestedPostcode.value = zip
  isLoading.value = true
  try {
    location.value = enteredPostcode === undefined
      ? await fetchDemoZipLocation()
      : await fetchZipLocation(zip)
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
      <button class="secondary-button" type="button" :disabled="isLoading" @click="lookUpZip()">
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
          :disabled="isLoading"
        />
        <small id="zip-hint">Enter a five-digit U.S. ZIP code.</small>
      </div>
      <button class="primary-button" type="submit" :disabled="isLoading">Look up ZIP</button>
    </form>
    <div aria-live="polite" aria-atomic="true">
      <p v-if="isLoading" class="message-text" role="status">Looking up ZIP {{ requestedPostcode }}…</p>
      <dl v-else-if="location" class="zip-location">
        <div><dt>Postcode</dt><dd>{{ location.postcode }}</dd></div>
        <div v-if="location.locality"><dt>Locality</dt><dd>{{ location.locality }}</dd></div>
        <div><dt>Latitude</dt><dd>{{ location.latitude }}</dd></div>
        <div><dt>Longitude</dt><dd>{{ location.longitude }}</dd></div>
      </dl>
    </div>
    <p v-if="error" class="message-text error-text" role="alert">{{ error }}</p>
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
</style>
