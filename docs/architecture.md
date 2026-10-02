# System Architecture

## Overview

The first functional version is a local web application. One Uvicorn process
hosts FastAPI, serves the HTML/CSS/JavaScript interface and exposes the JSON API.
The backend reads and writes a persistent SQLite file using Python's `sqlite3`.
There is no separate frontend server, build step or external database service.

## Architecture

```text
Browser (Spanish HTML/CSS/JavaScript interface)
       |
       | Local HTTP, relative API paths
       v
Uvicorn on 127.0.0.1:8000
       |
       v
FastAPI (backend/main.py)
       |-- GET /: backend/static/index.html
       |-- /static: styles.css and app.js
       |-- /docs: interactive API documentation
       |-- /health and incident endpoints
       |
       | sqlite3, parameterized SQL
       v
backend/securityops.db
       |-- incidents
       |-- incident_status_history
       |-- incident_notes
```

## Frontend

`backend/static/index.html` provides the list, incident creation form and detail
view. `styles.css` adapts the layout to desktop and mobile widths. `app.js`
calls the same-origin API through relative paths and renders user content using
`textContent`, without interpreting it as HTML.

The interface supports status/severity filters, descriptions, state changes,
history and investigation notes. It communicates loading, empty lists, success
and errors. UTC timestamps from the API are formatted with `Intl.DateTimeFormat`
in the browser's timezone.

## Backend and API

FastAPI routes and Pydantic models currently live in `backend/main.py`.
The models validate strings, allowed severity/status values and note length.
Uvicorn serves the application. Runtime dependencies are in
`backend/requirements.txt`; SQLite support comes from Python's standard library.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/health` | Health response |
| POST | `/incidents` | Create incident |
| GET | `/incidents` | List with optional status/severity filters |
| GET | `/incidents/{incident_id}` | Incident detail |
| PATCH | `/incidents/{incident_id}/status` | Status update and history |
| GET | `/incidents/{incident_id}/history` | Read status history |
| POST | `/incidents/{incident_id}/notes` | Add investigation note |
| GET | `/incidents/{incident_id}/notes` | Read investigation notes |

Creation endpoints return `201`; successful reads and status updates return
`200`. Validation errors return `422` and nonexistent incidents return `404`
after request validation. `/docs` exposes the API schema and examples can be
executed there. The web page route is excluded from the API schema.

## Data Lifecycle and Transactions

At startup, the FastAPI lifespan handler creates missing tables and indexes
with `IF NOT EXISTS`. It does not delete or recreate the database. The database
path is resolved relative to `main.py`, independent of the working directory,
and database files are excluded from Git.

Connections enable foreign keys and are closed after use. Status changes use
`BEGIN IMMEDIATE` before reading the current state, serializing writers. The
status update and its history entry are committed together; an error rolls
back both. Resending the same state creates no history entry. Notes are stored
separately and do not alter the incident or its status history.

See [database-design.md](database-design.md) for fields, constraints and ordering.

## Local Scope and Security Boundaries

The documented launch command binds to `127.0.0.1`. This version has no
authentication, users, roles, permissions or company isolation. Any client that
can reach the API can read and modify incident data. Validation, parameterized
SQL and safe text rendering are implemented, but access control is future work.
There is no publication or shared deployment configured.

## Verification

The unittest suite runs a real local HTTP server against a temporary SQLite
database. It covers API behavior, validation, ordering, persistence across
restarts, additive table creation, transaction rollback and web asset delivery.
An optional Node.js script drives headless Chrome via its local DevTools protocol
to exercise UI flows at desktop and mobile widths. See the README for commands
and environment requirements.

## Future Architecture

The original layered web-application direction is preserved. React, PostgreSQL
and Docker are candidates for later stages. Separating backend modules,
introducing schema migrations and adding authentication, permission enforcement
and company isolation are future work. The broader roadmap includes users,
assets, risks, controls, general auditing, reports and dashboards.
