<script setup>
defineProps({
  stay: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})
defineEmits(['choose'])

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const date = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
})
function formatDate(value) {
  return date.format(new Date(`${value}T00:00:00Z`))
}
</script>

<template>
  <article class="stay-card" :class="{ 'stay-selected': selected }">
    <div class="stay-media" role="img" :aria-label="`Photo placeholder for ${stay.hotel_name}`">
      <div class="main-placeholder">
        <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
          <rect x="7" y="9" width="34" height="30" rx="4" />
          <circle cx="17" cy="19" r="3" />
          <path d="m8 33 10-9 7 6 7-11 9 14" />
        </svg>
        <span>Photo coming soon</span>
      </div>
      <div class="placeholder-thumbnails" aria-hidden="true"><span></span><span></span></div>
    </div>
    <div class="stay-details">
      <div class="stay-copy">
        <h3>{{ stay.hotel_name }}</h3>
        <p class="stay-location">{{ stay.city }}, {{ stay.state }}</p>
        <p class="stay-trip">{{ stay.trip_name }}</p>
        <p class="stay-dates">
          {{ formatDate(stay.check_in) }}<br />– {{ formatDate(stay.check_out) }}
        </p>
        <span class="stay-badge"
          >{{ stay.nights }} night{{ stay.nights === 1 ? '' : 's' }} away</span
        >
      </div>
      <div class="stay-offer">
        <div class="stay-price">
          <strong>{{ currency.format(Number(stay.stay_price_usd)) }}</strong>
          <span>stay total</span>
          <span>{{ currency.format(Number(stay.nightly_rate_usd)) }} per night</span>
        </div>
        <button class="stay-button" type="button" :aria-pressed="selected" @click="$emit('choose')">
          {{ selected ? 'Selected' : 'Choose stay' }}
          <span aria-hidden="true">{{ selected ? '✓' : '→' }}</span>
        </button>
      </div>
    </div>
  </article>
</template>
