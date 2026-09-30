# Live nearby hotels API

`GET /api/zip-hotels?postcode=02108` returns a JSON array of hotel places within
5,000 meters of the exact point returned by `lookup_zip(postcode)`. The required
ZIP is five ASCII digits, including leading zeros. A request first resolves the
ZIP through the existing Geoapify geocoding controller, then queries Geoapify
Places with `categories=accommodation.hotel` and a 5,000 meter circle filter.
The backend uses `GEOAPIFY_API_KEY`; the key never appears in the response.

Each row contains `place_id`, `name`, nullable `address`, `latitude`, `longitude`,
and `distance_m`. Distance is calculated from the returned ZIP point, and rows
are sorted nearest first. The endpoint requests additional pages when needed and
deduplicates by provider place ID. An unresolved ZIP returns 404, invalid input
422, a provider failure 502, and missing configuration 503. A resolved ZIP with
no nearby hotels returns `[]`. Responses use `Cache-Control: no-store`.

The response contract lives in `models/contracts.py` and is exposed by
`/openapi.json`. These live places are separate from the application's priced
`Hotel` and `Trip` records: they have no room availability or booking rate.
