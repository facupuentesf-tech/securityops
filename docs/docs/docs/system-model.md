# System Model

## Overview

SecurityOps is organized around several core entities that represent
the cybersecurity environment of an organization.

The main entities are:

- Users
- Roles
- Permissions
- Assets
- Risks
- Security Controls
- Incidents
- Audit Logs

## Users

Users are individuals who can access the SecurityOps platform.

Each user belongs to an organization and has one or more roles.

## Roles

Roles define what actions a user can perform within the platform.

Initial roles:

- Administrator
- Security Manager
- Auditor
- Employee

## Permissions

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

## Assets

Assets represent technological resources belonging to an organization.

Examples:

- Computers
- Servers
- Network devices
- Applications
- Databases
- Cloud resources

## Risks

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

## Security Controls

Security controls represent measures implemented to reduce or manage
security risks.

Examples:

- Multi-factor authentication
- Backups
- Access reviews
- Security policies
- Network segmentation

## Incidents

Incidents represent security events that have occurred or are being
investigated.

Each incident should contain:

- Description
- Severity
- Status
- Date
- Responsible person
- Related asset

## Audit Logs

Audit logs record important actions performed within the platform.

Examples:

- User creation
- Role changes
- Risk modifications
- Incident creation
- Permission changes
