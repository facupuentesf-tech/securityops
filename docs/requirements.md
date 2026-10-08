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
- Every user and incident belongs to an organization. The server derives the
  organization from the authenticated account; request payloads cannot set or
  change the association. Incident list/filter/detail/status/history/note
  operations and user administration are scoped to that organization.
- Identifiers belonging to another organization return `404`, just like
  nonexistent identifiers.
- Roles are singular and fixed to `administrador`, `analista` and `lector`.
  Administrators manage users and perform all incident operations. Analysts
  read/create incidents, change status and add notes. Readers can only read
  incidents, history and notes. These checks apply to API operations regardless
  of interface visibility.

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
  widths; it supports login, incident operations and administrator user management.
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

Assets, risks, controls, general audit logs and shared deployment remain
future work. Multi-organization data isolation is implemented, but this remains
a local prototype bound to `127.0.0.1` and is not intended for shared deployment.

### 1. Assets

The system must allow organizations to register and manage their technological assets.

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
assignment and links to assets remain planned extensions. General audit logs,
reports, dashboards and security documentation management also remain future
work. Multi-organization isolation is implemented; shared deployment is not.
