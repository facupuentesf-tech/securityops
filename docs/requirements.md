# Requirements

## Implemented Requirements: First Functional Version

The current application runs locally and uses HTML/CSS/JavaScript, FastAPI
and SQLite. It has no authentication or role-based permissions.

### Incident API

- Preserve `GET /health` with `{"status":"ok"}`.
- `POST /incidents` returns `201` with an ID, title, description, severity,
  status and UTC creation timestamp.
- Title and description must be strings containing non-whitespace characters.
  Severity is required; status defaults to `open` when omitted.
- Severity values: `low`, `medium`, `high`, `critical`.
- Status values: `open`, `investigating`, `resolved`.
- `GET /incidents` returns incidents ordered by ID, with optional `status`
  and `severity` filters combined with AND. No matches returns `[]`.
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
  widths; it supports incident creation, filters, details, status, history and notes.
- Dates are displayed in the browser's timezone. User text is rendered through
  `textContent`; API calls use relative paths.
- The interface communicates loading, empty results, success and errors.
- SQLite data survives server restarts. Tables are created if absent at startup,
  preserving existing records; queries with input use bound SQL parameters.
- `/docs` remains available. Automated tests use temporary databases.

## Original Requirements: Future Work

The following requirements preserve the project's broader objectives. They are
not implemented in the first functional version, except for the incident
operations explicitly described above.

### 1. Users

The system must allow organizations to manage users.

Users should have different roles and permissions.

### 2. Assets

The system must allow organizations to register and manage their technological assets.

Examples:

- Computers
- Servers
- Routers
- Cloud resources
- Applications

### 3. Risks

The system must allow organizations to identify and manage security risks.

Each risk should have:

- Description
- Probability
- Impact
- Risk level
- Responsible person
- Status

### 4. Security Controls

The system must allow organizations to define and track security controls.

### 5. Incidents

The system must allow organizations to register and track security incidents.

Each incident should have:

- Description
- Severity
- Status
- Responsible person
- Date

Description, severity, status and date are implemented. Responsible-person
assignment and links to assets remain planned extensions. General audit logs,
reports, dashboards and security documentation management also remain future work.
