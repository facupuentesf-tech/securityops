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

The current version is a local, multi-organization incident-management
prototype with server-enforced tenant isolation. It provides:

- Incident creation, listing, detail and optional status/severity filters.
- Status changes with persistent history recorded atomically with the update.
- Investigation notes with validation and persistent storage.
- User login/logout, scrypt password hashes, opaque server-side sessions in
  `HttpOnly` cookies and CSRF protection for state-changing requests.
- Administrator-managed user accounts and backend-enforced administrator,
  analyst and reader permissions.
- Organization-scoped users and incidents; the organization is derived from
  the authenticated account and cannot be selected through the API.
- Local commands to bootstrap the initial organization or create another
  organization together with its first administrator.
- User attribution for new status-history entries and notes.
- Versioned SQLite migrations that preserve existing incident data.
- A responsive Spanish-language HTML/CSS/JavaScript interface served by FastAPI.
- SQLite persistence, interactive API documentation and automated tests.

The application runs locally through Uvicorn on `127.0.0.1`. Migration 003
assigns all existing users and incidents to an initial organization and
preserves existing sessions, history and notes. Existing history and notes are
preserved but cannot be attributed to users retroactively. Incident status
history is still a specific incident feature, not the general audit module
envisioned below. Shared deployment is not implemented or supported.

## Original Project Scope and Future Work

The original project roadmap is preserved. Beyond the initial incident module,
the following capabilities remain future work:

1. Asset management
2. Risk management
3. Security controls
4. Extended incident management with responsible users and related assets
5. General audit logs
6. Dashboard and basic metrics

Features such as automated vulnerability scanning, advanced compliance
automation and artificial intelligence assistance will be considered
for future versions.

React, PostgreSQL and Docker remain options for later stages; the implemented
version uses plain HTML/CSS/JavaScript, Python with FastAPI and SQLite.
