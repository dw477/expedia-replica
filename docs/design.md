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

The framework-free backend owns data access and calculations. It reads the
supplied CSV files, joins trips to hotels, matches hotel names, validates source
data, and calculates nights and total stay prices. Keeping this logic independent
of FastAPI makes it directly testable and reusable from other interfaces.
