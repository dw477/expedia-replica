# MVC Architecture

Reviewed on 2026-09-21 against `main` at `df8632f`.

The application uses Vue as its browser View and Python/FastAPI controllers over
SQLite. UI and CSS stay in `frontend/`. The optional plain-text search View lives
in `frontend/cli.py`; its password-hash entry tool is `frontend/hash_password.py`.
`backend/app.py` exposes the ASGI app and factory; old backend module paths remain
thin compatibility entry points.

## Changes since the previous handoff

The previous handoff described the booking workflow at `99ed4cc`. Since then:

- The reference-based interface became a responsive desktop/mobile layout with
  stay cards, local price sorting, and a booking panel.
- Backend entities, storage contracts, and business operations moved into explicit
  Model and Controller modules; HTTP schemas now have one OpenAPI source of truth.
- CSV-backed authentication replaced the traveler picker with session-owned
  bookings. Registration now creates an account and signs it in atomically across
  the credential CSV and SQLite, with recovery for interrupted saves.
- Signed-in search submissions now drive daily, user-specific surge pricing.
  Bookings save their creation rate, and schema version 3 upgrades existing data
  without reseeding it.

See [the current handoff](../handoffs/current.md) for verification and follow-up work.

## Models identified from the supplied CSVs

The supplied seed CSVs have 8 hotels, 6 users, 12 trips, and 6 bookings. Each ID column is unique;
all 12 hotel references and all 12 booking references resolve. Hotels H001–H003
and H007 have multiple trips. U001 has two bookings; U006 has none. There are four
confirmed and two cancelled bookings, with no duplicate confirmed user/trip pair.

| Model | Fields | Relationships |
| --- | --- | --- |
| Hotel | `hotel_id`, `hotel_name`, `city`, `state`, `nightly_rate_usd` | One hotel has many trips |
| User | `user_id`, `display_name`; CSV credential fields live in `UserAccount` | One user has many bookings |
| Trip | `trip_id`, `hotel_id`, `trip_name`, `check_in`, `check_out` | References one hotel; has many bookings |
| Booking | `booking_id`, `user_id`, `trip_id`, `booked_on`, `status`, `nightly_rate_usd` | References one user and one trip; saves its creation price |
| SearchHistory | `search_id`, `user_id`, `search_query`, `searched_at` | References one user; shared history of submitted searches |

A booking associates a user with a trip, forming the user/trip many-to-many
relationship. It has its own stable ID because cancellation retains history and
subsequent bookings may refer to the same pair. A trip is a fixed-date hotel stay;
no flight, payment, or room-inventory model is implied by this data. Authentication
adds username/password-hash fields to the supplied users CSV and a separate internal
session model; public user identities retain their original SQLite representation.

`backend/models/entities.py` defines immutable entity contracts and validation.
IDs and labels are non-empty text without surrounding whitespace; IDs preserve
letters and leading zeros. Model dates are Python `date` objects. Check-out must
follow check-in. Rates are finite non-negative `Decimal` values with whole cents
within SQLite's integer range. Status is `confirmed` or `cancelled`.

`backend/models/schema.py` is the SQLite schema source of truth. Dates persist as
ISO text; money persists as integer cents. Foreign keys are enforced on every
connection, referenced-parent deletion is restricted, and a partial unique index
allows only one confirmed booking per user/trip pair. Cancellation and deletion
are distinct operations. `models/results.py` defines immutable controller outputs;
nights and total prices are derived from dates and rates, never stored separately.
For example, T001 has two nights at $150, giving $300; B001 links U001 to T001/H001.

## Database controller contract

`backend/controllers/database.py` alone opens SQLite, executes SQL, and reads CSVs.
`DatabaseController(database_path)` configures a workflow; it does not initialize
or seed until `initialize(data_directory)` is called.

| Method | Input | Output |
| --- | --- | --- |
| `initialize(data_directory)` | Seed directory (defaults to `data/`) | `bool`: true only on first import |
| `get(Model, id)` | Hotel/User/Trip/Booking/AuthSession/SearchHistory class and text ID | Validated entity; missing IDs raise |
| `list(Model)` | Supported entity class | Entity list ordered by ID |
| `create(entity)` | Complete validated entity | Persisted entity |
| `update(entity)` | Complete validated entity under its existing ID | Updated entity; cannot rename IDs |
| `delete(Model, id)` | Supported class and text ID | `None`; missing IDs raise |
| `transaction(write=True)` | Write/read mode | Context yielding the controller with one shared connection |
| `list_search_counts(user_id, start, end)` | User ID and half-open Unix timestamp bounds | `list[SearchQueryCount]`, grouped and ordered by normalized query |
| `list_user_accounts(data_directory)` | Credential CSV directory, outside a workflow transaction | Validated `list[UserAccount]` linked to existing SQLite users |
| `register_user_account(account, session, data_directory, previous_session_id=None)` | Validated account/session; optional session digest to revoke | Public `User`; owns its transaction and CSV recovery protocol |
| `delete_expired_sessions(now)` | Non-negative Unix timestamp | Number of expired session rows deleted |

