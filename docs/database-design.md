# Database Design

## Overview

The local version uses SQLite, by default at `backend/securityops.db`. The
default path is relative to the backend module and can be overridden with
`SECURITYOPS_DATABASE`. Numbered SQL migrations in `backend/migrations` are
tracked in `schema_migrations`; database files are excluded from Git.
Migrations 001–011 preserve existing incident, history, note, user and session
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

Asset deletion, risk/control extensions and authentication audit events remain future work.
Multi-organization isolation is implemented for the current asset, incident and user
operations. Incident links use `incident_assets`; responsible users use `assignee_id`.
PostgreSQL remains a possible
later database.

The planned entities are:

- Organizations (implemented)
- Assets (creation and queries implemented; extensions planned)
- Risks
- Security Controls
- Audit Logs (implemented by migration 009)

### Asset extensions

Deletion and an `owner_id` association are planned.
Partial editing is implemented; deletion and ownership are not present in the API.

### Risks (implemented initial module; extensions planned)

Represents potential security risks within an organization.

Main fields:

- id
- organization_id
- asset_id
- title
- description
- probability
- impact
- score and level (derived response fields, not stored)
- status
- owner_id (future extension, not implemented)
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
- assignee_id (implemented, nullable)
- created_at

### Audit Logs (implemented)

Migration 009 implements `audit_logs`: `id`, `organization_id`, `actor_id`,
`actor_name`, `action`, `resource_type`, `resource_id`, `occurred_at`, `details`.
See the schema section below and [audit.md](audit.md) for the event contract.
IP addresses and authentication events are not recorded in this stage.

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

## risks (migration 006)

| Column | Type | Constraints |
| --- | --- | --- |
| id | INTEGER | Autoincrement primary key |
| organization_id | INTEGER | NOT NULL, references organizations(id) |
| title | TEXT | NOT NULL, nonempty trimmed text; API trims before storage |
| description | TEXT | Nullable |
| probability | INTEGER | NOT NULL, integer storage and range 1–5 |
| impact | INTEGER | NOT NULL, integer storage and range 1–5 |
| status | TEXT | NOT NULL, identified/treating/accepted; default identified |
| asset_id | INTEGER | Nullable; composite FK with organization_id to assets(id, organization_id) |
| created_at | TEXT | NOT NULL, application-generated UTC ISO timestamp |

Migration 006 adds the table and indexes on `(organization_id, id)`,
`(organization_id, status, id)` and `(organization_id, asset_id, id)` without
rewriting prior data. It reuses the unique asset key from migration 005. Foreign
keys prevent cross-organization links, invalid assets, and changing the asset's
organization or deleting an asset referenced by a risk. Null asset IDs are allowed.

Score and level are derived on the server, not stored: `probability * impact`.
The prototype's own matrix is low 1–4, medium 5–9, high 10–16, critical 17–25.
These thresholds are a local convention rather than an external standard.
SQLite checks storage type and range; JSON booleans and coercible strings/floats
are rejected by strict API validation. Risk deletion
remain deferred. Risk assignees are implemented by migration 008.

## Security controls and risk associations (migration 007)

`security_controls` stores:

| Column | Type | Constraints |
| --- | --- | --- |
| id | INTEGER | Autoincrement primary key |
| organization_id | INTEGER | NOT NULL, FK to organizations(id) |
| name | TEXT | NOT NULL, nonempty trimmed text; API trims before storage |
| description | TEXT | Nullable |
| type | TEXT | NOT NULL: preventive/detective/corrective |
| status | TEXT | NOT NULL: planned/implemented/retired; default planned |
| created_at | TEXT | NOT NULL, application-generated UTC ISO timestamp |

Unique `(id, organization_id)` indexes on controls and risks support the composite
foreign keys of `risk_controls(risk_id, control_id, organization_id)`. All three
columns are NOT NULL; `(risk_id, control_id)` is the primary key. Organization also
references `organizations(id)`. Both resources must belong to this organization.
Foreign keys protect inserts, relation updates, parent organization changes and
parent removal. Unlinking deletes only a relation. A reverse index on
`(control_id, organization_id)` supports control references.

Controls have organization/ID, organization/type/ID and organization/status/ID
indexes. Migration 007 adds tables/indexes without rebuilding or rewriting prior
records. Preservation tests include users, sessions, incidents, history, notes,
assets, incident-asset links, risks and existing autoincrement sequences.
Links store no residual assessment or effectiveness claim and never update risk
probability, impact, score or level. Control deletion remains future work.

## Assignees (migration 008)

`incidents.assignee_id` and `risks.assignee_id` are nullable INTEGER foreign keys
to `users(id)`, initially null for all existing rows. Migration 008 uses ALTER
TABLE and adds `(organization_id, assignee_id, id)` indexes without rebuilding
tables or changing prior columns, records, links or sequences.

