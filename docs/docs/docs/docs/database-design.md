# Database Design

## Overview

The SecurityOps database will use a relational database model.

The main entities are:

- Companies
- Users
- Roles
- Permissions
- Assets
- Risks
- Security Controls
- Incidents
- Audit Logs

## Companies

Represents an organization using SecurityOps.

Main fields:

- id
- name
- created_at

## Users

Represents users who can access the platform.

Main fields:

- id
- company_id
- name
- email
- password_hash
- role_id
- created_at

## Roles

Represents the roles assigned to users.

Main fields:

- id
- name
- description

Initial roles:

- Administrator
- Security Manager
- Auditor
- Employee

## Permissions

Represents specific actions that can be performed.

Main fields:

- id
- name
- description

Examples:

- users.create
- users.read
- users.update
- users.delete
- assets.read
- assets.create
- risks.read
- risks.create
- incidents.create

## Assets

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

## Risks

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

## Security Controls

Represents security measures used to reduce risks.

Main fields:

- id
- company_id
- name
- description
- status
- owner_id
- created_at

## Incidents

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

## Audit Logs

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
