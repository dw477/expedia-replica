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
There is no public registration flow.

Authentication endpoints are:

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
