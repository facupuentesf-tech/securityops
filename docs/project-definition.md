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

## First Functional Version: Implemented Scope

The current version is a local incident-management prototype. It provides:

- Incident creation, listing, detail and optional status/severity filters.
- Status changes with persistent history recorded atomically with the update.
- Investigation notes with validation and persistent storage.
- A responsive Spanish-language HTML/CSS/JavaScript interface served by FastAPI.
- SQLite persistence, interactive API documentation and automated tests.

The application runs locally through Uvicorn on `127.0.0.1`. It has no
authentication, user management or permission enforcement. Data is not separated
by company and changes are not attributed to users. The status history is a
specific incident feature, not the general audit module envisioned below.

## Original Project Scope and Future Work

The original project roadmap is preserved. Beyond the initial incident module,
the following capabilities remain future work:

1. User management
2. Role-based access control
3. Asset management
4. Risk management
5. Security controls
6. Extended incident management with responsible users and related assets
7. Audit logs
8. Dashboard and basic metrics

Features such as automated vulnerability scanning, advanced compliance
automation and artificial intelligence assistance will be considered
for future versions.

React, PostgreSQL and Docker remain options for later stages; the implemented
version uses plain HTML/CSS/JavaScript, Python with FastAPI and SQLite.
