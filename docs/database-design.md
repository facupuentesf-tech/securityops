# Database Design

## Overview

The first functional version uses SQLite at `backend/securityops.db`.
The implemented schema is defined in `backend/main.py`. Missing tables and
indexes are created at application startup using `IF NOT EXISTS`, without
deleting or recreating existing data. Database files are excluded from Git.
This is additive initialization, not a versioned schema-migration system.

## Implemented Schema

### incidents

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `title` | TEXT | Required, SQL check for nonempty trimmed text |
| `description` | TEXT | Required, SQL check for nonempty trimmed text |
| `severity` | TEXT | Required: `low`, `medium`, `high`, `critical` |
| `status` | TEXT | Required: `open`, `investigating`, `resolved` |
| `created_at` | TEXT | Required, application-generated UTC ISO 8601 timestamp |

The API rejects title/description values containing only whitespace. Status
defaults to `open` in the creation model when omitted; this is not a database
column default. Lists are ordered by `id` ascending. Optional status and severity
filters use equality conditions combined with AND and bound SQL parameters.

### incident_status_history

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `incident_id` | INTEGER | Required foreign key to `incidents.id` |
| `previous_status` | TEXT | Required, one of the three valid states |
| `new_status` | TEXT | Required, one of the three valid states; must differ from previous state |
| `changed_at` | TEXT | Required, application-generated UTC ISO 8601 timestamp |

Index: `idx_incident_history` on `(incident_id, id)`.
History is returned in ascending ID order. Effective changes are inserted in
the same transaction as the incident update, with `BEGIN IMMEDIATE` before the
state is read. If either write fails, both are rolled back. Sending the existing
state produces no entry. Creation and earlier changes are not backfilled.
No user identity is recorded because authentication is not implemented.

### incident_notes

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `incident_id` | INTEGER | Required foreign key to `incidents.id` |
| `content` | TEXT | Required, SQL length check between 1 and 5000 characters |
| `created_at` | TEXT | Required, application-generated UTC ISO 8601 timestamp |

Index: `idx_incident_notes` on `(incident_id, created_at, id)`.
The API strips surrounding whitespace before validating and storing 1–5000
characters. Notes are listed by `created_at` ascending, with `id` ascending to
break ties. Creating a note does not modify incident fields or status history.

### Relationships and Persistence

Each incident can have many history entries and many notes. Connections enable
`PRAGMA foreign_keys = ON`; the two child tables reference existing incidents.
No cascade-delete behavior or delete endpoints are implemented. All input values
in SQL queries are passed as parameters. Dates are stored as TEXT in UTC and
returned as datetime values in the API; the interface displays them in the
browser's timezone. Incident, history and note data survive server restarts.

## Original Proposed Model: Future Work

The original relational model below preserves the broader project objectives.
These company, user, role, permission, asset, risk, control and general audit
tables are not present in SQLite yet. The proposed incident fields such as
`company_id`, `asset_id` and `assigned_to` are future extensions, not columns in
the current `incidents` table. PostgreSQL remains a possible later database.

The planned entities are:

- Companies
- Users
- Roles
- Permissions
- Assets
- Risks
- Security Controls
- Incidents
- Audit Logs

### Companies

Represents an organization using SecurityOps.

Main fields:

- id
- name
- created_at

### Users

Represents users who can access the platform.

Main fields:

- id
- company_id
- name
- email
- password_hash
- role_id
- created_at

### Roles

Represents the roles assigned to users.

Main fields:

- id
- name
- description

Initial roles:

- Administrator
- Security Manager
- Auditor
- Employee

### Permissions

Represents specific actions that can be performed.

Main fields:

- id
- name
- description

Examples:

- users.create
- users.read
- users.update
- users.delete
- assets.read
- assets.create
- risks.read
- risks.create
- incidents.create

### Assets

Represents technological resources belonging to a company.

Main fields:

- id
- company_id
- name
- type
- description
- criticality
- owner_id
- created_at

### Risks

Represents potential security risks.

Main fields:

- id
- company_id
- asset_id
- title
- description
- probability
- impact
- risk_level
- status
- owner_id
- created_at

### Security Controls

Represents security measures used to reduce risks.

Main fields:

- id
- company_id
- name
- description
- status
- owner_id
- created_at

### Incidents (Planned Extensions)

Represents security incidents.

Main fields:

- id
- company_id
- asset_id
- title
- description
- severity
- status
- assigned_to
- created_at

### Audit Logs

Records important actions performed within the platform.

Main fields:

- id
- company_id
- user_id
- action
- entity_type
- entity_id
- timestamp
- ip_address
