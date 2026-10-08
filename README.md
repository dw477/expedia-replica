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

## Travel assistant chatbot

The floating **Travel assistant** button and the navigation button open a compact
chat popup. Ask a question, choose a suggested question, or continue a conversation.
After each answer, the suggested questions change to follow-ups based on that
question and answer. They appear below the reply; selecting one sends a follow-up.
Close it with the close button or Escape; your draft and conversation stay available
when you reopen it. A pending reply can finish while the popup is closed.
Enter sends; Shift + Enter inserts a new line. **New chat** clears the visible
conversation and starts a new conversation ID; existing server records remain.
Failed requests restore the message for retry. Chat is public and independent of
sign-in, hotel search, and bookings.

Install the updated backend requirements, then set these values in the project-root
`.env` (never a frontend `VITE_` variable):

```sh
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

```dotenv
GEMINI_API_KEY=your-api-key
GEMINI_MODEL=gemini-3.8-flash
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey). The model is
optional and defaults to `gemini-3.8-flash`; use a model supported by your account's
Interactions API. Process environment values override `.env`. Restart the backend
after configuration changes. An unconfigured assistant displays an error without
affecting hotel search or other features.

`POST /api/chat` accepts `{ "messages": [{ "role": "user", "content": "Which saved hotels in ZIP 02108 have a room on October 10, 2026?" }] }`
and an optional `conversation_id` (version-4 UUID). The browser keeps that ID in
page memory and reuses it for follow-ups and retries. Other fields are rejected.
It returns `{ "reply": "...", "suggestions": ["..."] }`, with up to three
short, distinct follow-up questions (or an empty array). Send alternating user/assistant messages ending
with the current user question. Requests require the existing CSRF header and all
responses use `Cache-Control: no-store`. Invalid input returns 422, missing CSRF
returns 403, missing configuration returns 503, storage failures return a safe
500, and provider or rejected-query failures return a safe 502. Provider 503
outages show "Gemini is temporarily unavailable. Please try again
in a moment." Timeouts show "Gemini took too long to reply. Please try again."
Other provider failures keep the generic safe message. The API key and provider
metadata never appear in response bodies or error logs. A key can be configured
correctly while Gemini's service is unavailable; retry after the provider recovers.

The assistant reads [prompts/hotel-assistant.md](prompts/hotel-assistant.md) once
at backend startup. This separate file contains its purpose, actual SQLite columns,
the JOIN from `saved_hotels` to `saved_hotel_zip_locations` by `hotel_id`, and the
JOIN to `demo_hotel_nights` by `hotel_id`. **Restart the backend after editing the
prompt**; Python's `--reload` does not reliably notice Markdown edits.

`backend/controllers/chat.py` makes two server-side `google-genai` requests with
`client.interactions.create()` and `interaction.output_text`, following
[Google's Interactions documentation](https://ai.google.dev/gemini-api/docs/interactions-overview).
The browser sends up to 10 complete recent exchanges plus the new question, within
32,000 characters total; each message is limited to 8,000 characters. Provider
calls have a 30-second timeout with automatic retries disabled and a 1,024-token
output limit per request. The first request proposes SQL from the question and
schema. The backend parses and authorizes one read-only SELECT against only the
three saved hotel tables on a separate read-only connection. It blocks private
tables, writes, multiple statements, and unsafe functions, and enforces a one-second
execution deadline, 100 returned rows, and a bounded result size. The second request
receives the original question and those rows and answers from them, acknowledging
empty results. That same request generates suggested questions based on the latest
question and answer, using a validated JSON response schema. No extra LLM call is
needed for suggestions. Both requests include the loaded prompt and use `store=False`.

Ask about ZIPs, dates, available rooms, and cheapest saved options. Rates convert
from stored integer cents to dollars. Multi-night stays require records and enough
rooms for every night; missing dated records mean availability is unknown. Answers
label rates and rooms **simulated classroom data** and describe only the saved
subset. The assistant cannot read accounts or Assignment 1 bookings or mutate data.

Schema version 6 adds `conversation_history` without resetting existing data. The
server stores separate user/assistant messages with IDs, conversation ID, timestamp,
role, and content. It also commits clearly labeled generated SQL, executed SQL,
result summaries, and safe errors as each step occurs. These trusted writes are
separate from the model's read-only hotel query; a later failure preserves earlier
records. Browser context is not logged again on follow-ups. The visible transcript
and conversation ID stay in page memory, without browser storage; resetting the
popup does not delete server records. There is no public transcript-read endpoint.
Chat schemas live in `backend/models/contracts.py` and `/openapi.json`.

## Assignment 2 local hotel demo

ZIP lookup checks saved hotels first. Matching local results use their stored ZIP
point and show dated rates and rooms labeled **simulated classroom data**. They
are only the saved subset, not a complete area listing. A successful empty local
lookup falls back to the existing live API; a local error is shown without calling
it. The fixed ZIP demonstration follows the same local-first flow.

Use **Add to Local** beside a live hotel to save its exact provider ID and searched
ZIP/location context. Database-backed status survives a browser refresh. Saves
create five fictional nights, October 10–14, 2026 inclusive, at $100.00 and 20 rooms
per night. Repeated saves preserve existing rates/inventory. **Remove from Local**
removes that saved hotel, all its ZIP associations, and its demo nights atomically.
This classroom storage is shared, independent of sign-in and Assignment 1 bookings.

Startup additively applies schema version 6 to the same SQLite database; no reset,
new dependencies, or new setup commands are needed. See `docs/design.md` for the
local endpoint and storage contracts.
