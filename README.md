# Expedia Assignment

## Goal

Build a small, maintainable travel application with a clear separation between the user interface and server-side responsibilities.

The specific product requirements and technology choices can be documented here as the assignment evolves.

## Project Layout

- `frontend/` is the View: Vue screens, components, CSS, API adapters, tests, and
  the optional plain-text search interface (`cli.py`).
- `backend/models/` defines Hotel, User, Trip, Booking, immutable result objects,
  validation, the SQLite schema, and HTTP request/response contracts.
- `backend/controllers/` contains the database/CRUD controller, search and booking
  business controllers, and the FastAPI HTTP controller.
- `backend/app.py` remains the ASGI entry point; original backend module paths
  remain compatible.

The CSV-derived relationships are Hotel → Trips, User → Bookings, and Trip →
Bookings. The database controller performs CRUD on all four models, checks parent
references, restricts deletion of referenced entities, and manages transactions.
The browser receives validated JSON and keeps presentation in the View.

MVC rules and contracts are recorded in [AGENTS.md](AGENTS.md). See
[docs/design.md](docs/design.md) for CSV analysis and controller contracts.
`backend/models/contracts.py` is the JSON schema source of truth, also exposed
at `/openapi.json` by FastAPI.

## Setup

The backend uses Python 3.14 and a project-local virtual environment:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

Run backend Python commands with `backend/.venv/bin/python` so dependencies remain isolated from the system interpreter.

The backend uses Python's standard-library SQLite support, so no database server or
additional package is required. Create and seed the local development database from
the four CSV files with:

```sh
backend/.venv/bin/python -m backend.database
```

The database defaults to `backend/expedia.sqlite3`. Set `EXPEDIA_DATABASE_PATH` to
use another location. The backend also initializes the database automatically on
startup. Starter records are imported only once, so later database changes survive
application restarts.

Start the API from the project root:

```sh
backend/.venv/bin/python -m uvicorn backend.app:app --reload
```

The backend loads the project-root `.env` (beside `frontend/` and `backend/`)
at startup using `backend/controllers/configuration.py` and the existing
`python-dotenv` dependency. Set `GEOAPIFY_API_KEY` there; existing process
environment variables take precedence. Restart the backend after adding,
changing, or removing the setting; do not rely on `--reload` to notice `.env`
edits. Keep this local file out of Git.

`GET /api/health` returns `status: "ok"` and a `geoapify` field containing
`"key is configured"` or `"key is not configured"`. Absent, empty, and
whitespace-only values are not configured. This checks configuration presence
only: it never returns the key or contacts Geoapify.

`GET /api/demo/zip-location` makes a backend Geoapify lookup for the fixed ZIP
`16802`. `GET /api/zip-location?postcode=02108` looks up an entered ZIP code;
the required `postcode` must be exactly five ASCII digits (leading zeros are
preserved), otherwise the backend returns 422 before calling Geoapify.
A successful response contains only postcode, country code, latitude,
longitude, and locality (or `null`). Missing/unavailable configuration returns
503, an unresolved ZIP returns 404, and provider failure returns 502. Errors
contain safe messages without credentials or provider URLs. The Vue app's
"ZIP lookup demonstration" panel offers a ZIP input and "Look up ZIP" submit
button alongside "Look up ZIP 16802". Both call the backend through the existing
`/api` proxy and update the same location results display. They show progress or
the backend error independently of hotel-name search, and both buttons are
disabled while a lookup runs. All ZIP responses use `Cache-Control: no-store`.

For the optional text View, search directly from the project root:

```sh
backend/.venv/bin/python -m frontend.cli "Harbor Lantern"
```

The existing `python -m backend.search` interface also remains available.

Run backend tests from the project root:

```sh
backend/.venv/bin/python -m pytest backend/tests
```

The frontend sends all searches and booking operations through FastAPI. Available
booking routes are:

- `GET /api/users` (signed-in user only)
- `GET /api/bookings` (signed-in user’s history)
- `POST /api/bookings`
- `PATCH /api/bookings/{booking_id}`
- `DELETE /api/bookings/{booking_id}`

## Search history and surge pricing

Submitted searches use `POST /api/stays` with `{ "hotel_name": "Harbor" }`.
`GET /api/stays?hotel_name=Harbor` reads prices without recording a search.
Both support public searches; only non-empty submissions by signed-in users are
recorded in the shared SQLite `search_history` table. Queries ignore case and
collapse extra whitespace. Searches with no matching hotels are still recorded.

