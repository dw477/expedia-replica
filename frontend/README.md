# Frontend

Vue 3 and Vite power the phone layout, styled after the supplied reference with a
cream background, navy frame, yellow accents, and stacked hotel stay cards.

## Development

Use a Node.js version supported by `package.json`, then run:

```sh
npm install
npm run dev
```

Run the existing FastAPI application separately from the repository root:

```sh
backend/.venv/bin/python -m uvicorn backend.app:app --reload
```

Vite forwards `/api` requests to `http://127.0.0.1:8000`.

## Functionality and data

The API contracts in `backend/app.py` are the source of truth. The frontend API
modules in `src/api/` use those existing routes for hotel-name search and booking
creation, history, cancellation, and deletion. Search results contain fixed trip
dates; the stay selector chooses among those trips. Price sorting happens locally
using the stay total, without changing API result order or booking choices.

`src/components/StayCard.vue` contains the image placeholders. They are explicitly
labeled as placeholders and do not represent real hotel photos. Cards show only
API-provided hotel, location, trip, date, night, and price information. The reference's
flights, bundle savings, ratings, and amenities are omitted because the API does
not provide those fields.

## Checks

```sh
npm run lint
npm run build
node --test tests/*.test.js
```

The price sorting tests use Node's built-in test runner. This JavaScript project
has no separate configured type checker; the production build compiles the Vue
components.
