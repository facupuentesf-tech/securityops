# System Architecture

## Overview

SecurityOps is a local, multi-organization web application with server-enforced
tenant isolation. One Uvicorn process hosts FastAPI, serves the
HTML/CSS/JavaScript interface and exposes the JSON API. The backend uses SQLite
through Python's `sqlite3`; there is no separate frontend server or external
database service.

## Architecture

```text
Browser (Spanish interface)
       |
       | Same-origin HTTP, opaque HttpOnly session cookie
       v
Uvicorn on 127.0.0.1:8000
       |
       v
FastAPI (backend/main.py)
       |-- /: login and incident/asset/user interface
       |-- /static: CSS and JavaScript
       |-- /docs: API schema
       |-- /auth: login, session and logout
       |-- /users: administrator-only management
       |-- /incidents: role-protected operations
       |-- /assets: organization-scoped creation and queries
       |
       | sqlite3, bound query parameters, SQL migrations
       v
SQLite database (default: backend/securityops.db)
       |-- organizations, users, sessions
       |-- incidents, incident_status_history, incident_notes
       |-- assets
       |-- schema_migrations
```

## Authentication and Authorization

Passwords are salted with Python's `hashlib.scrypt` (N=16384, r=8, p=1).
Successful login issues a cryptographically random opaque token; only its
SHA-256 digest is stored in SQLite. Sessions expire after 12 hours and are
revalidated against the active user on each protected request. The cookie is
`HttpOnly`, `SameSite=Strict`, scoped to `/`, and `Secure` on HTTPS. Logout
deletes the server-side session. Deactivation and password reset invalidate
the affected user's active sessions.

Authenticated mutating requests must supply the session's `X-CSRF-Token`.
The frontend keeps that token in memory, not in browser storage. Role checks
run in FastAPI dependencies for every protected API operation:

| Operation | Administrador | Analista | Lector |
| --- | --- | --- | --- |
| Read incidents, history and notes | Yes | Yes | Yes |
| Create incidents, change status, add notes | Yes | Yes | No |
| Read assets | Yes | Yes | Yes |
| Create assets | Yes | Yes | No |
| List/create/update/deactivate users, reset passwords | Yes | No | No |

`POST /auth/login` is the only public account operation. The initial
administrator is created through the interactive local command
`python backend/main.py create-admin`; further organizations and their first
administrators are bootstrapped with
`python backend/main.py create-organization`. Both prompt for new passwords;
no default password or public signup exists. The root page and static assets are
public so the login UI can load.
`/health` and `/docs` are also public; protected business data and operations
are not.

The authenticated user's `organization_id`, loaded from the user row on every
request, supplies the tenant scope. The API never accepts an organization ID
for users, incidents or assets, and administrator user-management operations are
restricted to that organization. Cross-organization identifiers return `404`.

## Frontend

`backend/static/index.html` contains the login form, incident list/detail,
asset list/filter/create/detail section and administrator user panel.
`styles.css` adapts layouts to desktop and mobile.
`app.js` calls same-origin routes, sends the CSRF header for mutations and
renders user-provided content with `textContent`.

The interface hides actions unavailable to a role for clarity, but this is not
the security boundary: FastAPI enforces the same permissions independently.
UTC timestamps are displayed in the browser's timezone. Administrators can
create users in their own organization, change display name/email/role,
deactivate accounts and reset passwords. Organization associations cannot be
changed through the API.

## API

| Method | Route | Access |
| --- | --- | --- |
| GET | `/health` | Public |
| POST | `/auth/login` | Public |
| GET | `/auth/session` | Public; reports the current session when present |
| POST | `/auth/logout` | Authenticated |
| GET, POST | `/users` | Administrator |
| PATCH | `/users/{user_id}` | Administrator |
| POST | `/users/{user_id}/password` | Administrator |
| POST | `/incidents` | Administrator, analyst |
| GET | `/incidents` | Any authenticated user |
| GET | `/incidents/{incident_id}` | Any authenticated user |
| PATCH | `/incidents/{incident_id}/status` | Administrator, analyst |
| GET | `/incidents/{incident_id}/history` | Any authenticated user |
| POST | `/incidents/{incident_id}/notes` | Administrator, analyst |
| GET | `/incidents/{incident_id}/notes` | Any authenticated user |
| POST | `/assets` | Administrator, analyst; returns 201 |
| GET | `/assets` | Any authenticated user; optional type/criticality filters with AND |
| GET | `/assets/{asset_id}` | Any authenticated user; foreign organization IDs return 404 |

