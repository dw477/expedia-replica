# Expedia Assignment

## Goal

Build a small, maintainable travel application with a clear separation between the user interface and server-side responsibilities.

The specific product requirements and technology choices can be documented here as the assignment evolves.

## Project Layout

- `frontend/` contains the client application and its tests.
- `backend/` contains APIs, business logic, persistence, and server-side tests.

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
```

Do not commit credentials, API keys, or local environment files.
