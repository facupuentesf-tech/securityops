# Requirements

## Implemented Requirements

The current application runs locally and uses HTML/CSS/JavaScript, FastAPI
and SQLite. It supports multiple isolated organizations, local authentication
and backend-enforced role-based permissions.

### Authentication and User Management

- `POST /auth/login` accepts an email and password; invalid or inactive accounts
  receive the same `401` response.
- Passwords are stored as salted scrypt hashes, never as plaintext.
- A successful login creates a random server-side session with a 12-hour
  expiration and returns a CSRF token. The opaque session cookie is `HttpOnly`,
  `SameSite=Strict`, scoped to `/`, and marked `Secure` when served over HTTPS.
- `GET /auth/session` returns the current public user and CSRF token, or null
  values if no valid session exists. `POST /auth/logout` revokes the session.
- State-changing requests using an authenticated session require its
  `X-CSRF-Token`; the backend rejects a missing or invalid token with `403`.
- An administrator can list, create and update users, deactivate accounts and
  reset passwords only within their own organization. User creation is not
  public. At least one active administrator per organization must remain; an
  account cannot deactivate itself.
- The first administrator is created only with the local interactive
  `python backend/main.py create-admin` command, and only when no user exists.
  It prompts for a new password; there are no default credentials.
- `python backend/main.py create-organization` interactively creates an
  organization and its first administrator in one transaction. It prompts for
  organization name, account details and a new password; it does not provide
  default credentials or a public registration route.
- Every user, incident and asset belongs to an organization. The server derives the
  organization from the authenticated account; request payloads cannot set or
  change the association. Incident list/filter/detail/status/history/note
  operations, asset operations and user administration are scoped to that organization.
- Identifiers belonging to another organization return `404`, just like
  nonexistent identifiers.
- Roles are singular and fixed to `administrador`, `analista` and `lector`.
  Administrators manage users and perform all incident operations. Analysts
  read/create incidents, change status and add notes. Readers can only read
  incidents, history, notes and assets. Administrators and analysts can create
  assets. These checks apply to API operations regardless
  of interface visibility.

### Asset API and Interface

- `POST /assets` returns `201` with ID, name, type, optional description,
  criticality and UTC creation timestamp. Administrators and analysts can create.
- Name is a required string, trimmed before storage; whitespace-only names
  are rejected. Type is `hardware`, `software`, `service` or `data`.
- Criticality is required: `low`, `medium`, `high` or `critical`.
- Description can be omitted, null or a string; omitted values become null.
- Payloads with extra fields, including `organization_id`, return `422`.
- `GET /assets` returns assets ordered by ID in the authenticated organization.
  Optional `type` and `criticality` filters combine with AND; no matches returns `[]`.
- `GET /assets/{asset_id}` returns the asset or `404` for missing or foreign IDs.
- All three roles can query assets. Anonymous requests return `401`; reader
  creation and missing/invalid CSRF tokens return `403`. Invalid fields or
  filter values return `422`. SQL uses bound parameters.
- The Spanish Assets section provides list, filters, creation and detail,
  hides creation for readers, renders text safely, adapts to mobile widths and
  shows loading, empty, success and error feedback.
- Migration 004 preserves existing data. Assets survive server restarts.

### Incident API

- Preserve `GET /health` with `{"status":"ok"}`.
- `POST /incidents` returns `201` with an ID, title, description, severity,
  status and UTC creation timestamp.
- Title and description must be strings containing non-whitespace characters.
  Severity is required; status defaults to `open` when omitted.
- Severity values: `low`, `medium`, `high`, `critical`.
- Status values: `open`, `investigating`, `resolved`.
- `GET /incidents` returns incidents ordered by ID, with optional `status`
  and `severity` filters combined with AND within the authenticated user's
  organization. No matches returns `[]`.
- `GET /incidents/{incident_id}` returns the incident or `404`.
- `PATCH /incidents/{incident_id}/status` requires a valid non-null status,
  updates only that field and returns the updated incident.
- Invalid payloads or filter values return `422`. Requests for a nonexistent
  incident return `404` after request validation.

### History and Notes

- Each effective status change records previous status, new status and UTC
  timestamp in the same transaction as the incident update.
- Sending the current status produces no history entry. Creation and changes
  made before the history feature existed are not reconstructed.
- `GET /incidents/{incident_id}/history` returns entries ordered by ID.
- `POST /incidents/{incident_id}/notes` accepts `{"content":"..."}`, strips
  leading/trailing whitespace and validates 1–5000 characters; it returns `201`.
- `GET /incidents/{incident_id}/notes` returns notes ordered by creation time
  ascending, then ID ascending. Existing incidents without history or notes
  return `[]`; nonexistent incidents return `404`.

### Interface and Persistence

- `GET /` serves a Spanish-language interface responsive to desktop and mobile
  widths; it supports login, incident operations, asset creation/queries and
  administrator user management.
- Dates are displayed in the browser's timezone. User text is rendered through
  `textContent`; API calls use relative paths.
- The interface communicates loading, empty results, success and errors.
- SQLite data survives server restarts. Numbered SQL migrations preserve
  existing incidents, history and notes; prior activity remains unattributed.
- Migration 003 assigns existing users and incidents to the initial
  organization while preserving account hashes, active sessions and incident
  records.
  The local path can be overridden with `SECURITYOPS_DATABASE`.
- Queries with input use bound SQL parameters. `/docs` remains available.
- Automated tests use temporary databases.

## Original Requirements: Future Work

Asset extensions, risks, controls, general audit logs and shared deployment remain
future work. Multi-organization data isolation is implemented, but this remains
a local prototype bound to `127.0.0.1` and is not intended for shared deployment.

### 1. Asset extensions

Creation and queries are implemented. Editing, deletion, responsible-person
assignment remain future work.

Examples:

- Computers
- Servers
- Routers
- Cloud resources
- Applications

### 2. Risks

The system must allow organizations to identify and manage security risks.

Each risk should have:

- Description
- Probability
- Impact
- Risk level
- Responsible person
- Status

### 3. Security Controls

The system must allow organizations to define and track security controls.

### 4. Incidents

The system must allow organizations to register and track security incidents.

Each incident should have:

- Description
- Severity
- Status
- Responsible person
- Date

Description, severity, status and date are implemented. Responsible-person
assignment remains a planned extension. General audit logs,
reports, dashboards and security documentation management also remain future
work. Multi-organization isolation is implemented; shared deployment is not.

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