Authenticated reads require the session cookie. All authenticated mutations
also require the matching CSRF header. `/docs` documents the API; its protected
operations still require a valid session and CSRF token when mutating data.

## Data Lifecycle and Migrations

The SQLite path defaults to a location relative to `main.py`; set
`SECURITYOPS_DATABASE` to override it. Database files are excluded from Git.
Connections enable foreign keys and close after use.

Numbered SQL files in `backend/migrations` are applied in order and recorded in
`schema_migrations`. Migration 001 creates the incident schema if absent.
Migration 002 adds users, sessions and nullable actor references for status
history and notes. Migration 003 creates the initial organization and assigns
existing users and incidents to it without replacing rows; existing sessions,
password hashes, history and notes remain intact. Organization columns are
required by database triggers and foreign keys. The upgrade does not invent
actors for historical records. Status changes and their history entries remain
atomic; concurrent writers are serialized with `BEGIN IMMEDIATE`.
Migration 004 adds assets and indexes without changing existing tables or data.

## Local Scope and Security Boundaries

This release supports isolated organization records but still binds to
`127.0.0.1`. It does not provide shared deployment configuration, rate limiting
or a general audit log. It is not safe to expose this local prototype to an
untrusted network.

## Verification and Future Work

The unittest suite exercises a local HTTP server with a temporary SQLite
database, including authentication, permissions, migration of legacy data,
incident and asset workflows, tenant isolation and persistence. An optional Node.js/Chrome smoke
test exercises the authenticated interface at desktop and mobile widths.

Asset editing and deletion, risk extensions, controls, general audit logs, reports and dashboards remain
future work. React, PostgreSQL and Docker are possible later choices.

## Incident-asset links (implemented)

Migration 005 adds `incident_assets(incident_id, asset_id, organization_id)` without
rewriting existing records. Each incident and asset can participate in multiple
links. The pair is the primary key. Composite foreign keys reference unique
`(id, organization_id)` indexes on incidents and assets, enforcing tenant integrity
on inserts, updates and parent organization changes. Parent removal with links is
restricted. Unlinking deletes only a relationship.

`GET /incidents/{incident_id}/assets` returns full asset records ordered by ID or
`[]`. `POST` on that path accepts only `{"asset_id": ID}` (positive strict integer),
returns `201` with the pair, and `409` for duplicates. `DELETE` on
`/incidents/{incident_id}/assets/{asset_id}` returns an empty `204`, or `404` when
absent. Missing or foreign resources return `404`. All roles read; administrators
and analysts write with session authentication and CSRF. SQL values are bound.

The responsive incident detail includes "Activos afectados", safe text rendering,
a selector excluding linked assets, unlink buttons, loading/empty/error feedback
and retry. Reader controls are hidden. Automated API tests cover relationships,
validation, permissions, CSRF, tenant isolation, database constraints, migration
preservation and restart persistence; Chrome smoke checks cover the interface.

## Initial risk module

`POST /risks` uses the existing administrator/analyst role dependency and session
CSRF checks. A `BEGIN IMMEDIATE` transaction verifies the optional asset belongs
to the session organization, inserts the risk and returns `201`. Composite foreign
keys provide the same organization check against direct database writes.
`GET /risks` and `GET /risks/{risk_id}` allow all authenticated roles; queries always
bind the session organization. Missing/foreign risk or asset IDs return `404`.

List filters `status`, `level`, `asset_id` combine with AND. Level filters use
parameterized score ranges. Responses derive score and level from the stored
probability/impact and include the optional asset name through an organization-scoped
left join. The matrix is a prototype convention: low 1–4, medium 5–9, high 10–16,
critical 17–25. Extra creation fields, including organization, score and level, are
rejected. Migration 006 adds only the new table and indexes.

The Spanish risk list, filters, create form and detail reuse the existing API,
safe DOM rendering, feedback and responsive styles. Independent request versions
discard stale list/detail/asset-selector responses on navigation or logout.
Reader creation controls are hidden; the backend enforces permissions.
API tests cover validation, all 25 factor combinations, tenant integrity and
persistence. Chrome checks creation with/without assets, filtering, reader access,
safe text, dates, network errors and desktop/mobile widths.
