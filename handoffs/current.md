# Current Handoff

## What works

The first end-to-end hotel search is implemented on `main`.

- Users can enter a full or partial hotel name in the Vue interface. Matching is
  case-insensitive and ignores surrounding whitespace.
- `frontend/src/api/stays.js` sends the request separately from the presentation
  code in `frontend/src/App.vue`.
- FastAPI exposes `GET /api/stays?hotel_name=...` and returns JSON.
- The framework-free backend queries SQLite, joins hotels and trips by `hotel_id`,
  and returns each matching fixed-date stay.
- SQLite is initialized automatically and imports all four starter CSV files only
  once. A seed marker preserves later booking changes and deletions across restarts.
- The Vue interface can select a traveler and searched stay, create a booking, load
  booking history, cancel a confirmed booking, and permanently delete a booking.
- All frontend data operations use FastAPI; SQLite access stays in the backend.
- Nights and total stay prices are calculated by the backend.
- The interface shows loading and error states, a labeled result table, and a
  clear message when no hotel matches.
- Vite proxies `/api` to `http://127.0.0.1:8000` during local development.

## What was checked

The following checks passed in the project environments:

```sh
backend/.venv/bin/python -m pytest backend/tests -q
cd frontend
npm run lint
npm run build
```

- All 20 backend tests passed, covering one-time CSV seeding, persistence across
  reinitialization, foreign-key enforcement, hotel-name matching, calculated nights
  and prices, booking CRUD and conflicts, API responses, no matches, and required
  query parameters.
- Backend tests emitted two deprecation warnings from the installed
  FastAPI/Starlette test dependencies; there were no test failures.
- Frontend lint passed without adding dependencies.
- The Vite production build completed successfully.
- A live request through the Vite proxy for `Lantern` returned both Harbor
  Lantern Hotel stays.

## Remaining limitations

- Search is limited to hotel names; there are no city, date, price, or availability
  filters beyond the fixed stays in `trips.csv`.
- Authentication, payments, taxes, and fees are not implemented. Demo travelers
  are selected explicitly in the interface.
- The frontend has no automated component or browser tests. Its current evidence
  is lint, production build, and the live proxy check.
- The Vite proxy is a development setup. Production hosting and cross-origin
  configuration have not been defined.
- The development servers are currently stopped.

## Next step

Add authentication and replace demo-traveler selection with a signed-in user before
introducing any real reservation or payment workflow.

## Repository state

The remote is `https://github.com/dw477/expedia-replica.git`. Branch
`database-integration` contains commit `225fb0a` (`Add SQLite database integration`)
plus the current uncommitted booking workflow changes.