Counts are separate for each user and normalized query and reset at midnight EST
(fixed UTC−05:00). The current submission counts: searches 1–3 use the base nightly
rate, and search 4 onward applies base × 1.2. Once any query qualifies, all hotels
matching that query have surge pricing for that user for the rest of that day,
including when reached through a different query. Surge never compounds or changes
the hotel's base rate. Nightly rates round to whole cents with half cents rounded
up; stay totals use the rounded nightly rate.

New bookings use the user's applicable hotel price at creation and save that rate.
Existing bookings, including cancelled/restored bookings, keep their saved rate.
Startup automatically adds search history and snapshots existing booking prices
without resetting the database or re-importing CSVs. The seed CSV formats stay the
same. All search responses use `Cache-Control: no-store`, and submitted searches
require the same CSRF header as other POST requests.

## Authentication

Sign in with a username and password to create, view, cancel, or delete bookings.
Hotel search is public. Users can manage only their own bookings; the traveler
picker has been replaced by the signed-in account.

`data/users.csv` holds `user_id,display_name,username,password_hash`. Password data
is a salted PBKDF2-SHA256 hash (600,000 iterations), never readable password text.
The CSV is the authentication source of truth and is read on sign-in/session
validation; changing its username/hash invalidates existing sessions. SQLite
stores public user identities and expiring session digests, not passwords.

The six fictional sample accounts are `traveler1` through `traveler6`. Their demo
passwords are `TravelDemo1!` through `TravelDemo6!`, respectively. For example:

- Username: `traveler6`
- Password: `TravelDemo6!`

These are public assignment fixtures. Keep real account credentials out of Git.
To generate a replacement hash without putting a password in shell history:

```sh
backend/.venv/bin/python -m frontend.hash_password
```

Paste the resulting hash into that user's `password_hash` column. Usernames in the
CSV must be unique lowercase names of 3–64 characters (letters, digits, `.`, `_`,
`-`). Sign-in trims/case-folds usernames; passwords preserve case and whitespace.
Select **Create an account** in the sign-in panel. Registration asks for username,
display name, and password, assigns a unique `U`-prefixed UUID, and signs you in
automatically. Passwords must be 8–256 characters, contain at least one uppercase
letter, one digit, and one of `!@$%&?`, and use only ASCII letters, digits, and those
special characters. Display names must be non-empty. Usernames use the existing
rules above and are checked without case sensitivity.

Account creation saves the salted hash in `users.csv` and the public identity and
session in SQLite. Duplicate usernames return a clear error. File locking and a
recovery journal protect interrupted saves; the backend needs write access to the
data directory. Keep real registered accounts out of Git; commit only the supplied
fictional demo fixtures. Lock/journal/temporary files are ignored.

Authentication endpoints are:

- `POST /api/auth/register` with `{ "username": "newtraveler", "display_name": "New Traveler", "password": "Abcdef1!" }` (201; duplicate username 409, invalid fields 422)
- `POST /api/auth/login` with `{ "username": "traveler6", "password": "TravelDemo6!" }`
- `GET /api/auth/me` to restore the signed-in account
- `POST /api/auth/logout` to revoke the session and clear its cookie

Sessions expire after eight hours and survive backend restarts. Cookies are
HTTP-only, host-only, scoped to `/api`, and `SameSite=Lax`; the browser stores no
session token in local storage. Mutating requests require
`X-Requested-With: XMLHttpRequest`, added by the frontend request adapter.
Booking creation accepts `{ "trip_id": "T001" }`; the API derives `user_id` from
the authenticated session. An optional legacy `user_id` must match that account.
Private responses use `Cache-Control: no-store`.

Startup adds the session table to existing databases without re-importing the
starter data or changing bookings. No database reset is needed. The existing
users table stays compatible with its original public identity fields.

Local HTTP development uses non-secure cookies. For an HTTPS deployment, start
with `EXPEDIA_SECURE_COOKIES=true` so cookies require HTTPS:

```sh
EXPEDIA_SECURE_COOKIES=true backend/.venv/bin/python -m uvicorn backend.app:app
```

The View and API must share one browser origin (Vite's configured `/api` proxy does
this in development); cross-origin CORS access is not enabled.

The frontend uses Vue with Vite and requires a Node.js version accepted by the `engines` field in `frontend/package.json`:

```sh
cd frontend
npm install
npm run dev
```

Run the frontend quality checks from `frontend/`:

```sh
npm run lint
npm run build
node --test tests/*.test.js
```

Do not commit real credentials, API keys, or local environment files.
