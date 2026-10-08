# Project Definition

## Project Name

SecurityOps

## Problem

Small and medium-sized businesses often lack a centralized system
to manage their cybersecurity information.

Security-related information may be distributed across spreadsheets,
documents, emails and different tools.

This makes it difficult to understand the organization's security
posture, identify risks, track security controls and maintain
documentation.

## Solution

SecurityOps is a web-based platform designed to centralize the
management of cybersecurity information for small and medium-sized
businesses.

The long-term platform vision will allow organizations to manage:

- Users and permissions
- Technological assets
- Security risks
- Security controls
- Security incidents
- Audit information
- Security documentation

## Target Users

The initial target users are:

- Small businesses
- Medium-sized businesses
- IT administrators
- Security professionals
- External security consultants

## Initial Goal

The initial goal is to build a functional prototype that demonstrates
how an organization can centralize and manage its cybersecurity
information through a single platform.

The project will prioritize security, usability, documentation and
maintainability.

## Implemented Scope

The current version is a local, multi-organization incident and asset management
prototype with server-enforced tenant isolation. It provides:

- Incident creation, listing, detail and optional status/severity filters.
- Asset creation, listing and detail with optional type/criticality filters.
- Initial risk creation, listing and detail with optional asset association,
  strict probability/impact values, server-derived score/level and AND filters.
- Security control creation, listing/detail and type/status AND filters, with
  many-to-many risk associations protected by organization in the API and database.
- Optional incident/risk responsible users, administrator-only assignment and
  minimal eligible-candidate lookup, with atomic cleanup on user eligibility changes.
- Status changes with persistent history recorded atomically with the update.
- Investigation notes with validation and persistent storage.
- User login/logout, scrypt password hashes, opaque server-side sessions in
  `HttpOnly` cookies and CSRF protection for state-changing requests.
- Administrator-managed user accounts and backend-enforced administrator,
  analyst and reader permissions.
- Organization-scoped users, incidents and assets; the organization is derived from
  the authenticated account and cannot be selected through the API.
- Local commands to bootstrap the initial organization or create another
  organization together with its first administrator.
- User attribution for new status-history entries and notes.
- Versioned SQLite migrations that preserve existing incident data.
- A responsive Spanish-language HTML/CSS/JavaScript interface served by FastAPI.
- SQLite persistence, interactive API documentation and automated tests.

The application runs locally through Uvicorn on `127.0.0.1`. Migration 003
assigns all existing users and incidents to an initial organization and
preserves existing sessions, history and notes. Migration 004 adds assets without
altering existing data. Existing history and notes are
preserved but cannot be attributed to users retroactively. Incident status
history remains a specific incident feature. Migration 009 adds local business
and user-administration audit logs without reconstructing earlier events.
Shared deployment is not implemented or supported.

## Original Project Scope and Future Work

The original project roadmap is preserved. Beyond the initial incident module,
the following capabilities remain future work:

1. Asset editing, deletion, ownership assignment
2. Risk editing/deletion and residual evaluation
3. Security control editing/deletion and effectiveness assessment
4. Further incident workflow extensions
5. Authentication audit events and stronger audit storage
6. Dashboard and basic metrics

Features such as automated vulnerability scanning, advanced compliance
automation and artificial intelligence assistance will be considered
for future versions.

React, PostgreSQL and Docker remain options for later stages; the implemented
version uses plain HTML/CSS/JavaScript, Python with FastAPI and SQLite.

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

## Initial risks

Migration 006 implements organization-scoped risks with optional asset association.
Administrators and analysts create; readers query. The Spanish interface supports
list, creation, detail and filters by status, level and asset. The server enforces
roles, CSRF, validation and same-organization associations; the database protects
the association with a composite foreign key while preserving prior data.
Score is probability × impact (integer factors 1–5). The prototype defines its own
levels: low 1–4, medium 5–9, high 10–16, critical 17–25. Editing, deletion
and residual evaluation are deferred.

## Initial security controls

Migration 007 introduces organization-owned security controls and many-to-many
risk associations. Administrators and analysts create/link/unlink; readers query.
The Spanish UI includes control list, filtering, creation/detail and “Controles
asociados” on risk details, excluding already-linked controls from the selector.
The relationship documents a measure, preserves the risk score and makes no
effectiveness claim. Residual evaluation and control editing/deletion remain
future work. Versioned migration tests verify preservation of prior module data;
API and Chrome tests cover permissions, isolation, relations and interface flows.

## Responsible-user assignment

Migration 008 preserves existing records and initializes optional incident/risk
assignees to null. Only active administrators/analysts in the same organization
are eligible; only administrators may assign or clear. API responses and filters
include assignment information, while a minimal candidate endpoint exposes only
ID and name. The responsive Spanish interface provides safe displays, selectors
and filters reflecting these permissions.

Database guards prevent cross-tenant or ineligible assignments. Deactivation or
conversion to reader clears both resource collections in the account-update
transaction, preserving resources and all other relationships. Injected-failure
tests verify complete rollback. Assignment introduces no notifications/messages;
local business/user auditing is implemented by migration 009; authentication
auditing remains future work.


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
