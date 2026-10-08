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

An **account** has a display name, unique email, scrypt password hash, active
flag, exactly one of three roles and belongs to one organization. Administrators
create and manage accounts only in their own organization; there is no public
registration. The initial administrator is bootstrapped with
`python backend/main.py create-admin`, before any user exists. Additional
organizations and their initial administrators are created locally with
`python backend/main.py create-organization`.

An **organization** owns its users and incidents. The authenticated user's
organization is loaded by the server from the account record on each request;
the client cannot choose or change it. Incident list/filter/detail/status,
history, notes and user administration are all organization-scoped. Attempts
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
| Manage users and reset passwords | Yes | No | No |

The HTML/CSS/JavaScript interface is in Spanish, calls the FastAPI API and
formats dates in the browser's timezone. UI visibility reflects role
permissions, but access is enforced by the backend. The prototype supports
multiple isolated organizations while remaining local; it is not configured
for shared deployment.

## Original Domain Vision: Future Work

The following entities and relationships preserve the original vision.
Assets, risks, controls and general audit logs are not yet implemented.
Responsible users and asset links for incidents are also future work.

The planned domain entities are:

- Organizations / tenant isolation (implemented for users and incidents)
- Assets
- Risks
- Security Controls
- Incidents
- Audit Logs

### Assets

Assets represent technological resources belonging to an organization.

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
