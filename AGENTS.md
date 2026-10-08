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
  Do not pass arbitrary table names or SQLite rows across controller boundaries.
  The only SQL input exception is the typed, untrusted `HotelQuery` proposal for
  the hotel assistant, checked by the database controller's default-deny guard.
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
- `controllers/configuration.py` loads the project-root `.env` at backend startup
  using its own file path, preserving process environment overrides. Public
  `GET /api/health` returns `{status: "ok", geoapify: "key is configured"}` or
  `geoapify: "key is not configured"` with `no-store`. Missing, empty, and
  whitespace-only keys are not configured. Never return the key or contact
  Geoapify for this check; restart the backend after configuration edits.
- Update these rules, API schemas, design documentation, and contract tests together
  when changing an input/output contract. See `docs/design.md` for fields, CSV
  analysis, public controller signatures, and HTTP routes.
- `controllers/geocoding.py` exposes `lookup_zip(postcode: str) -> ZipLocation | None`.
  Accept exactly five ASCII digits; invalid input raises `ValueError`. Use Geoapify
  forward geocoding with postcode/type=postcode/filter=countrycode:us/format=json
  and the configuration helper's backend-only key, with a finite timeout. Return
  only an exact U.S. postcode result with valid coordinates; no acceptable match
  returns `None`. Configuration failures raise `ZipConfigurationError` (a
  `ZipLookupError` subclass); provider failures raise sanitized `ZipLookupError`.
  `models/location.py` owns the immutable postcode/country_code/latitude/longitude/
  optional locality result, separate from Hotel. Never expose credentials, full
  provider URLs, or raw exception text. Public `GET /api/demo/zip-location` calls
  this controller with fixed `"16802"`, returning `ZipLocationResponse` on 200,
  or a fixed safe `{detail}` error: 503 for configuration, 404 for unresolved ZIP,
  502 for provider failure. Public `GET /api/zip-location?postcode=02108` accepts
  a required postcode of exactly five ASCII digits, preserving leading zeros,
  and uses the same controller, response schema, and error mapping. Invalid or
  missing input returns 422 before provider access. `ZipPostcode` in
  `models/contracts.py` defines the HTTP input constraint. All responses use
  `no-store`. The View's ZIP form and fixed demo button call these backend routes
  through `frontend/src/api/` and share the same location results display. Keep
  their request state separate from hotel search and disable both buttons while
  busy. User-entered five-digit U.S. ZIP codes are supported alongside `"16802"`.

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

## Assignment 2 Local Hotel Contracts

- Preserve the Part 1 `/api/zip-hotels`, ZIP lookup schemas, provider search, and
  list/map selection. Local storage uses separate schemas/routes; it never writes
  Assignment 1 hotels, trips, bookings, users, or supplied CSVs.
- `models/local_hotel.py` owns immutable `SavedHotel`, `HotelZipAssociation`,
  `DemoHotelNight`, and `LocalHotelResult`. Map API `place_id` verbatim to the
  saved hotel's text primary key. Nullable name/address remain nullable.
- Schema version 5 adds `saved_hotel_zip_locations` keyed by `(hotel_id, postcode)`
  with a restricted hotel FK, ZIP point/country/locality, and returned distance.
  Store the searched ZIP context independently of hotel coordinates. Migrations
  are additive and repeatable. Only the database controller issues SQL.
- `LocalHotelsController.save(hotel, association) -> LocalHotelResult` atomically
  inserts only missing hotel/association rows and the five inclusive dates
  2026-10-10 through 2026-10-14, using schema defaults 10000 cents and 20 rooms.
  These are simulated classroom data. Repeated saves never overwrite rates,
  inventory, hotel fields, or existing ZIP contexts. `list_for_zip(postcode)`
  returns typed local results ordered by distance/name/provider ID using a read
  snapshot; `list_ids()` returns all exact saved IDs; `remove(hotel_id)` deletes
  the hotel, all ZIP associations, and all demo nights in one write transaction.
- Public `GET /api/local-hotels?postcode=02108` returns an array with provider
  fields plus stored `location` and dated `demo_nights` (decimal-string
  `nightly_rate_usd`, integer `rooms_available`). `GET /api/local-hotels/ids`
  returns a string array. `POST /api/local-hotels` accepts exactly `{hotel,
  location}`, with only provider fields in `hotel`, and returns 201 with the
  stored result. No submitted prices/inventory are accepted.
  `DELETE /api/local-hotels` accepts exactly `{place_id}` and returns 204;
  JSON keeps opaque IDs out of URL normalization. Missing records return 404,
  invalid inputs 422, storage failures sanitized 500. All responses use no-store;
  mutations require the existing CSRF header. This is shared classroom storage.
- ZIP search first requests local hotels, uses stored location and demo values on
  a match, and only falls back to Part 1 after a successful empty local result.
  Local failures stop lookup. Before showing API cards, refresh global saved IDs
  from the database. Mark saved/removed only after success; prevent duplicate
  pending mutations and ZIP changes during a mutation. Keep selection buttons
  separate from Add/Remove. Label local results as a saved subset, never a complete
  area listing, and label all rates/rooms as simulated classroom data.

## External LLM Chat Contracts

- `models/chat.py` owns immutable `ChatMessage`, `ChatConversation`, and `ChatReply`.
  Messages are trimmed, nonblank text of at most 8000 characters, with only
  `user`/`assistant` roles. Conversations have 1–21 alternating messages, starting
  and ending with user, with at most 32000 total characters.
