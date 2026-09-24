import { requestJson } from './request.js'

export async function fetchDemoZipLocation() {
  return fetchLocation('/api/demo/zip-location')
}

export async function fetchZipLocation(postcode) {
  const query = new URLSearchParams({ postcode })
  return fetchLocation(`/api/zip-location?${query}`)
}

async function fetchLocation(url) {
  const location = await requestJson(url)
  if (
    !location || typeof location.postcode !== 'string' ||
    !Number.isFinite(location.latitude) || !Number.isFinite(location.longitude) ||
    (location.locality != null && typeof location.locality !== 'string')
  ) {
    throw new Error('The ZIP lookup returned an unexpected response.')
  }
  return location
}
