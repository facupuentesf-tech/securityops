# Database Design

## Overview

The local version uses SQLite, by default at `backend/securityops.db`. The
default path is relative to the backend module and can be overridden with
`SECURITYOPS_DATABASE`. Numbered SQL migrations in `backend/migrations` are
tracked in `schema_migrations`; database files are excluded from Git.
Migrations 001 and 002 preserve the existing incident, history and note data.

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
| `changed_by` | INTEGER | Optional foreign key to `users.id`; null for history predating migration 002 |

Index: `idx_incident_history` on `(incident_id, id)`.
History is returned in ascending ID order. Effective changes are inserted in
the same transaction as the incident update, with `BEGIN IMMEDIATE` before the
state is read. If either write fails, both are rolled back. Sending the existing
state produces no entry. Creation and earlier changes are not backfilled.
New status changes are attributed to the authenticated user.

### incident_notes

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `incident_id` | INTEGER | Required foreign key to `incidents.id` |
| `content` | TEXT | Required, SQL length check between 1 and 5000 characters |
| `created_at` | TEXT | Required, application-generated UTC ISO 8601 timestamp |
| `created_by` | INTEGER | Optional foreign key to `users.id`; null for notes predating migration 002 |

Index: `idx_incident_notes` on `(incident_id, created_at, id)`.
The API strips surrounding whitespace before validating and storing 1–5000
characters. Notes are listed by `created_at` ascending, with `id` ascending to
break ties. New notes are attributed to the authenticated user. Creating a note
does not modify incident fields or status history.

### users

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `display_name` | TEXT | Required, nonempty after trimming |
| `email` | TEXT | Required, unique and case-insensitive |
| `password_hash` | TEXT | Required, salted scrypt hash |
| `role` | TEXT | Required: `administrador`, `analista` or `lector` |
| `is_active` | INTEGER | Required boolean, defaults to 1 |
| `created_at` | TEXT | Required, application-generated UTC ISO 8601 timestamp |

One role is stored directly on each user. User records are not yet related to
an organization because this stage supports one local organization only.
Accounts are created by an administrator or the interactive initial-admin
command; no public signup exists. At least one active administrator must remain.

### sessions

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `token_hash` | TEXT | Primary key, SHA-256 hash of a random opaque session token |
| `user_id` | INTEGER | Required foreign key to `users.id`, cascade deleted |
| `csrf_token` | TEXT | Required random token checked on state-changing requests |
| `expires_at` | INTEGER | Required Unix timestamp; session lifetime is 12 hours |

Only the token digest is stored; the cookie contains the opaque original token
and is `HttpOnly`, `SameSite=Strict`, and `Secure` for HTTPS requests.
Deactivating an account blocks its sessions immediately. Password reset deletes
all sessions for that user.

### schema_migrations

Stores each applied migration version and its UTC application timestamp.
Migration 001 creates incident tables and indexes if absent. Migration 002
creates users/sessions and adds nullable actor foreign keys. Each migration runs
in a transaction and is applied only once.

### Relationships and Persistence

Each incident can have many history entries and many notes. Users can be
referenced by new history entries and notes. Connections enable
`PRAGMA foreign_keys = ON`; child rows reference existing incidents/users.
Incidents, history and notes have no delete endpoints. User deletion is not
exposed; sessions cascade only if a user row is deleted outside the API. All
input values in SQL queries are passed as parameters. Dates are stored as TEXT in UTC and
returned as datetime values in the API; the interface displays them in the
browser's timezone. Incident, history and note data survive server restarts.

## Domain entities still planned

Organizations, assets, risks, controls and general audit logs remain future
work. Multi-organization support and tenant isolation are not implemented.
Proposed incident fields such as `company_id`, `asset_id` and `assigned_to`
are not columns in the current `incidents` table. PostgreSQL remains a possible
later database.

The planned entities are:

- Companies (future multi-organization support)
- Assets
- Risks
- Security Controls
- Audit Logs

### Companies

Represents an organization using SecurityOps.

Main fields:

- id
- name
- created_at

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
