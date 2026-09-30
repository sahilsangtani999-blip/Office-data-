# Architecture — RSSB Office Data Platform

## Overview

The RSSB Office Data Platform is a full-stack web application that enables users to search and manage office data. The platform follows a three-tier architecture with a clear separation between the frontend, backend, and database layers.

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│                   Client Browser                │
│              http://localhost:3000               │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              Frontend (Next.js)                 │
│         TypeScript · React · SSR/CSR            │
│              Port 3000                          │
└──────────────────────┬──────────────────────────┘
                       │ HTTP / JSON
                       ▼
┌─────────────────────────────────────────────────┐
│              Backend (FastAPI)                  │
│         Python · Uvicorn · SQLAlchemy           │
│              Port 8000                          │
│                                                 │
│  Endpoints:                                     │
│    GET /health                                  │
└──────────────────────┬──────────────────────────┘
                       │ SQL (via SQLAlchemy)
                       ▼
┌─────────────────────────────────────────────────┐
│            Database (PostgreSQL 17)             │
│         Port 5432                               │
│                                                 │
│  Managed via Alembic migrations                 │
└─────────────────────────────────────────────────┘
```

## Components

### Frontend — Next.js + TypeScript

- **Location**: `frontend/`
- **Purpose**: User-facing web interface for searching and viewing office data.
- **Runtime**: Node.js
- **Port**: 3000

### Backend — FastAPI + Python

- **Location**: `backend/`
- **Purpose**: REST API serving data to the frontend, handling business logic, and managing database access.
- **Runtime**: Python 3.11+ with Uvicorn
- **Port**: 8000
- **ORM**: SQLAlchemy 2.x (async-ready)
- **Migrations**: Alembic

### Database — PostgreSQL 17

- **Purpose**: Persistent storage for all application data.
- **Port**: 5432
- **Data directory**: `postgres-data/` (git-ignored)

### Data Directory

- **Location**: `data/`
- **Purpose**: Local file storage for uploads, processed files, and exports.
- **Subdirectories**:
  - `uploads/` — raw incoming files
  - `processed/` — files after processing
  - `exports/` — generated export files
- All subdirectories are git-ignored; only the directory structure is tracked.

## Security & Access Control (Phase 2.5)

The platform implements backend-enforced Role-Based Access Control (RBAC):
- **Authentication**: Salted bcrypt password hashing and HMAC-SHA256 JWT Bearer access tokens.
- **Roles**:
  - `admin`: Full administrative control across all features and operations.
  - `reviewer`: Validation, approval, rejection, and correction workflows.
  - `uploader`: Ingestion of Excel and PDF office documents.
  - `viewer`: Read-only queries, calculations, and provenance inspection.
- **Enforcement**: Permissions are verified at API boundaries via FastAPI dependencies (`get_current_user`, `require_permission`). See `docs/AUTHENTICATION.md` for complete specification.

## Reports Generation & Data Export (Phase 3.1)

The platform provides an institutional reporting and export engine:
- **Compilation**: Deterministic aggregation of attendance figures, sewadar duty assignments, and vehicle transportation records.
- **Export Formats**: Multi-sheet formatted Excel (`.xlsx`) with brand styling and standard CSV (`.csv`).
- **REST Endpoints**: `/api/v1/reports` endpoints for compilation, listing, detail retrieval, and authenticated file downloads.
- **Search Discoverability**: Natural-language search queries retrieve matching reports directly with export links. See `docs/REPORTS.md` for details.

## Configuration

All sensitive configuration is managed via environment variables loaded from a `.env` file (never committed). See `backend/.env.example` for the template.

## Key Design Decisions

1. **Separation of concerns**: Frontend and backend are independent applications that communicate over HTTP.
2. **Environment-based config**: No secrets in source code. All configuration via `.env`.
3. **Migration-first database**: Schema changes are always managed through Alembic migrations.
4. **Backend-enforced security**: Role permissions are validated at the server API layer, preventing unauthorized operations even if client-side validation is bypassed.
5. **Minimal dependencies**: Only install what is actively used.
