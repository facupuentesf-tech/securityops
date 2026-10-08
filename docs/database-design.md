# Database Design

## Overview

The local version uses SQLite, by default at `backend/securityops.db`. The
default path is relative to the backend module and can be overridden with
`SECURITYOPS_DATABASE`. Numbered SQL migrations in `backend/migrations` are
tracked in `schema_migrations`; database files are excluded from Git.
Migrations 001–005 preserve existing incident, history, note, user and session
data while assigning existing users and incidents to the initial organization.

## Implemented Schema

### organizations

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `name` | TEXT | Required, unique case-insensitively, 1–120 trimmed characters |
| `created_at` | TEXT | Required, UTC creation timestamp |

Migration 003 creates `Organización inicial` and associates all pre-existing
users and incidents with it. The local `create-organization` command creates
additional organizations together with their first administrator.

### assets

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `organization_id` | INTEGER | Required foreign key to `organizations.id` |
| `name` | TEXT | Required, nonempty trimmed text; API strips surrounding whitespace |
| `type` | TEXT | Required: `hardware`, `software`, `service`, `data` |
| `description` | TEXT | Optional, nullable; omitted values are stored as null |
| `criticality` | TEXT | Required: `low`, `medium`, `high`, `critical` |
| `created_at` | TEXT | Required, application-generated UTC ISO 8601 timestamp |

Migration 004 adds this table and indexes on `(organization_id, id)`,
`(organization_id, type, id)` and `(organization_id, criticality, id)` without
altering existing tables or data. Assets are listed by ascending ID. Type and
criticality filters combine with AND and use bound SQL parameters within the
authenticated organization. Asset response models omit the internal organization
ID; creation rejects client-supplied associations. Editing, deletion, ownership
assignment remain future work.

### incidents

| Field | SQLite type | Constraints and meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `title` | TEXT | Required, SQL check for nonempty trimmed text |
| `description` | TEXT | Required, SQL check for nonempty trimmed text |
| `severity` | TEXT | Required: `low`, `medium`, `high`, `critical` |
| `status` | TEXT | Required: `open`, `investigating`, `resolved` |
| `created_at` | TEXT | Required, application-generated UTC ISO 8601 timestamp |
| `organization_id` | INTEGER | Required foreign key to `organizations.id` |

The API rejects title/description values containing only whitespace. Status
defaults to `open` in the creation model when omitted; this is not a database
column default. Lists are ordered by `id` ascending. Optional status and severity
filters use equality conditions combined with AND and bound SQL parameters.
Every list, filter and detail lookup also requires the authenticated user's
organization ID, which is supplied by the server rather than the request.

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
| `organization_id` | INTEGER | Required foreign key to `organizations.id` |

One role is stored directly on each user. The server derives the user's
organization from the authenticated session. Administrators can create and
manage accounts only in that organization; API requests cannot set or change
the association. Accounts are created by an administrator or by a local
interactive bootstrap command; no public signup exists. At least one active
administrator must remain in each organization.

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
creates users/sessions and adds nullable actor foreign keys. Migration 003
creates organizations, assigns old users/incidents to the initial organization
and adds organization indexes and required-association triggers. Each migration
runs in a transaction and is applied only once. Migration 004 adds assets and
their organization-scoped indexes.

### Relationships and Persistence

Each incident can have many history entries and many notes. Users can be
referenced by new history entries and notes. Connections enable
`PRAGMA foreign_keys = ON`; child rows reference existing incidents/users.
Incidents, history and notes have no delete endpoints. User deletion is not
exposed; sessions cascade only if a user row is deleted outside the API. All
input values in SQL queries are passed as parameters. Dates are stored as TEXT in UTC and
returned as datetime values in the API; the interface displays them in the
browser's timezone. Incident, history, note and asset data survive server restarts.

## Domain entities still planned

Asset editing and deletion, risks, controls and general audit logs remain future work.
Multi-organization isolation is implemented for the current asset, incident and user
operations. Incident links use the separate `incident_assets` table; `assigned_to` remains
a planned extension. PostgreSQL remains a possible
later database.

The planned entities are:

- Organizations (implemented)
- Assets (creation and queries implemented; extensions planned)
- Risks
- Security Controls
- Audit Logs

### Asset extensions

Editing, deletion, an `owner_id` association are planned.
They are not present in the current schema or API.

### Risks

Represents potential security risks within an organization.

Main fields:

- id
- organization_id
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

Represents security measures used to reduce risks in an organization.

Main fields:

- id
- organization_id
- name
- description
- status
- owner_id
- created_at

### Incidents (Planned Extensions)

Represents future incident extensions within an organization.

Main fields:

- id
- organization_id
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
- organization_id
- user_id
- action
- entity_type
- entity_id
- timestamp
- ip_address

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
