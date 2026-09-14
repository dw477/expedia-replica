# Application Responsibilities

The application is split into three responsibilities connected through JSON.

## Vue frontend

Vue owns browser interaction and presentation. It collects the hotel-name query,
starts the request, tracks loading and error states, and renders the returned
availability in an accessible table. HTTP calls stay in `frontend/src/api/` so
presentation components do not contain request details.

## FastAPI boundary

FastAPI owns HTTP concerns: route paths, query validation, JSON response schemas,
and conversion of backend failures into appropriate HTTP errors. Routes call the
backend functions but do not duplicate search or pricing rules.

## Backend logic

The framework-free backend owns data access and calculations. `backend/database.py`
is the source of truth for the SQLite schema and imports the supplied CSV files in
one transaction the first time a database is initialized. A metadata marker keeps
later application changes from being overwritten or duplicated on restart.

Search joins trips to hotels in SQLite, matches hotel names, and calculates nights
and total stay prices. Money is stored as integer cents to avoid floating-point
rounding, while dates use validated ISO `YYYY-MM-DD` text. Connections enable
foreign-key enforcement. Keeping these responsibilities independent of FastAPI
makes them directly testable and reusable from other interfaces.
