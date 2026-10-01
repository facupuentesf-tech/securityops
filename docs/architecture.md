# System Architecture

## Overview

SecurityOps will use a layered web application architecture.

The main components are:

- Frontend
- Backend API
- Database

The backend will act as the main security boundary between users and
the application's data.

## Architecture

```text
User
 |
 v
Frontend
 |
 | HTTP / HTTPS
 v
Backend API
 |
 | SQL
 v
Database
