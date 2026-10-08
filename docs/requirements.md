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

Asset extensions, risk/control extensions, authentication audit events and shared deployment remain
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

### 2. Risk extensions

The system must allow organizations to identify and manage security risks.

Each risk should have:

- Description
- Probability
- Impact
- Risk level
- Responsible person
- Status

### 3. Security control extensions

The system must allow organizations to define and track security controls.

### 4. Incidents

The system must allow organizations to register and track security incidents.

Each incident should have:

- Description
- Severity
- Status
- Responsible person
- Date

Description, severity, status, date and optional responsible-person assignment
are implemented, together with local business/user audit logs. Authentication audit events,
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

## Initial risks (implemented)

- `POST /risks` returns `201`; administrators and analysts create, readers only
  query. Anonymous requests return `401`; unauthorized writes or invalid CSRF
  tokens return `403`.
- Title is required, trimmed and cannot be whitespace-only. Description is optional
  and nullable. Probability and impact are strict JSON integers from 1 to 5:
  booleans, strings, floats and out-of-range values return `422`.
- Status is identified/treating/accepted, default identified. Asset ID is optional,
  nullable and otherwise a strict positive integer belonging to the session organization.
- Organization is session-derived. Extra fields including organization_id, score
  and level return `422`. The server computes score = probability × impact.
- The prototype's own matrix is low 1–4, medium 5–9, high 10–16, critical 17–25;
  it is not presented as an external standard. Response fields include score,
  level, UTC created_at and nullable asset_name.
- `GET /risks` returns records ordered by ID, with status/level/asset_id filters
  combined with AND; no matches returns `[]`. Invalid filters return `422`.
- `GET /risks/{risk_id}` returns a risk. Missing or foreign risks/assets return
  `404`, including asset IDs supplied in creation or filters.
- Migration 006 preserves existing data. Database foreign keys enforce same-tenant
  asset associations and restrict removal or tenant changes of referenced assets.
- The responsive Spanish section provides list, filters, creation and detail,
  optional organization asset selection, safe text rendering and loading/empty/error
  feedback. Data persists across server restarts.
- Editing, deletion and residual evaluation remain future work; risk assignees are implemented.

## Initial security controls (implemented)

- Controls have a trimmed nonempty name, optional nullable description, type
  preventive/detective/corrective, status planned/implemented/retired (default
  planned), ID and UTC creation time. `POST /controls` returns `201`.
- `GET /controls` lists by ID, with type/status filters combined with AND and
  `[]` for no matches. `GET /controls/{control_id}` returns the public control.
- Extra fields including organization_id are rejected (`422`). Organization is
  session-derived; identifiers missing or belonging to another organization give `404`.
- A risk may have many controls and a control may have many risks. Duplicate links
  are prohibited. `GET /risks/{risk_id}/controls` returns full control records or `[]`.
- `POST` on the relation path accepts only `{"control_id": ID}` with a strict
  positive integer. Creation returns `201` with the pair, duplicates `409`.
- `DELETE /risks/{risk_id}/controls/{control_id}` returns empty `204`, or `404` for
  an absent link. It preserves both resources and all their other links.
- Administrators/analysts create, link and unlink. Readers only consult. Existing
  authentication, CSRF and parameterized SQL apply to every route.
- Migration 007 preserves all prior data and enforces organization integrity with
  composite foreign keys and a unique relation pair.
- The Spanish UI provides control list, filters, creation/detail and a risk detail
  section “Controles asociados”; its selector excludes foreign and already-linked
  controls. It is responsive, safely renders user text, respects roles and shows
  loading, empty, error and retry feedback.
- Association documents a measure, does not change score/level or demonstrate
  effectiveness. Residual evaluation and control editing/deletion remain pending.

## Incident and risk assignees (implemented)

- Each resource has an optional assignee: an active administrator or analyst in
  the same organization. New and migrated records start unassigned.
- `PATCH /incidents/{incident_id}/assignee` and `PATCH /risks/{risk_id}/assignee`
  accept an explicit `{"assignee_id": ID}` or null and return the updated resource.
- Only administrators assign/reassign/clear. Analysts/readers can query the
  information and minimal candidate list according to existing read permissions.
- Missing fields, booleans, strings, floats, nonpositive IDs and extra fields give
  `422`. Missing/foreign resource or user IDs give `404`; own inactive/reader user
  IDs give `422`. Existing authentication, CSRF and bound SQL apply.
- `GET /assignees` returns only id/display_name for eligible organization users,
  ordered by ID, or `[]`. It exposes no email, role, password, session or tenant data.
- Resource responses include assignee_id and assignee_name, null when unassigned.
  Creation payloads reject assignment fields, preventing non-admin assignment.
- `assignee_id` list filters combine with all existing filters using AND; no
  matches gives `[]`. Missing/foreign filter users give `404`. Existing own users
  without assignments give `[]` even if no longer eligible.
- Migration 008 preserves all prior data and protects same-organization eligible
  assignments with foreign keys and database triggers.
- Deactivating or converting a user to reader clears all current incident/risk
  assignments in the same transaction; any failure rolls back both the user and
  all assignments. Resources and other relations are retained. Reactivation does
  not restore prior assignments.
- The responsive Spanish detail UI shows the assignee or “Sin asignar”, offers
  administrator-only selectors/actions, uses minimal candidates for filters, safely
  renders names and shows loading/error/empty feedback with retries.
- No notifications/messages are included. Local audit events are implemented by migration 009.


## Local audit logs (migration 009)

Business and user-administration API operations now insert organization-scoped
local audit events in the same transaction, including automatic assignment
removals. Insert failure rolls back the full change; failed requests and no-op
changes produce no events. Actor ID/name snapshots preserve historical identity;
explicit detail allowlists exclude credentials, secrets and free resource text.
Administrator-only `GET /audit-logs` provides AND filters and bounded pagination
ordered by UTC timestamp/ID descending. The responsive Spanish UI renders safe
text and local dates with loading/error/empty feedback. Migration 009 preserves
all existing data and never reconstructs past events. Authentication events are
deferred. This local audit does not resist modification by someone with direct
SQLite access. See [audit.md](audit.md) for the event contract, query validation,
transaction guarantees, tests and manual verification steps.
