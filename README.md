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

- `GET /api/users`
- `GET /api/bookings?user_id=U001`
- `POST /api/bookings`
- `PATCH /api/bookings/{booking_id}`
- `DELETE /api/bookings/{booking_id}`

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

Do not commit credentials, API keys, or local environment files.