- `controllers/chat.py` exposes
  `reply_to_chat(messages: tuple[ChatMessage, ...], *, database_path,
  conversation_id=None, prompt=None) -> ChatReply`. Invalid input
  raises `ValueError` before provider access. Missing configuration raises
  `ChatConfigurationError`; SDK/transport or unusable response failures raise
  sanitized `ChatProviderError`. Use a per-workflow `google-genai` client, finite
  30-second timeout, no automatic retries, and a 1024-token output limit. Map
  messages to text-only Interactions steps; require completed, usable text replies.
  Each successful turn makes two requests: first propose a hotel SELECT from the
  question/schema, then answer from the original question and retrieved rows.
  The second request uses a JSON response schema for a plain-text `reply` and
  up to three distinct `suggestions`, each trimmed, nonblank, and at most 160
  characters. Generate these follow-up questions from the latest question and
  answer in that same request; no additional provider call. Validate the entire
  envelope before returning it; malformed envelopes raise `ChatProviderError`.
  Provider HTTP 503 raises `ChatUnavailableError`; wrapped transport timeouts
  raise `ChatTimeoutError` (both `ChatProviderError` subclasses). Classify using
  numeric status and exception types, never raw messages. Logs contain only fixed
  safe descriptions of outages/timeouts.
- Keep `GEMINI_API_KEY` and optional `GEMINI_MODEL` in backend configuration,
  loading root `.env` with process overrides. Default to `gemini-3.8-flash`.
  Never expose credentials, provider URLs, raw SDK errors, or provider metadata.
  Restart after configuration changes; preserve the existing health contract.
- Store assistant purpose, actual schema, both hotel-ID JOINs, ZIP/date/room
  filters, numeric price ordering, cents-to-dollars conversion, missing-date
  semantics, and simulated-data labels in `prompts/hotel-assistant.md`.
  Load this file once at backend startup and include it in both LLM requests;
  restart after editing. AGENTS.md is repository guidance, not the LLM prompt.
- `models/hotel_query.py` owns immutable `HotelQuery`/`HotelQueryResult` contracts.
  Only `DatabaseController.validate_hotel_query`/`execute_hotel_query` accept
  proposals. Permit one SELECT (optional nonrecursive WITH) reading only
  `saved_hotels`, `saved_hotel_zip_locations`, and `demo_hotel_nights`. Parse with
  SQLite before execution; default-deny authorization covers nested reads and
  functions. Use a separate mode=ro, query-only connection, no extensions, a
  backend outer LIMIT, 100 returned rows, a 32,000-character result bound, and
  a one-second execution deadline. Deny writes, private tables, schema inspection,
  PRAGMA, ATTACH, recursive CTEs, multiple statements, and unsafe functions.
  Revalidate on the execution handle. Rejected/timed-out queries raise
  `HotelQueryRejectedError`/`HotelQueryTimeoutError`, mapped to `ChatQueryError`;
  storage failures raise `ChatDataError`. Missing dated records mean unknown
  availability; a multi-night stay requires sufficient rooms on every night.
- Public `POST /api/chat` accepts `{messages: [{role, content}, ...]}` and an
  optional version-4 UUID `conversation_id` for grouping server records, and
  returns exactly `{reply, suggestions}` on 200. `suggestions` is a string array,
  including an empty array when appropriate. Reject unknown fields/system roles with 422;
  configuration failures return fixed safe 503, provider/query failures fixed
  safe 502, and storage failures fixed safe 500.
  Require the existing CSRF header (403 if absent), and use no-store on all replies.
  HTTP schemas remain in `models/contracts.py` and `/openapi.json`.
  Provider outages return "Gemini is temporarily unavailable. Please try again
  in a moment." Timeouts return "Gemini took too long to reply. Please try again."
  These remain 502; other provider failures keep the generic safe message.
- Keep chat state, accessible log/composer, loading, retry, and reset in the View;
  call the backend only through `frontend/src/api/chat.js`. Send up to 10 recent
  complete exchanges plus the current question, dropping oldest pairs to fit the
  character bound. Prevent duplicate submits/reset while busy; restore failed
  drafts without adding failed exchanges to history. Render escaped plain text.
  A floating launcher and navigation button open a responsive nonmodal popup;
  closing/Escape restores focus to the opener and preserves drafts/history.
  Pending replies may finish while closed without stealing focus.
  Show starter questions before the first exchange and replace them with the
  latest successful answer's suggestions below the transcript. Hide suggestions
  while busy; failures preserve the previous successful set. New chat restores
  starter questions. Suggestions are optional actions, not transcript messages.
  Keep the chat-help paragraph and keyboard/storage footer removed; avoid stale
  aria-describedby references to those elements.
- Chat reads only shared Assignment 2 saved hotel data, never account information
  or Assignment 1 booking operations. Answer only from retrieved records,
  acknowledge empty/truncated results, and label rates/rooms as simulated
  classroom data. Do not connect the LLM to authoritative mutations.
- Schema version 6 adds `conversation_history`. `models/conversation.py` owns
  immutable records with message ID, conversation ID, Unix-millisecond timestamp,
  role, content, and record type. Store current user and final assistant messages
  separately (`role=user/assistant`, `record_type=message`); never duplicate replayed
  browser history. Log `generated_sql`, `executed_sql` (the exact bounded query
  submitted after validation), `result_summary`, and sanitized `error` records
  with role=system as each stage occurs, before advancing. Errors contain only
  stage and safe error code, never SDK/SQLite exception text or credentials.
  Database-controller log writes each commit in a separate trusted transaction;
  failures retain earlier steps. Hotel reads cannot access conversation history.
- The View keeps its transcript and a conversation UUID in page memory, without
  browser storage; follow-ups/retries reuse the UUID, and New chat creates another
  UUID without deleting server logs. Document server persistence in README.md.
  No public transcript-read API is provided; IDs group records, not authorize
  access. Continue using `store=False` on both provider interactions. Test with
  fake transports/responses rather than real keys or live LLM calls.
