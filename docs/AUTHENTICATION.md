# Authentication & Office Permissions — Phase 2.5

## Overview

The RSSB Office Data Platform implements a secure, stateless authentication and Role-Based Access Control (RBAC) security layer. The implementation utilizes industry-standard cryptographic primitives: **salted bcrypt** for password hashing and **HMAC-SHA256 (HS256) JSON Web Tokens (PyJWT)** for bearer session verification.

Permissions are strictly enforced on the **backend API layer** across all office-data endpoints, protecting document ingestion, verification/approval workflows, data querying, and provenance auditing.

---

## 1. Authentication Architecture

```
┌────────────────────────────────────────────────────────┐
│                      Client Browser                    │
│    (Next.js Frontend / API Client / Office Terminal)   │
└───────────────────────────┬────────────────────────────┘
                            │
              1. POST /api/v1/auth/login
                 { username, password }
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                   FastAPI Backend                      │
│                                                        │
│  2. bcrypt.checkpw(plain_password, user.hashed_pw)    │
│  3. Issue JWT Bearer Token                             │
│     Claims: sub (username), role, user_id, exp, iat    │
└───────────────────────────┬────────────────────────────┘
                            │
              4. Return access_token & User Profile
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                   Subsequent Requests                  │
│     Header: 'Authorization: Bearer <access_token>'     │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│           FastAPI RBAC Security Dependencies           │
│                                                        │
│  - get_current_user: Decodes JWT, validates signature  │
│    and expiration, verifies user in DB is active       │
│  - require_permission(perm): Checks role matrix       │
│    * Missing/Invalid Token -> HTTP 401 Unauthorized    │
│    * Insufficient Role     -> HTTP 403 Forbidden       │
└────────────────────────────────────────────────────────┘
```

---

## 2. Office Roles & Permissions Matrix

The platform defines four clear office roles reflecting the operational workflows of the RSSB office data ecosystem:

| Role Code | Role Name | Description | Allowed Permissions |
|---|---|---|---|
| `admin` | Office Administrator | Full access to all endpoints, user management, reviews, uploads, and search. | `read`, `read_sources`, `upload`, `review`, `admin` |
| `reviewer` | Office Reviewer | Validates, approves, rejects, and flags documents for correction. Can query data and inspect source provenance. | `read`, `read_sources`, `review` |
| `uploader` | Data Operator | Uploads Excel and PDF attendance, duty assignment, and vehicle data files. Can query data and inspect source provenance. | `read`, `read_sources`, `upload` |
| `viewer` | Office Viewer | Read-only access to execute natural language queries and view provenance/source previews. | `read`, `read_sources` |

### Explicit Permissions

- **`read`**: Permission to run natural language searches and structured data queries (`POST /api/v1/query`).
- **`read_sources`**: Permission to retrieve source provenance metadata and contextual previews (`GET /api/v1/sources/*`).
- **`upload`**: Permission to ingest Excel (`.xlsx`, `.xlsm`) and PDF (`.pdf`) documents (`POST /api/v1/documents/upload`).
- **`review`**: Permission to trigger validation, approve, reject, or request corrections on documents (`POST /api/v1/documents/{id}/validate`, `/approve`, `/reject`, `/needs-correction`).
- **`admin`**: Administrative rights across all system operations.

---

## 3. Protected API Endpoints

All office data endpoints enforce permissions at the controller boundary:

| Endpoint | Method | Required Permission | Allowed Roles | Error on Missing Auth | Error on Wrong Role |
|---|---|---|---|---|---|
| `/api/v1/auth/login` | `POST` | Public | All | — | — |
| `/api/v1/auth/me` | `GET` | Authenticated | All authenticated users | `401 Unauthorized` | — |
| `/api/v1/auth/seed` | `POST` | Public / Admin | Development & Maintenance | — | — |
| `/api/v1/documents/upload` | `POST` | `upload` | `admin`, `uploader` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/documents/{id}/validate` | `POST` | `review` | `admin`, `reviewer` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/documents/{id}/validation` | `GET` | `read` | `admin`, `reviewer`, `uploader`, `viewer` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/documents/{id}/issues` | `GET` | `read` | `admin`, `reviewer`, `uploader`, `viewer` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/documents/{id}/approve` | `POST` | `review` | `admin`, `reviewer` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/documents/{id}/reject` | `POST` | `review` | `admin`, `reviewer` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/documents/{id}/needs-correction` | `POST` | `review` | `admin`, `reviewer` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/query` | `POST` | `read` | `admin`, `reviewer`, `uploader`, `viewer` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/sources/{id}` | `GET` | `read_sources` | `admin`, `reviewer`, `uploader`, `viewer` | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/sources/{id}/preview` | `GET` | `read_sources` | `admin`, `reviewer`, `uploader`, `viewer` | `401 Unauthorized` | `403 Forbidden` |

---

## 4. Default Development & Test Credentials

The system provides default seed accounts for development and automated testing:

| Username | Password | Role | Email | Capabilities |
|---|---|---|---|---|
| `admin` | `admin123` | `admin` | `admin@rssb.local` | Upload, review, validate, approve/reject, search, view sources |
| `reviewer` | `reviewer123` | `reviewer` | `reviewer@rssb.local` | Validate, approve/reject, request corrections, search, view sources |
| `uploader` | `uploader123` | `uploader` | `uploader@rssb.local` | Upload Excel and PDF files, search, view sources |
| `viewer` | `viewer123` | `viewer` | `viewer@rssb.local` | Search and view sources (upload and review actions are forbidden) |

> Default accounts are seeded automatically on application startup and can also be triggered via `POST /api/v1/auth/seed`.

---

## 5. Environment Variables

Authentication is configured via environment variables in `backend/.env`:

| Variable | Default Value | Description |
|---|---|---|
| `JWT_SECRET_KEY` | `rssb-office-data-platform-dev-secret-key-change-in-production-2026` | Cryptographic secret key used to sign and verify HMAC-SHA256 JWT tokens. Must be >= 32 characters in production. |
| `JWT_ALGORITHM` | `HS256` | JWT signature algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24 hours) | Token lifespan in minutes before expiration. |
| `AUTH_ENFORCED` | `false` | When `true`, all requests without a valid Bearer token receive `401 Unauthorized`. When `false` (dev mode), requests with tokens are strictly validated; requests without tokens fall back to dev context to allow seamless local testing. |

---

## 6. Security Behavior

### Unauthenticated Access
- A request to any protected endpoint with an invalid, expired, corrupt, or missing token (when `AUTH_ENFORCED=true`) is rejected immediately with:
  ```json
  {
    "detail": "Authentication required. Please provide a valid Bearer token."
  }
  ```
  Status: `HTTP 401 Unauthorized`.
  Response header: `WWW-Authenticate: Bearer`.

### Unauthorized Role Access
- A caller presenting a valid JWT token whose assigned role lacks the required permission is rejected with:
  ```json
  {
    "detail": "Forbidden: role 'viewer' does not have 'upload' permission."
  }
  ```
  Status: `HTTP 403 Forbidden`.

### Password Security
- Passwords are never stored in plaintext. They are hashed using `bcrypt` with unique cryptographic salts (`bcrypt.gensalt()`).
- Verification is performed in constant time via `bcrypt.checkpw()`.
- Passwords and hashed strings are excluded from all API responses and logs.

### Database Migration
- The user table is managed through Alembic migration revision `a8b236c71d8a_add_users_table.py`.
