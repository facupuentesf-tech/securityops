# System Model

## Overview

SecurityOps aims to centralize the cybersecurity environment of an organization.
The first functional version implements a local incident-management workflow.

## Implemented Model

An **incident** represents a recorded security event with an ID, title,
description, severity, current status and UTC creation time. The system can
create, list, filter and read incidents. It can update their status but does
not provide general editing or deletion.

Severity is `low`, `medium`, `high` or `critical`. Status is `open`,
`investigating` or `resolved`. Any of these states may be selected, including
reopening a resolved incident; there are no transition restrictions beyond
validating the value.

A **status-history entry** belongs to one incident and records the previous
state, new state, UTC time and authenticated actor for an effective change.
Repeating the current state does not create another entry. History entries
created before migration 002 keep a null actor; past activity is not reconstructed.

An **investigation note** belongs to one incident and contains text, an ID, a
UTC creation time and (for new notes) its authenticated author. Notes can be
created and listed, not edited or deleted.
Their content is trimmed and limited to 1–5000 characters. They do not change
the incident's status or its history.

Each incident has zero or more history entries and notes. Both collections are
persistent in SQLite; existing incidents without entries return empty lists.
History is ordered by ID, and notes by creation time with ID as a tiebreaker.

An **asset** belongs to one organization and has an ID, trimmed nonempty name,
type (`hardware`, `software`, `service`, `data`), optional description,
criticality (`low`, `medium`, `high`, `critical`) and UTC creation timestamp.
Administrators and analysts create assets; all authenticated roles can list,
filter and view details. Type and criticality filters combine with AND.
Editing, deletion, ownership assignment are future work.

An **account** has a display name, unique email, scrypt password hash, active
flag, exactly one of three roles and belongs to one organization. Administrators
create and manage accounts only in their own organization; there is no public
registration. The initial administrator is bootstrapped with
`python backend/main.py create-admin`, before any user exists. Additional
organizations and their initial administrators are created locally with
`python backend/main.py create-organization`.

An **organization** owns its users, incidents and assets. The authenticated user's
organization is loaded by the server from the account record on each request;
the client cannot choose or change it. Incident list/filter/detail/status,
history, notes, asset operations and user administration are all organization-scoped. Attempts
to access identifiers belonging to another organization return `404`.

An **authenticated session** is represented by a random opaque token held in an
`HttpOnly`, `SameSite=Strict` cookie. SQLite stores only its SHA-256 digest and
an expiry (12 hours). Each protected API request rechecks the active account
and its current role. State-changing requests also require the session's CSRF
token. Logout, account deactivation and password reset invalidate sessions.

The implemented role permissions are:

| Operation | Administrador | Analista | Lector |
| --- | --- | --- | --- |
| Read incidents, history and notes | Yes | Yes | Yes |
| Create incidents, change status, add notes | Yes | Yes | No |
| Read assets | Yes | Yes | Yes |
| Create assets | Yes | Yes | No |
| Read risks | Yes | Yes | Yes |
| Create risks | Yes | Yes | No |
| Read assignees and eligible candidates | Yes | Yes | Yes |
| Assign, reassign and clear assignees | Yes | No | No |
| Read controls and risk-control links | Yes | Yes | Yes |
| Create controls, link and unlink | Yes | Yes | No |
| Link and unlink incident assets | Yes | Yes | No |
| Manage users and reset passwords | Yes | No | No |

The HTML/CSS/JavaScript interface is in Spanish, calls the FastAPI API and
formats dates in the browser's timezone. UI visibility reflects role
permissions, but access is enforced by the backend. The prototype supports
multiple isolated organizations while remaining local; it is not configured
for shared deployment.

## Original Domain Vision: Future Work

The following entities and relationships preserve the original vision.
Asset extensions, risk/control extensions and general audit logs remain future work.
Responsible users for incidents and risks are implemented.

The planned domain entities are:

- Organizations / tenant isolation (implemented for users, incidents and assets)
- Assets (creation and queries implemented; extensions planned)
- Risks
- Security Controls
- Incidents
- Audit Logs

### Asset extensions

Asset creation and queries are implemented. Editing, deletion, ownership and
extensions remain planned. Assets represent technological resources belonging to an organization.

Examples:

- Computers
- Servers
- Network devices
- Applications
- Databases
- Cloud resources

### Risks

Risks represent potential events that could negatively affect the
organization.

Each risk should contain information such as:

- Description
- Probability
- Impact
- Risk level
- Related asset
- Responsible person
- Status

### Security Controls

Security controls represent measures implemented to reduce or manage
security risks.

Examples:

- Multi-factor authentication
- Backups
- Access reviews
- Security policies
- Network segmentation

### Incidents (Planned Extensions)

Incidents represent security events that have occurred or are being
investigated.

Each incident should contain:

- Description
- Severity
- Status
- Date
- Responsible person
- Related asset

### Audit Logs

Audit logs record important actions performed within the platform.

Examples:

- User creation
- Role changes
- Risk modifications
- Incident creation
- Permission changes

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

## Initial risk model (implemented)

A risk records a potential security event in one organization. It has an ID,
trimmed nonempty title, optional description, integer probability and impact
from 1 to 5, status identified/treating/accepted and UTC creation time.
The initial status defaults to identified; the current module only creates
and reads records, with no status updates or other editing/deletion.

A risk may reference zero or one asset in the same organization; an asset may
have multiple risks. Server validation and composite foreign keys both enforce
this association. Score is probability × impact and level is derived using the
prototype's own thresholds: low 1–4, medium 5–9, high 10–16, critical 17–25.
Some integer scores within the intervals cannot be produced by the 5×5 factors.
This is an initial assessment with no residual-risk calculation.

## Initial security control model (implemented)

A security control documents a measure owned by one organization. Its name is
trimmed and nonempty; description is optional. Type is preventive, detective or
corrective; status is planned, implemented or retired, defaulting to planned.
Each record has an ID and UTC creation timestamp.

Risks and controls have a many-to-many relationship within the same organization.
Each pair appears at most once. Linking and unlinking do not alter either resource
or any other relationship. All control states may be associated to document the
measure's current state. The association alone neither changes initial risk score
and level nor proves efficacy. No residual assessment, control editing or control
deletion is implemented.

## Optional responsible users

Each incident and risk may reference one responsible account, or remain unassigned.
Only active administrators and analysts in the resource's organization are eligible.
Administrators assign/reassign/clear; the other roles view according to their existing
resource permissions. Candidate lookup reveals only ID and display name for eligible
accounts. Names are read from the current account and rendered as safe text.

Assignment is distinct from the authors of notes/history and does not modify status,
history, notes, asset/control links, probability, impact or score. Deactivation or a
role change to reader clears the user's assignments atomically with the account
update. Any failure reverses the whole operation. Reactivation never reconstructs
responsibility automatically. Foreign-organization assignments and organization
changes that would invalidate a current assignment are prevented by the database.
No notifications or general audit events are introduced.
