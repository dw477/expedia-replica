# MVC Architecture

The application uses Vue as its browser View and Python/FastAPI controllers over
SQLite. UI and CSS stay in `frontend/`. The optional plain-text search View lives
in `frontend/cli.py`. `backend/app.py` exposes the ASGI app and factory; old backend
module paths remain thin compatibility entry points.

## Models identified from the supplied CSVs

The CSVs have 8 hotels, 6 users, 12 trips, and 6 bookings. Each ID column is unique;
all 12 hotel references and all 12 booking references resolve. Hotels H001–H003
and H007 have multiple trips. U001 has two bookings; U006 has none. There are four
confirmed and two cancelled bookings, with no duplicate confirmed user/trip pair.

| Model | Fields | Relationships |
| --- | --- | --- |
| Hotel | `hotel_id`, `hotel_name`, `city`, `state`, `nightly_rate_usd` | One hotel has many trips |
| User | `user_id`, `display_name` | One user has many bookings |
| Trip | `trip_id`, `hotel_id`, `trip_name`, `check_in`, `check_out` | References one hotel; has many bookings |
| Booking | `booking_id`, `user_id`, `trip_id`, `booked_on`, `status` | References one user and one trip |

A booking associates a user with a trip, forming the user/trip many-to-many
relationship. It has its own stable ID because cancellation retains history and
subsequent bookings may refer to the same pair. A trip is a fixed-date hotel stay;
no flight, payment, authentication, or room-inventory model is implied by this data.

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
| `get(Model, id)` | Hotel/User/Trip/Booking class and text ID | Validated entity; missing IDs raise |
| `list(Model)` | Supported entity class | Entity list ordered by ID |
| `create(entity)` | Complete validated entity | Persisted entity |
| `update(entity)` | Complete validated entity under its existing ID | Updated entity; cannot rename IDs |
| `delete(Model, id)` | Supported class and text ID | `None`; missing IDs raise |
| `transaction(write=True)` | Write/read mode | Context yielding the controller with one shared connection |

CRUD supports all four models. Reads never return SQLite rows or open connections.
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
Subsequent initialization audits references without re-importing, preserving new,
updated, and deleted records. Existing databases use the same schema; this change
requires no destructive migration.

## Business controller contracts

Business controllers use public database-controller methods, not SQL or private
connections. Both take an optional `database_path` for isolated testing.

| Controller operation | Input | Output |
| --- | --- | --- |
| `search_available_stays` | `hotel_name`, optional database path/seed directory | `list[HotelAvailability]` |
| `list_users` | Optional database path | `list[User]` in ID order |
| `list_booking_history` | `user_id`, optional database path | `list[BookingHistoryEntry]` |
| `create_booking` | `user_id`, `trip_id`, optional path/`booked_on` date | Confirmed `BookingHistoryEntry` with generated ID |
| `update_booking_status` | `booking_id`, `status`, optional path | Updated `BookingHistoryEntry` |
| `delete_booking` | `booking_id`, optional path | `None` |

`controllers/search.py` matches a hotel-name substring after trimming and
case-folding. Results are ordered by trip ID; blank input and no matches return
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

## Controller–View HTTP contract

`backend/models/contracts.py` defines request/response schemas. FastAPI exposes
these through `/openapi.json`; frontend `src/api/` modules consume that JSON
contract. `controllers/http.py` owns routing, request validation, serialization,
and error mapping. Route handlers delegate business operations to controllers.

| HTTP operation | Request | Successful response |
| --- | --- | --- |
| `GET /api/stays` | Required `hotel_name` query | 200, array of availability results |
| `GET /api/users` | None | 200, array of `{user_id, display_name}` |
| `GET /api/bookings` | Required `user_id` query | 200, array of booking history results |
| `POST /api/bookings` | `{user_id, trip_id}` | 201, booking result |
| `PATCH /api/bookings/{booking_id}` | `{status}` | 200, booking result |
| `DELETE /api/bookings/{booking_id}` | Path ID | 204, no body |

Creation trims ID strings and requires 1–64 characters after trimming. Unknown
request-body fields are rejected; status is limited to `confirmed`/`cancelled`.
Missing entities are 404, booking conflicts 409, invalid requests 422, and storage
failures 500. Non-success JSON includes `detail` (a string for domain failures,
validation details for 422). Collections are arrays even when empty. Dates are
`YYYY-MM-DD` strings; dollar amounts are decimal strings, preserving exact cents.

The View collects input, requests data, and manages selection/loading/error state.
It formats dates/currency and sorts returned results for presentation. It never
calculates authoritative prices, assigns booking IDs/status policy, or accesses
persistence. The CLI renders its own text table from the same controller outputs.
