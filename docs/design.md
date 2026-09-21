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