CRUD supports all four travel models, AuthSession, and SearchHistory. Reads never return SQLite rows or open connections.
SQL identifiers come from internal model mappings; values are parameterized.
Writes acquire a transaction before checking references. Workflow transactions
commit on success and roll back on failure; read transactions provide a consistent
snapshot and reject writes. Instances must be scoped to a single workflow and
must not be shared across threads. Nested transactions are unsupported.

Errors crossing this boundary are `RecordNotFoundError` (including missing
parents), `ReferenceConflictError` (parent still referenced), `RecordConflictError`
(uniqueness/data constraints), or base `DatabaseError` (opening, parsing, storage,
or invalid stored data). Invalid entity construction raises `ValueError` before CRUD.

Initialization imports UTF-8 BOM CSVs in parent-first order using entity validation
in a single transaction, audits references with `PRAGMA foreign_key_check`, and
sets a seed marker only after successful import. Failed imports can be retried.
Subsequent initialization upgrades the schema when needed, recovers interrupted
registrations, and audits references without re-importing, preserving new,
updated, and deleted records. Schema version 3 adds search history and snapshots
legacy booking rates as described below; no database reset is required.

## Business controller contracts

Business controllers use public database-controller methods, not SQL or private
connections. Both take an optional `database_path` for isolated testing.

| Controller operation | Input | Output |
| --- | --- | --- |
| `search_available_stays` | `hotel_name`, optional database path/seed directory; keyword `user_id=None`, `record_search=True` | `list[HotelAvailability]` |
| `list_users` | Optional database path | `list[User]` in ID order |
| `list_booking_history` | `user_id`, optional database path | `list[BookingHistoryEntry]` |
| `create_booking` | `user_id`, `trip_id`, optional path/`booked_on` date | Confirmed `BookingHistoryEntry` with generated ID |
| `update_booking_status` | `booking_id`, `status`, optional path/`owner_user_id` | Updated `BookingHistoryEntry` |
| `delete_booking` | `booking_id`, optional path/`owner_user_id` | `None` |

### ZIP lookup controller

`backend/controllers/geocoding.py` provides
`lookup_zip(postcode: str) -> ZipLocation | None`. Input must be exactly five
ASCII digits (preserving leading zeros); invalid input raises `ValueError` before
any request. The View supports user-entered ZIP codes alongside the fixed
`"16802"` demonstration.

