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
state, new state and UTC time of an effective change. Repeating the current
state does not create another entry. History starts with changes made through
the implemented feature and does not record incident creation or identify an actor.

An **investigation note** belongs to one incident and contains text, an ID and
a UTC creation time. Notes can be created and listed, not edited or deleted.
Their content is trimmed and limited to 1–5000 characters. They do not change
the incident's status or its history.

Each incident has zero or more history entries and notes. Both collections are
persistent in SQLite; existing incidents without entries return empty lists.
History is ordered by ID, and notes by creation time with ID as a tiebreaker.

The HTML/CSS/JavaScript interface is in Spanish, calls the FastAPI API and
formats dates in the browser's timezone. This version runs locally and has no
authentication, user accounts, permissions or organization isolation.

## Original Domain Vision: Future Work

The following entities and relationships preserve the original vision. Users,
roles, permissions, assets, risks, controls and general audit logs are not yet
implemented. Responsible users and asset links for incidents are also future work.

The planned domain entities are:

- Users
- Roles
- Permissions
- Assets
- Risks
- Security Controls
- Incidents
- Audit Logs

### Users

Users are individuals who can access the SecurityOps platform.

Each user belongs to an organization and has one or more roles.

### Roles

Roles define what actions a user can perform within the platform.

Initial roles:

- Administrator
- Security Manager
- Auditor
- Employee

### Permissions

Permissions define specific actions that users can perform.

Examples:

- Create user
- Modify user
- Delete user
- View assets
- Create risk
- Modify risk
- View incidents
- Create incident

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
