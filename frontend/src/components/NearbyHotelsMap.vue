<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  center: { type: Object, required: true },
  hotels: { type: Array, required: true },
  selectedPlaceId: { type: String, default: '' },
})
const emit = defineEmits(['select'])

const mapElement = ref(null)
const mapError = ref('')
const markers = new Map()
let leaflet
let map
let radiusCircle
let centerMarker
let removed = false

function hotelIcon() {
  return leaflet.divIcon({
    className: 'hotel-map-marker',
    html: '<span aria-hidden="true"></span>',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })
}

function popupContent(hotel) {
  const content = document.createElement('div')
  const name = document.createElement('strong')
  name.textContent = hotel.name
  content.append(name)
  if (hotel.address) {
    const address = document.createElement('div')
    address.textContent = hotel.address
    content.append(address)
  }
  const distance = document.createElement('div')
  distance.textContent = `${(hotel.distance_m / 1000).toFixed(1)} km from ZIP point`
  content.append(distance)
  return content
}

function updateSelection() {
  if (!map) return
  for (const [placeId, marker] of markers) {
    const selected = placeId === props.selectedPlaceId
    marker.getElement()?.classList.toggle('is-selected', selected)
    marker.setZIndexOffset(selected ? 1000 : 0)
    if (selected) {
      map.panTo(marker.getLatLng())
      marker.openPopup()
    } else {
      marker.closePopup()
    }
  }
}

function renderHotels() {
  if (!map) return
  for (const marker of markers.values()) marker.remove()
  markers.clear()
  radiusCircle?.remove()
  centerMarker?.remove()

  const center = [props.center.latitude, props.center.longitude]
  map.setView(center, 12)
  radiusCircle = leaflet.circle(center, {
    radius: 5000,
    color: '#253a68',
    weight: 2,
    fillColor: '#4c70b0',
    fillOpacity: 0.08,
    interactive: false,
  }).addTo(map)
  centerMarker = leaflet.circleMarker(center, {
    radius: 7,
    color: '#fff',
    weight: 2,
    fillColor: '#d32f2f',
    fillOpacity: 1,
    interactive: false,
  }).addTo(map)

  for (const hotel of props.hotels) {
    const marker = leaflet.marker([hotel.latitude, hotel.longitude], {
      icon: hotelIcon(),
      title: hotel.name,
      keyboard: true,
    }).addTo(map)
    marker.bindPopup(() => popupContent(hotel), {
      maxWidth: 220,
      autoPanPadding: [16, 16],
    })
    marker.on('click', () => emit('select', hotel.place_id))
    markers.set(hotel.place_id, marker)
  }

  map.fitBounds(radiusCircle.getBounds(), { padding: [20, 20] })
  updateSelection()
  requestAnimationFrame(() => map?.invalidateSize())
}

onMounted(async () => {
  try {
    leaflet = await import('leaflet')
    if (removed || !mapElement.value) return
    map = leaflet.map(mapElement.value, { scrollWheelZoom: false })
    leaflet.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)
    renderHotels()
  } catch {
    mapError.value = 'The map could not be loaded. The hotel list is still available.'
  }
})

watch(() => [props.center, props.hotels], renderHotels)
watch(() => props.selectedPlaceId, updateSelection)

onBeforeUnmount(() => {
  removed = true
  map?.remove()
  map = null
  markers.clear()
})
</script>

<template>
  <div class="hotel-map">
    <div ref="mapElement" class="hotel-map-canvas" role="region" aria-label="Map of nearby hotels" />
    <p v-if="mapError" class="map-error" role="status">{{ mapError }}</p>
  </div>
</template>

<style scoped>
.hotel-map {
  min-width: 0;
  border: 1px solid #dedde1;
  border-radius: 12px;
  overflow: hidden;
  background: #e8edf2;
}

.hotel-map-canvas {
  width: 100%;
  height: 380px;
}

.map-error {
  padding: 16px;
  margin: 0;
}

.hotel-map :deep(.hotel-map-marker) {
  display: grid;
  place-items: center;
  background: #253a68;
  border: 3px solid white;
  border-radius: 50%;
  box-shadow: 0 2px 8px #182b4a66;
}

.hotel-map :deep(.hotel-map-marker.is-selected) {
  background: #d47717;
  box-shadow: 0 0 0 5px #f8c66c99, 0 2px 8px #182b4a66;
}

.hotel-map :deep(.hotel-map-marker:focus-visible) {
  outline: 3px solid #d47717;
  outline-offset: 3px;
}

.hotel-map :deep(.leaflet-popup-content) {
  overflow-wrap: anywhere;
}
</style>