BEFORE INSERT and BEFORE UPDATE OF assignee_id/organization_id triggers on each
resource require a non-null assignee to be active, administrator/analyst and in
the same organization. A BEFORE UPDATE OF organization_id trigger on users
prevents moving an assigned user across organizations. These database checks
protect both directions of the relationship, including direct SQL writes.

An AFTER UPDATE OF is_active/role trigger on users clears incident and risk
assignments in the user's organization when the new account is inactive or reader.
It executes inside the user-update transaction. If either collection fails to
update, the user and all assignment changes roll back. Clearing assignments never
deletes resources, notes, history or links, and later reactivation does not restore
them. A referenced user cannot be deleted while assignments exist. Display names
are obtained through organization-scoped joins, not duplicated in these tables.


## Audit logs (migration 009)

`audit_logs` adds an autoincrement `id`, organization foreign key, immutable
historical `actor_id`/`actor_name` snapshots, fixed `action` and `resource_type`,
positive `resource_id`, UTC ISO `occurred_at`, and JSON-object `details` checked
by SQLite. Actor/resource IDs intentionally have no foreign keys to mutable
accounts/resources, preserving history without cascades. Indexes on organization,
date/ID and organization/actor/date/ID support scoped queries. This migration only
creates the audit table and indexes; existing rows, relations and sequences are
preserved and historical activity is not backfilled.

API transactions insert events with explicit minimal detail keys; insert failure
rolls back business changes, user changes, sessions and automatic removals.
No API updates or deletes audit entries. These are local records, without tamper
resistance against direct SQLite access. See [audit.md](audit.md) for the event
catalog, permissions, pagination, validation and verification.


## Initial dashboard (implemented)

Authenticated administrators, analysts and readers can query `GET /dashboard`.
The server derives the organization from the session and binds it in every
query. One SQLite read transaction provides a consistent summary of incidents,
assets, risks and controls, with zero-valued categories, pending unassigned
counts, five recent pending incidents and five highest-scoring identified/treating
risks. Date/ID descending orders recent incidents; score/ID descending orders
priority risks. Counts do not join many-to-many relations. No user or audit data,
control-effectiveness estimates or global security scores are included.

The Spanish Resumen screen is the initial authenticated view; Gestión retains
all existing modules and permissions. Detail links, safe text, local dates,
automatic refresh on return, manual refresh, loading/error/retry/empty feedback
and responsive accessible layouts are provided. No schema migration or data
writes are needed. See [dashboard.md](dashboard.md) for the response contract,
consistent-read test and API/browser/manual verification.


## Partial resource editing (implemented, migration 010)

Administrator/analyst PATCH routes on assets, risks and controls accept only
editable fields, preserve omitted values and reject empty bodies, unknown or
protected fields and invalid values with 422. Null is limited to descriptions
and the optional risk asset_id. Missing/foreign resources and associated assets
return 404. Authenticated organization/actor and CSRF checks come from the server.
Risk score/level are recalculated; assignees, creation dates and many-to-many
links are preserved. Implementing a control never reduces risk score automatically.

Effective changes and one minimal updated audit event share BEGIN IMMEDIATE and
a transaction; audit insertion failure rolls back the edit. Text details are
field-change flags, other details are previous/new enum/number/ID values. No-op
or failed requests generate no events. Migration 010 extends the audit action
CHECK while preserving events, indexes and ID high-water marks; no business data
is rewritten. The safe responsive UI offers role-protected prefilled forms,
save/cancel, validation/error feedback and duplicate-submit guards. Detail/list
refresh after save and Resumen refreshes on return. Resource deletion is not
implemented. See [resource-edits.md](resource-edits.md) for the contract and tests.


## Residual risk assessments (implemented, migration 011)

Manual residual estimates have an append-only API history via POST/GET
`/risks/{risk_id}/assessments`. Administrators/analysts create; all authenticated
roles read. Strict 1–5 probability/impact and trimmed 1–5000 justification are
validated. Score/level reuse the existing matrix. Original probability/impact/score
snapshots and evaluator-name snapshots preserve historical comparisons. Higher
residual scores are allowed. Composite foreign keys enforce organization-scoped
risk/evaluator references. Assessment and minimal numeric assessed audit event
share a transaction; audit failure rolls back the assessment. Justification is
never copied to audit. Migration 011 preserves prior data and audit ID sequences.
The responsive safe UI separates original/latest/history and supports errors and
retries. Controls do not automatically alter estimates; dashboard priorities and
levels continue using the current original score. Assessment editing/deletion
are not provided. See [risk-assessments.md](risk-assessments.md) for the API,
schema, tests and manual verification.
