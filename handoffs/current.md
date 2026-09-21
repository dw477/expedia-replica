# Current Handoff

Updated 2026-09-21 against `main` at `df8632f` (`Add user-specific daily surge
pricing and saved booking rates`). This replaces the booking-workflow handoff
last updated in `99ed4cc`.

## What changed since the previous handoff

- `7e5e16b` and `634ffa6`: reference-based frontend redesign, adapted for desktop
  and mobile with stay cards, price sorting, and responsive booking/history panels.
- `6829e37`: explicit MVC models, controller boundaries, transactional CRUD, and
  HTTP schemas in `backend/models/contracts.py`, exposed through `/openapi.json`.
- `b63beb3`: CSV-backed sign-in, persistent expiring sessions, and ownership checks
  replacing the demo traveler picker.
- `64d5124`: account registration with automatic sign-in, password validation,
  duplicate-name handling, and recoverable CSV/SQLite persistence.
- `df8632f`: shared search history, user-specific daily surge pricing, saved
  booking rates, and a non-destructive schema version 3 migration.

## What works

Hotel-name search is public and matches case-folded, whitespace-collapsed
substrings against fixed-date stays. The responsive Vue interface shows labeled
photo placeholders, nightly rates and stay totals, loading/error/empty states,
and local price sorting. Booking history and creation use the signed-in account;
users can cancel and permanently delete their own bookings. Restoration is
supported by the API/controller but has no browser action.

Users can sign in, restore an existing session on page load, register and sign in
automatically, or sign out. The six fictional fixtures are `traveler1` through
`traveler6`, with passwords `TravelDemo1!` through `TravelDemo6!`. Registration
validates the three agreed fields and saves salted PBKDF2-SHA256 hashes in
`data/users.csv`. SQLite holds public identities and session digests. Sessions
expire after eight hours; credential changes invalidate them on the next request.
Account changes clear private state, and stale search responses cannot repopulate
cleared personalized results.

Search submissions use `POST /api/stays`; `GET /api/stays` refreshes current
prices without recording another submission. Only non-empty signed-in submissions
are recorded, including searches with no matches. Counts are separate per user
and normalized query on each fixed UTC−05:00 EST day. Submissions 1–3 use base
prices; submission 4 onward applies base × 1.2 to matching hotels, without
compounding. A qualifying query affects that user's matching hotel prices even
when a later query differs. Nightly rates round to cents before totals are derived.

New bookings calculate and save the user's applicable nightly rate within their
creation transaction. History, cancellation, and restoration retain it after day
changes or base-price edits. The client sends a trip ID, never a price or arbitrary
owner. Schema version 3 snapshots preexisting bookings' displayed base rates once;
startup preserves subsequent changes and never re-imports deleted seed records.

All browser data operations go through FastAPI. Mutations require
`X-Requested-With: XMLHttpRequest`; authentication uses an HTTP-only, host-only,
SameSite=Lax cookie scoped to `/api`. Search and private responses use `no-store`.
The database controller alone handles SQLite and credential CSV access. See
[the design note](../docs/design.md) and [project rules](../AGENTS.md) for contracts.

## What was checked

The following checks were rerun successfully on 2026-09-21 from the repository root:

```sh
backend/.venv/bin/python -m pytest backend/tests -q
(cd frontend && npm run lint)
(cd frontend && npm run build)
(cd frontend && node --test tests/*.test.js)
```

- **145 backend tests passed.** Coverage includes seeding and CRUD, MVC contracts,
  references and rollback, booking conflicts, HTTP validation, authentication and
  ownership, registration concurrency/recovery, surge thresholds and rounding,
  EST midnight boundaries, per-user isolation, and stored-rate migration.
- **28 frontend tests passed.** Coverage includes sorting, rendered card/form
  markup, API adapters, registration errors, sign-in price refreshes, session
  expiry, and stale search responses after account clearing.
- Frontend lint and the Vite production build passed.
- Backend tests reported two installed-dependency deprecations: Starlette's
  `httpx` TestClient integration and AnyIO's `BlockingPortal` alias.
- Frontend tests reported `WebSocket server error: Port 24678 is already in use`;
  all tests still passed and the command exited successfully. Investigate the
  Vite test-server port collision if cleaning up test output.

No separate formatter or type-check command is configured. The frontend is
JavaScript; its build compiles Vue components. Frontend tests use mocked requests
and server-rendered/custom-renderer components, not a real browser. No live proxy,
browser layout, or end-to-end check was rerun for this documentation update.

## Run locally

Use the existing Python virtual environment and a Node version accepted by
`frontend/package.json` (`^22.18.0 || >=24.12.0`). In separate terminals from the
repository root:

```sh
backend/.venv/bin/python -m uvicorn backend.app:app --reload
```

```sh
cd frontend
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. Startup initializes/migrates the
default `backend/expedia.sqlite3`; `EXPEDIA_DATABASE_PATH` selects another database.
Do not reset an existing database to apply these changes. See [README](../README.md)
for dependency installation, CLI search, and password-hash generation.

Registration writes the credential CSV as well as SQLite. The data directory must
be writable and the platform must support POSIX file locking (`fcntl`). Keep real
registered accounts out of Git; only the fictional fixtures belong in the tracked
CSV. Runtime lock, recovery-journal, and temporary files are ignored. Use disposable
data/database copies when verifying registration so fixture data stays unchanged.

## Remaining limitations and next steps

- Search supports hotel names and supplied trip dates only. There are no city,
  flexible-date, price, or room-inventory filters, payments, taxes, or fees.
- Production hosting is not configured. It needs persistent writable CSV/SQLite
  storage, a common browser origin for frontend/API, HTTPS, and
  `EXPEDIA_SECURE_COOKIES=true`; credentialed cross-origin CORS is not enabled.
- Add a real-browser smoke test for registration/sign-in, the fourth-search surge,
  booking creation at that price, cancellation/deletion, and sign-out/expiry.
  Check keyboard interaction and desktop/mobile layouts as part of that work.
- Resolve the test-runner port warning and dependency deprecations in a focused
  maintenance change; they did not block the checks above.

## Repository state

The implementation reviewed is committed on `main` through `df8632f`. The
documentation/report commit also includes the user's changes to `reports/report.md`,
the new `reports/report 2.md`, three screenshots, and the demo video. Report content
was preserved as supplied. Three locally registered accounts in `data/users.csv`
are excluded from the commit to retain the supplied six-account seed fixture.
The verification results above apply to that fixture. Development-server running
state was not checked.
