# Current Handoff

## What works

The first end-to-end hotel search is implemented on `main`.

- Users can enter a full or partial hotel name in the Vue interface. Matching is
  case-insensitive and ignores surrounding whitespace.
- `frontend/src/api/stays.js` sends the request separately from the presentation
  code in `frontend/src/App.vue`.
- FastAPI exposes `GET /api/stays?hotel_name=...` and returns JSON.
- The framework-free backend reads the supplied hotel and trip CSV files, joins
  them by `hotel_id`, and returns each matching fixed-date stay.
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

- All 10 backend tests passed, covering hotel-name matching, calculated nights
  and prices, the API response, no matches, and the required query parameter.
- Backend tests emitted two deprecation warnings from the installed
  FastAPI/Starlette test dependencies; there were no test failures.
- Frontend lint passed without adding dependencies.
- The Vite production build completed successfully.
- A live request through the Vite proxy for `Lantern` returned both Harbor
  Lantern Hotel stays.

## Remaining limitations

- Search is limited to hotel names; there are no city, date, price, or availability
  filters beyond the fixed stays in `trips.csv`.
- Data is read-only CSV data. There is no SQLite persistence or write workflow.
- Booking creation, cancellation, deletion, traveler history, authentication,
  payments, taxes, and fees are not implemented.
- The frontend has no automated component or browser tests. Its current evidence
  is lint, production build, and the live proxy check.
- The Vite proxy is a development setup. Production hosting and cross-origin
  configuration have not been defined.
- The development servers are currently stopped.

## Next step

Confirm the Part 2 scope, then add a SQLite-backed repository that imports the
starter CSV records only when the database is first created. Preserve the current
FastAPI JSON contract while replacing direct CSV reads, and add persistence tests
before building booking and traveler-history interfaces.

## Repository state

The remote is `https://github.com/dw477/expedia-replica.git`. Commit `4c4dfc9`
(`Implement hotel availability search`) is on `origin/main`. This handoff and
`docs/design.md` are uncommitted documentation changes created afterward.
