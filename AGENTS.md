# Project Rules

These rules apply throughout the repository.

## Structure

- Keep client-side code in `frontend/` and server-side code in `backend/`.
- Keep shared contracts explicit. If API schemas or generated types are added, document where their source of truth lives.
- Prefer small, focused modules with names that describe their responsibility.

## Changes

- Preserve the existing architecture and conventions unless a requirement calls for changing them.
- Avoid unrelated refactors in feature and bug-fix changes.
- Never commit secrets, credentials, generated build output, dependency directories, or local environment files.
- Update `README.md` when setup steps, prerequisites, or top-level commands change.

## Quality

- Add or update tests for behavior changes.
- Run the relevant formatter, linter, type checker, and tests before considering work complete.
- Handle errors explicitly at system boundaries such as HTTP requests, input parsing, and persistence.
- Keep user-facing behavior accessible and responsive when working in the frontend.

## Documentation

- Explain non-obvious decisions near the code or in the relevant application documentation.
- Keep commands copy-pasteable and avoid documenting tools that are not actually configured.

## MVC Architecture and Contracts

- Follow Model–View–Controller (MVC). Keep immutable entity definitions, field
  validation, relationships, and result objects in `backend/models/`. Models must
  not import controllers, frontend code, HTTP handlers, or database connections.
- Keep screens, components, interaction state, presentation formatting, and CSS
  in `frontend/` (the View). Text interfaces live in `frontend/cli.py` and
  `frontend/hash_password.py`.
  The browser communicates with controllers through `frontend/src/api/`; it must
  never read CSVs, execute SQL, or calculate authoritative prices or booking rules.
  Display formatting and sorting already returned results are View responsibilities.
- Keep persistence and business operations in `backend/controllers/`. Only
  `controllers/database.py` may open SQLite, read seed CSVs, issue SQL, or manage
  transactions. SQLite DDL lives in `models/schema.py` as the storage contract.
  Do not put HTML, CSS, table rendering, or presentation formatting in controllers.
- The CSV-derived models are Hotel (`hotel_id`), User (`user_id`), Trip (`trip_id`),
  and Booking (`booking_id`). Hotel has many Trips; User and Trip each have many
  Bookings. `Trip.hotel_id`, `Booking.user_id`, and `Booking.trip_id` must reference
  existing parents. Preserve text IDs and restrict deletion of referenced parents;
  never silently cascade or leave orphan records.
- The Model–Controller input contract uses validated immutable entities, Python
  `date` objects, `Decimal` dollar amounts with whole cents, and statuses
  `confirmed`/`cancelled`. Persist money as integer cents and dates as ISO text.
  Nights and stay totals are derived result properties, never stored duplicates.
- The database-controller contract is `initialize(data_directory) -> bool`
  (true only when seeded), `get(Model, id) -> Model`, `list(Model) -> list[Model]`
  (ID order), `create(entity) -> entity`, `update(entity) -> entity`, and
  `delete(Model, id) -> None`. Updates take a complete replacement under the same
  ID; they do not rename IDs. Call initialize before CRUD on a new database.
  Do not pass SQL, arbitrary table names, or SQLite rows across controller boundaries.
- Database errors are explicit: `RecordNotFoundError` for missing entities or
  references, `ReferenceConflictError` for referenced-parent deletion,
  `RecordConflictError` for uniqueness/constraint conflicts, and `DatabaseError`
  for storage failures. Entity construction raises `ValueError` for invalid fields.
  Group workflows in `DatabaseController.transaction()` for atomic writes;
  `transaction(write=False)` provides a consistent read snapshot. Scope each
  controller instance to one workflow; do not share it between threads or nest
  transactions. Re-importing seed CSVs must never overwrite application changes.
- Put each business responsibility in its own controller. Search owns matching;
  bookings own creation, cancellation/restoration, and history. Controllers may
  call one another only through public typed methods and agreed result/error
  contracts. They must not access another controller's SQL, connection, or internals.
- The Controller–View JSON source of truth is `backend/models/contracts.py`,
  exposed by FastAPI's `/openapi.json`. `controllers/http.py` validates requests,
  serializes result models, and maps missing records to HTTP 404, booking conflicts
  to 409, invalid requests to 422, and storage failures to 500. Successful booking
  creation is 201; deletion is 204 with no body. Dates serialize as `YYYY-MM-DD`,
  money as decimal strings, and collections as arrays (including empty arrays).
  Booking creation requires `trip_id` and accepts an optional legacy `user_id`
  (trimmed non-empty strings, at most 64 characters). Derive the owner from the
  authenticated session and reject a supplied different user ID. Status updates
  accept only `status`; unknown fields are rejected.