It uses the installed HTTPX client and
[Geoapify forward geocoding](https://apidocs.geoapify.com/docs/geocoding/) with
`postcode`, `type=postcode`, `filter=countrycode:us`, and `format=json`.
`controllers/configuration.py` supplies the key exclusively to the backend request.
Timeouts are 10 seconds per network phase; redirects are not followed.

`backend/models/location.py` defines frozen `ZipLocation` with `postcode`,
`country_code` (`us`), `latitude`, `longitude`, and optional `locality` (`None`
when absent). Locality uses the first non-empty city/town/village. It has no price
or Hotel relationship and is not persisted. Accept only an exact postcode,
case-insensitive U.S. country code, `result_type=postcode`, and numeric, finite
latitude/longitude within ±90/±180; booleans and numeric strings are rejected.
Return the first acceptable result. Empty results, mismatches, and invalid
candidate coordinates produce `None` if no acceptable candidate remains.

Missing/unreadable configuration raises `ZipConfigurationError`, a subclass of
`ZipLookupError`. Transport/timeouts, non-success HTTP responses, invalid JSON,
or a missing/non-array `results` envelope raise `ZipLookupError` with a fixed
safe message. No provider bodies or original exception chains are exposed.
HTTPX request logs for Geoapify are suppressed because they include the API key
in the URL. Mocked tests exercise request parameters, results, errors, and log
redaction without using real credentials. The thin public demo route below calls
this controller with fixed `"16802"`; `/api/zip-location` passes the validated
`postcode` query parameter. Vue's `ZipLookupDemo.vue` uses `src/api/zip-location.js`
and the shared request adapter for both its fixed demo button and ZIP form.
The text input uses a numeric keyboard hint and five-digit validation while
preserving leading zeros; submitting by button or Enter updates the same results
display used by the demo. The panel clears earlier results/errors on each request,
disables both buttons and the input while loading, and announces progress/results/errors.
Its state is independent of hotel search. No frontend credentials or direct
provider requests are used.

### Search and booking controllers

`controllers/search.py` matches a hotel-name substring after collapsing whitespace and
case-folding in both the query and hotel name. Results are ordered by trip ID; blank input and no matches return
`[]`. It initializes the database for the standalone CLI as well as API use and
raises `SearchDataError` for data failures. The sample data guide includes city
examples; the existing application contract searches hotel names.

`controllers/bookings.py` creates IDs and default booking dates, implements status
changes and history ordering (date descending, then ID descending), and translates
database errors to `BookingNotFoundError`, `BookingConflictError`, or
`BookingDataError`. An invalid status raises `ValueError`. Creation/status changes
and their result joins share one write transaction; history shares one read
snapshot. The SQLite uniqueness constraint protects confirmed-booking rules,
including simultaneous writers and restoration of a cancelled booking.

`HotelAvailability` contains trip ID/name, hotel name, city/state, check-in/out,
nightly rate, and derived nights/stay total. `BookingHistoryEntry` adds booking
ID, user ID/display name, booked-on date, and status.

## Search history and user-specific surge pricing

`models/search.py` defines immutable `SearchHistory(search_id, user_id,
search_query, searched_at)` and `SearchQueryCount(search_query, search_count)`.
All users share one SQLite history table; the user reference restricts deletion,
and an index on user/time/query supports daily counts. Query normalization uses
case-folding and collapses all whitespace runs to one space. Timestamps are Unix
seconds. Non-empty signed-in submissions are recorded even when nothing matches;
anonymous searches and read-only refreshes are not recorded.

`controllers/pricing.py` defines daily boundaries at midnight EST, fixed UTC−05:00
(no daylight-saving adjustment). Each user/query count includes the current
submission. At four or more searches, every hotel whose normalized name contains
that query costs base × 1.2 for that user for the rest of the day. Different queries
count separately, but a qualifying query continues to surge the hotel even if a
later search uses another query. Multiple qualifying queries never compound the
multiplier. Base rates are untouched. Decimal `ROUND_HALF_UP` rounds the nightly
rate to cents before the derived stay total is calculated.

Search inserts and count/result reads share a write transaction, serializing
concurrent submissions at the threshold. Booking creation reads the same policy
inside its own write transaction; it requires only the trip, so omitting or changing
a search query cannot bypass a hotel's surge. It saves the final nightly rate in
`bookings.nightly_rate_cents`. History, cancellation, and restoration use that saved
rate even after later searches, day changes, or hotel price edits. Existing bookings
never gain surge. The client cannot submit a price or choose a pricing owner.

Schema version 3 adds history and the booking rate column. A one-time migration
snapshots each preexisting booking's currently displayed hotel rate, including
cancelled bookings. Initialization is atomic and idempotent and never restores
deleted seed records. Seed bookings resolve their initial rate from their trip's
hotel; the pricing feature does not change any CSV columns. Authentication's
additional user columns remain required. Nights and totals are not stored.

## Authentication contracts

`data/users.csv` extends the original public identity columns with `username` and
`password_hash`. `models/authentication.py` defines `UserAccount` with these four
fields and enforces canonical unique-name/hash formats. `User` still contains
only public identity fields; usernames/passwords are not mirrored into SQLite.
`DatabaseController.list_user_accounts(data_directory)` reads and validates the CSV
on every authentication operation, returning only accounts whose IDs exist in
SQLite. Deleting an identity disables its login without reseeding it.

`controllers/passwords.py` hashes passwords with a fresh 16-byte salt and
PBKDF2-HMAC-SHA256 at 600,000 iterations. The CSV format is
`pbkdf2_sha256$600000$<salt hex>$<digest hex>`; malformed or readable password
values fail closed. Verification preserves password case/whitespace, compares
hashes in constant time, and bounds password length at 256 characters. The
algorithm/work factor follows [OWASP's password-storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
while using Python's existing standard library. Usernames in the CSV are lowercase,
3–64 characters, using letters/digits/dots/underscores/hyphens. Login input trims
and case-folds usernames.

`AuthenticationController(database_path, data_directory)` exposes:

| Operation | Output | Failure contract |
| --- | --- | --- |
| `register(username, display_name, password, previous_token=None)` | `(User, raw token)`, automatic sign-in | `ValueError`, `AccountExistsError`, `AuthenticationDataError` |
| `login(username, password, previous_token=None)` | `(User, raw token)` | `InvalidCredentialsError`, `AuthenticationDataError` |
| `current_user(token)` | `User` | `AuthenticationRequiredError`, `AuthenticationDataError` |
| `logout(token)` | `None`, idempotent revocation | `AuthenticationDataError` |

Registration trims/case-folds usernames and trims non-empty display names. New
passwords must be 8–256 ASCII letters/digits or `!@$%&?`, including at least one
uppercase letter, digit, and allowed special. There is no lowercase requirement.
Existing login verification retains its original password policy. The immutable
model's validator owns the password policy; `RegistrationRequest` owns the exact
three JSON fields and rejects extras. Validation responses contain location,
message, and error type, never submitted input.

The authentication controller assigns `U` plus a random UUID's 32 uppercase hex
digits and hashes the password before calling
`DatabaseController.register_user_account(account, session, data_directory,
previous_session_id=None) -> User`. The database controller owns this transaction,
checks username/ID uniqueness, appends credentials to CSV, inserts the public user
and first session into SQLite, and revokes the previous session only on success.
CSV usernames remain reserved even if their SQLite identity is removed. Duplicate
usernames raise `AccountUsernameConflictError`, mapped by authentication to
`AccountExistsError`; other uniqueness/storage failures are database errors.

Registrations use SQLite's write lock and a stable POSIX account-file lock
(`.users.csv.lock`) to serialize writers across processes. CSV publication uses
owner-readable temporary files, atomic replacement, and fsync. A durable
`.users.csv.registration.json` journal contains the original CSV bytes and new
user ID before any mutations. Recovery keeps the new CSV if that identity has
committed; otherwise it restores the original CSV. Initialization and credential
reads recover pending saves while holding the file lock. Cleanup after commit is
idempotent. Credential reads must precede database read transactions; registration
owns its transaction and cannot be nested. These runtime files and real account
records must stay out of version control. The deployment needs write access to
its CSV directory as well as SQLite; the existing fixture columns/schema remain
unchanged.

Unknown usernames follow a dummy hash-verification path and receive the same
invalid-credentials error as incorrect passwords. Raw random 256-bit tokens cross
only into HTTP cookie setters. The internal `AuthSession` model stores token
SHA256 digest as `session_id`, `user_id` foreign key, `expires_at` Unix timestamp,
and `credential_version` digest of the account's username/hash. Sessions expire
after eight hours and survive restarts. Login rotates the previous browser session
and prunes expired rows via `delete_expired_sessions(now) -> int`. A removed account
or edited username/hash invalidates existing sessions at the next request.

Startup creates the session table in both new and existing databases; schema version
3 includes the pricing migration described above without overwriting seeded application records. Session rows use
the database controller's typed CRUD and transaction contract. Credentials remain
in CSV, so the public `users` table needs no credential migration.

Hotel search stays public. The HTTP controller authenticates all booking routes
and derives the owner from the session; arbitrary submitted owner IDs cannot grant
access. Status/deletion controllers receive `owner_user_id` and check ownership
inside the write transaction. A foreign booking is indistinguishable from a
missing one (404). The View restores `/api/auth/me` on mount, uses the signed-in
identity instead of a traveler picker, clears private state on sign-out/401, and
keeps secrets out of local storage.

## Controller–View HTTP contract

`backend/models/contracts.py` defines request/response schemas. FastAPI exposes
these through `/openapi.json`; frontend `src/api/` modules consume that JSON
contract. `controllers/http.py` owns routing, request validation, serialization,
and error mapping. Route handlers delegate business operations to controllers.

| HTTP operation | Request | Successful response |
| --- | --- | --- |
| `GET /api/health` | None (public) | 200, `{status: "ok", geoapify: "key is configured"}` or `geoapify: "key is not configured"` |
| `GET /api/demo/zip-location` | None (public); fixed ZIP `16802` | 200, `ZipLocationResponse`: postcode, country_code, latitude, longitude, nullable locality |
| `GET /api/zip-location` | Required `postcode` query (public); exactly five ASCII digits | 200, same `ZipLocationResponse` as the demo |
| `GET /api/stays` | Required `hotel_name` query; optional session | 200, current prices without recording a search |
| `POST /api/stays` | Exactly `{hotel_name}`; optional session, CSRF header | 200, prices including this submission in the signed-in user's count |
| `GET /api/users` | Valid session | 200, array containing only signed-in public identity |
| `GET /api/bookings` | Valid session; optional matching `user_id` query | 200, array of booking history results |
| `POST /api/bookings` | Valid session, `{trip_id}`; optional matching `user_id` | 201, booking result |
| `PATCH /api/bookings/{booking_id}` | Valid session, own booking, `{status}` | 200, booking result |
| `DELETE /api/bookings/{booking_id}` | Valid session, own booking ID | 204, no body |
| `POST /api/auth/register` | `{username, display_name, password}` | 201, public user identity plus session cookie |
| `POST /api/auth/login` | `{username, password}` | 200, public user identity plus session cookie |
| `GET /api/auth/me` | Valid session | 200, public user identity |
| `POST /api/auth/logout` | Optional session | 204, revoked session and cleared cookie |

Both ZIP routes use `ZipLocationResponse` and `ZipLookupErrorResponse` from the JSON
contract module. They map configuration errors to 503, unresolved ZIP to 404, and
provider errors to 502 with safe `{detail}` messages, never exception text. The
404 message identifies the validated requested ZIP. Success and error responses
use `Cache-Control: no-store`. The demo accepts no lookup input; query parameters
cannot override its fixed postcode. The entered-ZIP route requires a `postcode`
query constrained by `ZipPostcode` in `models/contracts.py`; missing or invalid
values return 422 before contacting the provider. Provider requests and domain
validation remain in the geocoding controller.

Health uses `HealthResponse` and `Cache-Control: no-store`. At startup,
`controllers/configuration.py` loads `.env` from the project root derived from
the helper's file path, preserving existing environment variables. It reads
`GEOAPIFY_API_KEY` and retains only a boolean for health responses. Absent, empty,
or whitespace-only values are not configured. Restart the backend after edits.
Health reports API liveness and configuration presence, without checking key
validity or calling Geoapify.

Registration/login responses and `/api/auth/me` expose only `user_id` and `display_name`.
Duplicate registration usernames are 409; invalid registration fields are 422.
Invalid credentials and missing/expired sessions are 401; storage failures are
500. Cookie attributes are HTTP-only, host-only, SameSite=Lax, `/api` path, and
secure when `EXPEDIA_SECURE_COOKIES=true`. HTTPS deployments require that setting;
local HTTP development keeps it off. Auth/booking/user/search responses use `no-store`.
Every mutating API request requires `X-Requested-With: XMLHttpRequest` (403 if
missing). The same-origin View adds this header; credentialed cross-origin CORS
is not enabled, so a foreign browser origin cannot approve the required preflight.

Search requests with no session remain public and return base prices. A supplied
invalid or expired session returns 401 so the View clears private state. POST
searches reject unknown fields, including supplied user IDs/prices; blank text
returns `[]` without recording. On sign-in the View refreshes the last submitted
query with GET, preserving counts; sign-out/expiry clears personalized results.

Creation trims ID strings and requires 1–64 characters after trimming. Unknown
request-body fields are rejected; status is limited to `confirmed`/`cancelled`.
Missing entities are 404, booking conflicts 409, invalid requests 422, and storage
failures 500. A requested history/creation owner different from the session is 403.
Non-success JSON includes `detail` (a string for domain failures,
validation details for 422). Collections are arrays even when empty. Dates are
`YYYY-MM-DD` strings; dollar amounts are decimal strings, preserving exact cents.

The View collects input, requests data, and manages selection/loading/error state.
It formats dates/currency and sorts returned results for presentation. It never
calculates authoritative prices, assigns booking IDs/status policy, or accesses
persistence. The CLI renders its own text table from the same controller outputs.

## Browser View and interaction state

`App.vue` coordinates search, authentication, selection, and booking history.
`StayCard.vue`, `SignInForm.vue`, and `CreateAccountForm.vue` own reusable
presentation. API adapters share `src/api/request.js` for same-origin cookies,
the mutation header, response parsing, and errors. Registration places display
name before username and gives a short password hint; field errors explain the
remaining constraints without exposing submitted credentials.

The cream/navy/yellow layout presents horizontal stay cards beside the booking
panel on desktop, then stacks sections on smaller screens. History uses two
columns on larger screens and one on mobile. Cards distinguish nightly rates
from stay totals and explicitly label photo placeholders. Ratings, amenities,
flights, and bundle savings are absent because the API does not supply them.
`src/utils/stays.js` sorts returned totals numerically while preserving the
original result/selector order. All offered dates come from fixed trips.

Choosing a stay moves focus to the relevant booking or account form and respects
reduced-motion preferences. Inputs have labels, busy actions are disabled, and
errors/status messages use alert or live regions. Successful sign-in and
registration refresh the last submitted search with GET before loading history.
Search revision checks discard stale responses after a newer request or account
clearing; booking-history responses are checked against the active identity.
The browser never supplies a rate, and creation uses the server's policy at that
moment rather than treating an earlier search result as a locked quote.

## Verification and scope

Backend pytest coverage exercises model validation, MVC/storage contracts,
transaction rollback, API ownership and CSRF, session lifecycle, registration
recovery and concurrency, pricing thresholds and EST boundaries, saved rates,
and schema upgrades. Frontend Node tests cover API adapters, rendered form/card
markup, sorting, and search/account state with mocked requests. They do not
constitute browser end-to-end or visual layout verification. See the handoff for
the latest commands, counts, and warnings.

The application remains a fixed-stay assignment prototype: no room inventory,
payment processing, taxes/fees, city/date filters, or production deployment is
implemented. The API/controller can restore cancelled bookings; the browser
currently offers cancellation and deletion only. Registration's file lock uses
POSIX `fcntl`; hosting must support it and provide writable persistent CSV and
SQLite storage. HTTPS hosting also needs secure cookies and one browser origin
for the View and API.

## Assignment 2 Part 2 storage

Schema version 4 additively creates `saved_hotels` and `demo_hotel_nights` during
normal database initialization, on both existing and fresh databases. Repeated
initialization preserves all rows; Assignment 1 tables and CSV imports are unchanged.
No API or frontend contract changes, automatic API saves, or demo-night generation
are introduced in this step. Both new tables start empty.

The frozen nearby hotel response maps `place_id` to `saved_hotels.hotel_id`
(verbatim text, case-sensitive primary key); `name`, `address`, `latitude`, and
`longitude` map to identically named columns. Storage allows NULL names and
addresses when unavailable. The existing Part 1 filtering and response behavior
remain unchanged. Coordinates are required numbers within latitude ±90 and
longitude ±180. The provider ID is independent of Assignment 1 hotel IDs.

`demo_hotel_nights` references `saved_hotels.hotel_id`, restricts parent deletion,
and has a composite primary key `(hotel_id, stay_date)`. Dates must be valid
calendar dates in `YYYY-MM-DD` format. Rates and room counts must be nonnegative
integers and default to 10000 cents ($100.00) and 20 rooms. These are fictional
classroom defaults, never provider-supplied pricing or availability. SQLite
foreign-key enforcement is enabled by `connect_database`; DB Explorer connections
must also enable `PRAGMA foreign_keys = ON` when writing.

### Local hotel workflows (schema version 5)

The Part 1 provider endpoints and JSON fields remain frozen. Local storage now
adds `saved_hotel_zip_locations`, keyed by hotel ID and five-digit postcode, with
foreign-key deletion restricted. It stores the searched U.S. ZIP's latitude,
longitude, optional locality, and the returned hotel distance separately from the
hotel's own coordinates. It permits one hotel to be associated with multiple ZIPs.

`models/local_hotel.py` defines immutable SavedHotel, HotelZipAssociation,
DemoHotelNight, and LocalHotelResult. `controllers/local_hotels.py` owns workflows
through public typed database-controller methods. Save runs in a write transaction,
inserting absent rows only, including all five dates October 10–14, 2026 inclusive.
Default rates and room counts remain 10000 cents and 20. Existing hotel metadata,
ZIP contexts, rates, and availability are preserved on repeated saves. Removal
explicitly deletes all associated ZIP and night rows before the hotel in one
transaction; a failure rolls everything back. ZIP reads use a consistent snapshot.
Assignment 1 records and CSV files are untouched.

The additional public endpoints are:

- `GET /api/local-hotels?postcode=02108`: array of stored provider-shaped hotel
  fields plus `location` (the ZIP response schema) and `demo_nights` (ISO date,
  decimal-string nightly_rate_usd, nonnegative integer rooms_available). Ordered
  by stored distance, name, then exact provider ID. No matches returns `[]`.
- `GET /api/local-hotels/ids`: sorted array of all exact saved provider IDs,
  including hotels saved under other ZIPs or without ZIP associations.
- `POST /api/local-hotels`: `{hotel, location}`; hotel fields are place_id, nullable
  name/address, latitude/longitude, and distance_m. Location includes postcode,
  country_code="us", ZIP latitude/longitude, and optional locality. Returns 201
  with the stored result, including on an idempotent repeated save. Unknown fields,
  submitted rates/inventory, invalid coordinates, distances, or ZIPs return 422.
- `DELETE /api/local-hotels`: `{place_id}` in the JSON body preserves opaque IDs
  without URL normalization. Returns 204 with no body, or 404 if absent.

Schemas remain sourced from `models/contracts.py` and `/openapi.json`. Every local
response uses `Cache-Control: no-store`; write requests require the existing
X-Requested-With header. Storage failures return fixed safe 500 messages.
The shared classroom demo intentionally does not require authentication.

The View requests local hotels first. A local match displays the stored center,
local hotels, dated simulated rates and room counts, labeled "Saved locally" and
explicitly described as an incomplete saved subset. A successful empty result
refreshes global saved IDs and then uses the existing ZIP and hotel API routes,
labeled "API results". Local lookup/status errors do not trigger provider fallback.
No requests run automatically on mount; re-entering a ZIP after refresh reads the
database. Add/Remove buttons are siblings of the accessible card selection button.
ZIP controls are blocked during pending mutations, and state changes only after
successful writes. Removing a local result removes its card/marker; removing an
API result's saved copy keeps its API card and selection.

The earlier Part 2 storage-only milestone started with empty tables; these new
workflows now populate them only when the user explicitly saves a hotel.

## Hotel assistant chat (schema version 6)

`models/chat.py` defines immutable `ChatMessage(role, content)`,
`ChatConversation(messages)`, and `ChatReply(reply, suggestions=())` results. Messages are trimmed,
nonblank plain text with only user/assistant roles, alternating starting and ending
with user. Limits remain 8,000 characters per message, 1–21 messages, and 32,000
characters total. Invalid inputs raise `ValueError` before writes/provider access.
Suggestions are immutable tuples of up to three distinct, trimmed nonblank strings
of at most 160 characters. They are optional follow-up actions, not chat messages.

`prompts/hotel-assistant.md` is the separate LLM instruction file; AGENTS.md supplies
repository rules only. `controllers/chat_prompt.py` reads it using its own absolute
project path once during FastAPI lifespan startup, independent of the working
directory. Missing, unreadable, or empty instructions stop startup with a safe error.
The loaded text is included in both provider calls. Restart the backend after
Markdown prompt edits; Python reload does not guarantee detection.

The prompt documents the actual columns from `models/schema.py`:

| Relation | Columns |
| --- | --- |
| saved_hotels | hotel_id, name (nullable), address (nullable), latitude, longitude |
| saved_hotel_zip_locations | hotel_id, postcode, country_code, latitude, longitude, locality (nullable), distance_m |
| demo_hotel_nights | hotel_id, stay_date, nightly_rate_cents, rooms_available |

The first JOIN matches `saved_hotels.hotel_id` to
`saved_hotel_zip_locations.hotel_id` and filters the five-digit `postcode` text,
preserving leading zeros. Associations describe the searched ZIP, independently
of hotel coordinates. The second JOIN matches `demo_hotel_nights.hotel_id` to the
hotel ID to retrieve dated rates and room counts. Queries apply requested dates
and minimum rooms and order by numeric price with stable hotel-ID ties. Cents
convert using `/ 100.0`, displayed as dollars with two decimals. Check-in is
inclusive and checkout exclusive; eligible stays require records and sufficient
rooms on every night. Missing records mean unknown availability, not zero rooms.
LEFT JOIN date conditions belong in ON when reporting missing records. Prompt
examples cover single nights and complete multi-night stays. Results represent
only the saved subset; rates and rooms are always simulated classroom data.

`controllers/chat.py` exposes
`reply_to_chat(messages: tuple[ChatMessage, ...], *, database_path=DEFAULT_DATABASE_PATH,
conversation_id=None, prompt=None) -> ChatReply`. Direct callers initialize the
database first; HTTP startup performs initialization. Each turn:

1. Commits the current user message (not replayed browser context).
2. Sends the conversation and loaded schema/purpose instructions to Gemini to
   propose exactly one SELECT query without Markdown.
3. Commits the generated SQL, then validates it without execution.
4. Commits the exact bounded SQL to be submitted, executes it on a separate guarded
   read-only connection, and commits a summary (columns, row count, empty/truncated).
5. Sends the original question and retrieved rows to Gemini in a second request,
   with instructions to answer only from records, acknowledge empty/truncated
   results, explain unknown dates, and label simulated data. This request also
   generates follow-up questions tailored to the latest question and its answer.
6. Validates the structured answer/suggestions envelope, commits the final
   assistant message, and returns the answer and suggested actions to the View.

No database transaction spans a provider call. Each workflow owns/closes one
`google-genai` client. Both text-only Interactions requests use `store=False`, a
30-second timeout, no automatic retries, and a 1,024-token output limit.
User/assistant context maps to user_input/model_output steps; retrieved rows are
JSON in a user_input step, never system instructions. The SDK Interactions retry
configuration is disabled explicitly. Only completed, nonblank, bounded text is
accepted. Fake HTTP transports verify serialization and failure behavior.
The second request sets response_format to type=text, mime_type=application/json with the
ChatResponse JSON schema from models/contracts.py. The first still returns SQL
text. No third request is added. The backend rejects malformed JSON, extra fields,
blank/duplicate/oversized suggestions, or invalid answers with a safe provider
error, preserving previous workflow logs. Only reply text is saved as the assistant
message; suggested actions are not inserted into conversation history.

`models/hotel_query.py` defines the narrowly scoped immutable `HotelQuery(sql)`
and `HotelQueryResult(columns, rows, truncated)` contracts. This is the sole SQL
input exception to typed controller boundaries. Only the database controller
opens SQLite or issues SQL. `validate_hotel_query(query) -> HotelQuery` uses
SQLite EXPLAIN to compile both the standalone query and its outer LIMIT wrapper
without execution. This rejects multiple statements and attempts to escape the
wrapper. `execute_hotel_query(query) -> HotelQueryResult` revalidates on its own
handle. Both use mode=ro, query_only, trusted_schema off, and a default-deny
SQLite authorizer for every nested read/function. Only the three hotel tables and
the documented ordinary scalar/aggregate functions are permitted. Writes, DDL,
PRAGMA, ATTACH, extension/file access, recursive CTEs, metadata/private tables,
and table-valued functions are blocked. Nonrecursive WITH is supported.

Queries have an 8,000-character input limit, 100 returned rows (101 fetched to detect
truncation), a 32,000-character serialized result bound, and a one-second deadline
enforced by SQLite's progress handler and bounded lock waiting. SQLite also limits
SQL/column/expression/value/bytecode sizes. Results are immutable JSON scalars,
never SQLite rows. Rejected proposals raise `HotelQueryRejectedError`; deadline
failures raise `HotelQueryTimeoutError`. The chat controller maps both to safe
`ChatQueryError`. Storage failures map to `ChatDataError`.

The additive schema version 6 creates `conversation_history`:

| Column | Contract |
| --- | --- |
| message_id | Unique version-4 UUID text primary key |
| conversation_id | Version-4 UUID grouping a page-memory chat, indexed |
| timestamp | Nonnegative Unix milliseconds (UTC) |
| role | user, assistant, or system |
| content | Nonblank text, at most 16,000 characters |
| record_type | message, generated_sql, executed_sql, result_summary, or error |

`models/conversation.py` validates immutable `ConversationRecord` objects.
`DatabaseController.append_conversation_record(record) -> None` commits each
trusted write independently of hotel reads. User/assistant messages have
record_type=message; workflow records use role=system with distinct record types.
Executed SQL means the validated statement submitted for execution, including its
outer LIMIT; a subsequent timeout/error records failure, not successful completion.
Error records contain only stage and fixed safe classification, never raw exceptions,
URLs, keys, or provider metadata. Earlier records survive later failures. An audit
write failure stops the workflow. Internal `list_conversation_records(id)` returns
records in insertion order; no public transcript endpoint exists. The read-only
hotel authorizer cannot access this table. Reinitialization preserves all records,
local data, and Assignment 1 tables/CSV data.

Configuration remains backend-only `GEMINI_API_KEY` and optional `GEMINI_MODEL`,
loaded from root .env with process overrides. Missing/blank keys are unconfigured;
the default is gemini-3.8-flash. Restart after edits. Health is unchanged.

Public `POST /api/chat` accepts messages plus an optional version-4 UUID
conversation_id; other fields, system roles, and invalid conversations return 422.
The source of truth remains ChatRequest/ChatMessageRequest/ChatResponse/
ChatErrorResponse in models/contracts.py and /openapi.json. Success is 200 with
exactly `{reply, suggestions}`. Suggestions serialize as an array, including empty
arrays, with at most three strings of at most 160 characters. Missing
X-Requested-With: XMLHttpRequest is 403; configuration is
503; storage is sanitized 500; provider and rejected-query failures are sanitized
502. Provider 503 and wrapped transport timeouts retain their distinct fixed safe
messages. Classification uses numeric statuses and exception types, not raw text.
All responses use no-store. Chat is public and can read only shared classroom
hotels, never identities, credentials, sessions, or Assignment 1 bookings.

The View's API adapter bounds context to 10 recent complete exchanges plus the
current question. ChatAssistant.vue preserves its accessible nonmodal popup,
plain-text rendering, Enter/Shift+Enter behavior, focus return on close/Escape,
loading, retry, and reset. Failed exchanges restore the draft and are excluded
from subsequent context. A page-memory UUID groups turns and retries; New chat
creates a new UUID and clears the local transcript, without deleting server logs.
Starter questions appear before the first exchange. Successful answers replace
them with generated follow-ups below the transcript. While busy they are hidden;
failed turns and closing the popup preserve the previous successful set. New chat
restores the starters. The API adapter validates suggestions; clicking one sends
that text through the usual bounded conversation flow. The View renders both
answers and suggestions as escaped text. The introductory help paragraph and
keyboard/storage footer are removed as requested, along with their accessibility
references; errors remain associated with the composer. Server persistence and
simulated rates remain documented in README and in the assistant's answer rules.
No browser storage is used. The frontend receives answers and suggested questions,
not SQL or internal logs.

Tests cover actual prompt columns/JOIN examples, ZIP/date/room filtering, whole
stays and missing nights, numeric conversion/order, authorization bypasses, row/size/
time limits, incremental durable logs, safe errors, two-request SDK serialization,
conversation grouping/reset, generated suggestion validation/refresh/retry/reset,
removed-text accessibility references, startup prompt snapshots, and additive initialization.
Tests use temporary databases and fake providers without real keys or live LLM calls.