- Search's public contract is `search_available_stays(hotel_name, database_path,
  data_directory, *, user_id=None, record_search=True) -> list[HotelAvailability]`,
  ordered by trip ID with case-folded, whitespace-collapsed substring matching;
  blank input returns `[]`, and failures raise `SearchDataError`.
  Booking methods return `User` or `BookingHistoryEntry` models; history is ordered
  by booking date and ID descending. They raise `BookingNotFoundError`,
  `BookingConflictError`, or `BookingDataError`; invalid status arguments raise
  `ValueError`. At most one confirmed booking is allowed per user/trip pair.
- Keep `backend/app.py` as the ASGI entry point. Existing `backend/database.py`,
  `backend/search.py`, and `backend/bookings.py` are compatibility entry points;
  add new implementation to the model/controller folders instead.
- Update these rules, API schemas, design documentation, and contract tests together
  when changing an input/output contract. See `docs/design.md` for fields, CSV
  analysis, public controller signatures, and HTTP routes.

## Search History and Pricing Contracts

- Store all users' search submissions in one `search_history` table. The immutable
  `models/search.py` `SearchHistory` has `search_id`, `user_id` (foreign key),
  normalized `search_query`, and `searched_at` (Unix seconds). Restrict deletion of
  users referenced by history. Normalize with case-folding and whitespace collapse.
- Only non-empty submitted searches by signed-in users are recorded, even with no
  matches. `POST /api/stays` takes exactly `{hotel_name}` and requires the CSRF
  header. `GET /api/stays` is a read-only refresh. Both use the optional session's
  identity and `no-store`; an invalid supplied session returns 401, absent sessions
  allow public base-price searches. The View refreshes prices on sign-in without
  recording another submission and clears personalized results on sign-out/expiry.
- `DatabaseController.list_search_counts(user_id, start, end)` returns immutable
  `SearchQueryCount` results grouped by normalized query, ordered by query, over
  the half-open Unix timestamp interval. Only the database controller issues SQL.
- `controllers/pricing.py` owns the policy shared by search and bookings: count
  queries separately for each user on the same EST day (fixed UTC−05:00), including
  the current submission. Counts 1–3 use base; 4+ use base × 1.2 without compounding.
  Any qualifying query matching a hotel's normalized name surges that hotel for
  that user for that day, including results from another query. Round nightly rates
  to whole cents with `ROUND_HALF_UP` before deriving stay totals.
- Search insertion, counting, and results share a write transaction. New bookings
  evaluate the same user/hotel policy within their creation transaction and save
  `Booking.nightly_rate_usd` as integer cents. History and cancellation/restoration
  retain this rate; hotel base rates never change through surge. The Booking model
  requires this validated Decimal field. No client-supplied rate is accepted.
- Schema version 3 adds history and stored booking rates. Initialization snapshots
  the currently displayed base rate for preexisting bookings once; subsequent runs
  preserve it. Seed bookings derive their initial rate through their trip/hotel;
  the four CSV formats remain unchanged. Nights and totals remain derived.

## Authentication Contracts

- Keep username/password verification and session rules in
  `backend/controllers/authentication.py`, password hashing/verification in
  `controllers/passwords.py`, and credential/session objects in
  `backend/models/authentication.py`. Keep forms, loading/errors, and CSS in the View.
- `data/users.csv` is the username/password-data source of truth. Its exact columns
  are `user_id,display_name,username,password_hash`. Store random-salted
  PBKDF2-SHA256 hashes with 600,000 iterations, never plaintext. Sample demo accounts
  are fictional public fixtures; do not add real credentials to the repository.
  `UserAccount` includes these CSV fields; `User` remains the public SQLite identity.
- Only the database controller may read/write credential CSVs or persist sessions.
  `list_user_accounts(data_directory) -> list[UserAccount]` validates unique usernames
  and user IDs, returns only accounts linked to existing SQLite users, and raises
  `DatabaseError` for parsing/storage failures. Removing a database user disables
  its CSV login. Account reads must not restore deleted identities or reseed data.
- Account creation accepts exactly username, display name, and password. Trim and
  case-fold usernames; trim display names and require non-empty text. Preserve
  existing 3–64 character username rules. New passwords must be 8–256 ASCII
  letters/digits or `!@$%&?`, with at least one uppercase letter, one digit, and
  one allowed special character. Do not apply this policy retroactively to login.
  Keep validation in `models/authentication.py` and request fields in
  `models/contracts.py`; never echo submitted credentials in validation errors.
- `AuthenticationController.register(username, display_name, password,
  previous_token=None) -> (User, raw_session_token)` allocates a `U`-prefixed UUID
  and signs the new account in. Invalid fields raise `ValueError`; duplicate
  usernames raise `AccountExistsError`; storage failures raise
  `AuthenticationDataError`. Usernames remain reserved while present in CSV,
  including when the corresponding SQLite identity has been deleted.
- `DatabaseController.register_user_account(account, session, data_directory,
  previous_session_id=None) -> User` owns its transaction and saves the CSV hash,
  public identity, and session together. It raises `AccountUsernameConflictError`
  for duplicate usernames and `DatabaseError` for storage failures. Serialize
  registrations with a stable file lock and atomic file replacement. A durable
  recovery journal restores the original CSV after an interrupted uncommitted
  save; the committed SQLite identity decides recovery. Keep locks, journals,
  temporary files, and real registered accounts out of Git. Read account files
  before entering a database transaction; do not nest registration in one.
- `/api/auth/register` accepts only `{username, display_name, password}`, returns
  201 with the public identity and the same session cookie as login, and rotates
  the previous browser session only on success. Duplicate usernames are 409;
  invalid fields are 422; storage failures are 500. The View offers registration
  and sign-in forms and immediately loads the new signed-in account's bookings.
  Place display name before username in registration. Show a small password hint
  with only the minimum character count and required character types; do not list
  special characters. Present other entry requirements in clear error messages
  when validation fails.
- `AuthenticationController.login(username, password, previous_token=None)` returns
  `(User, raw_session_token)` or raises `InvalidCredentialsError` /
  `AuthenticationDataError`. Username matching trims and case-folds input; CSV names
  are canonical lowercase 3–64 character names. Password input is 1–256 characters
  and preserves case/whitespace. Use constant-time digest comparison and perform
  a dummy password derivation for unknown usernames.
- `current_user(token) -> User` raises `AuthenticationRequiredError` for absent,
  forged, expired, revoked, or disabled sessions; storage errors raise
  `AuthenticationDataError`. `logout(token) -> None` revokes a session and is
  idempotent. Scope authentication-controller instances to individual workflows.
- `AuthSession` is an internal model with `session_id` (SHA256 token digest),
  `user_id` (foreign key), `expires_at` (Unix seconds), and `credential_version`
  (digest of the CSV username/hash). Persist only digests, never raw session tokens.
  Sessions expire after eight hours; login rotates/revokes the previous browser
  token and prunes expired records via `delete_expired_sessions(now) -> int`.
  CSV credential changes invalidate existing sessions on their next request.
- `/api/auth/login` accepts only `{username, password}` and returns the public
  `{user_id, display_name}` with an HTTP-only, host-only, SameSite=Lax `/api` cookie.
  `/api/auth/me` returns that same public schema; `/api/auth/logout` returns 204
  and clears the cookie. Never expose password hashes, session digests, or raw
  tokens in response bodies, logs, URLs, or frontend storage. Private responses
  must use `Cache-Control: no-store`. Use secure cookies for HTTPS deployments.
- Keep hotel searches public. Require a valid session on `/api/users` and every
  booking route. `/api/users` returns only the signed-in user's identity; history
  defaults to that account. Access to another user's history or creation as another
  user returns 403. Pass `owner_user_id` to booking status/deletion controllers so
  they check ownership inside the write transaction; another user's booking is 404.
  Trusted internal booking calls may omit this argument; HTTP handlers must pass it.
- Every mutating `/api/` request, including registration/login/logout, requires
  `X-Requested-With: XMLHttpRequest`. The View's request adapter adds this header
  and uses same-origin cookies. Do not enable cross-origin credentialed CORS
  without revisiting CSRF protection. Invalid credentials or sessions are 401;
  credential/session storage failures are 500; missing CSRF headers are 403.
- The View must clear private booking data on sign-out or session expiry and restore
  the current session on page load. It must not let users choose a different owner.
