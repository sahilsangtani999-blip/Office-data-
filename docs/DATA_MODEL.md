# RSSB Office Data Platform — Data Model Documentation

## Overview

This document details the database schema established in **Phase 1.1 — RSSB Office Data Foundation**. The schema is built using **SQLAlchemy 2.0 ORM** and managed with **Alembic** migrations on **PostgreSQL 17**.

The design models verified internal office concepts without inventing unconfirmed business rules, hierarchies, or validation constraints.

---

## Entity Relationship Overview

```
 [DataSource] 1──* [Document] 1──* [DocumentVersion]
                         │                 │
                         └──┐           ┌──┘
                            ▼           ▼
                         [SourceReference] ◄────────┐ (provenance)
                         ▲       ▲       ▲          │
                         │       │       │          │
                 ┌───────┘       │       └──────┐   │
                 │               │              │   │
        [Assignment]      [Attendance]   [VehicleWheelData]
         │    │    │             │              │
         │    │    └─────────┐   │   ┌──────────┘
         │    ▼              ▼   ▼   ▼
         │  [Role]          [SatsangGhar]
         ▼
      [Person]              [MajorCenter] (Standalone)

      [Report] (Metadata)
```

---

## Table Definitions

### 1. `data_sources`
Represents an ingestion channel or origin for files and records (e.g., Google Drive folders, SSM systems, local directories, manual uploads).

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `name` | `VARCHAR(255)` | No | — | Human-readable name of the source (Indexed) |
| `source_type` | `VARCHAR(100)` | No | — | Type identifier (e.g., `google_drive`, `ssm`, `manual_upload`) (Indexed) |
| `status` | `VARCHAR(50)` | No | `'active'` | Operating status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

### 2. `documents`
Represents a distinct file received from a `DataSource`.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `data_source_id` | `UUID` | Yes | — | FK to `data_sources.id` (ON DELETE SET NULL) (Indexed) |
| `original_filename` | `VARCHAR(500)` | No | — | Original file name as received (Indexed) |
| `document_type` | `VARCHAR(100)` | Yes | — | Classification/extension (e.g., `pdf`, `xlsx`, `docx`) (Indexed) |
| `status` | `VARCHAR(50)` | No | `'active'` | Processing status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

### 3. `document_versions`
Represents a physical, immutable snapshot of a document, tracking file hashes and storage paths.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `document_id` | `UUID` | No | — | FK to `documents.id` (ON DELETE CASCADE) (Indexed) |
| `version_number` | `INTEGER` | No | `1` | Sequential version index |
| `content_hash` | `VARCHAR(128)` | Yes | — | SHA-256 hash for deduplication and integrity (Indexed) |
| `storage_path` | `VARCHAR(1000)` | Yes | — | File path in storage runtime |
| `status` | `VARCHAR(50)` | No | `'active'` | Version status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Timestamp of version ingestion |

---

### 4. `satsang_ghars`
Represents an individual Satsang Ghar center/location.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `name` | `VARCHAR(255)` | No | — | Official name of Satsang Ghar (Indexed) |
| `status` | `VARCHAR(50)` | No | `'active'` | Operational status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

> **Design Note**: A foreign key from `SatsangGhar` to `MajorCenter` is **intentionally omitted** pending confirmation of the official hierarchy (1-to-many, many-to-many, or jurisdictional).

---

### 5. `major_centers`
Represents a Major Center administrative unit.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `name` | `VARCHAR(255)` | No | — | Name of Major Center (Indexed) |
| `status` | `VARCHAR(50)` | No | `'active'` | Operational status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

### 6. `persons`
Represents an individual volunteer, speaker, reader, or coordinator.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `name` | `VARCHAR(255)` | No | — | Full name as recorded in office documents (Indexed) |
| `status` | `VARCHAR(50)` | No | `'active'` | Active status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

### 7. `roles`
Represents designated duties/roles (e.g., SK for Satsang Karta, SR for Satsang Reader).

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `code` | `VARCHAR(50)` | No | — | Unique role code (e.g., `SK`, `SR`) (Unique Index) |
| `name` | `VARCHAR(255)` | No | — | Descriptive name (e.g., "Satsang Karta") |
| `description` | `TEXT` | Yes | — | Additional role details |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

### 8. `source_references`
Reusable data provenance model tracing extracted values back to their specific origin coordinates in a document.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `document_id` | `UUID` | Yes | — | FK to `documents.id` (ON DELETE SET NULL) (Indexed) |
| `document_version_id` | `UUID` | Yes | — | FK to `document_versions.id` (ON DELETE SET NULL) (Indexed) |
| `page_number` | `INTEGER` | Yes | — | Page number (for PDF / multi-page documents) |
| `sheet_name` | `VARCHAR(255)` | Yes | — | Sheet/tab name (for Excel workbooks) |
| `row_number` | `INTEGER` | Yes | — | Row number in sheet |
| `cell_or_range` | `VARCHAR(100)` | Yes | — | Cell coordinate or range (e.g., `B14`, `A1:F20`) |
| `source_text` | `TEXT` | Yes | — | Exact raw text snippet from the document |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |

---

### 9. `assignments`
Flexible duty assignments (e.g., speaker and reader schedules).

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `date` | `DATE` | Yes | — | Date of scheduled duty (Indexed) |
| `satsang_ghar_id` | `UUID` | Yes | — | FK to `satsang_ghars.id` (ON DELETE SET NULL) (Indexed) |
| `person_id` | `UUID` | Yes | — | FK to `persons.id` (ON DELETE SET NULL) (Indexed) |
| `role_id` | `UUID` | Yes | — | FK to `roles.id` (ON DELETE SET NULL) (Indexed) |
| `description` | `TEXT` | Yes | — | Notes, topics, or program details |
| `source_reference_id` | `UUID` | Yes | — | FK to `source_references.id` (ON DELETE SET NULL) (Indexed) |
| `status` | `VARCHAR(50)` | No | `'active'` | Assignment status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

### 10. `attendances`
Recorded attendance figures for Satsang Ghar sessions.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `date` | `DATE` | Yes | — | Session date (Indexed) |
| `satsang_ghar_id` | `UUID` | Yes | — | FK to `satsang_ghars.id` (ON DELETE SET NULL) (Indexed) |
| `count_value` | `INTEGER` | Yes | — | Numeric parsed headcount |
| `raw_value` | `VARCHAR(255)` | Yes | — | Preserves raw office text (e.g., "approx 350") |
| `source_reference_id` | `UUID` | Yes | — | FK to `source_references.id` (ON DELETE SET NULL) (Indexed) |
| `status` | `VARCHAR(50)` | No | `'active'` | Record status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

### 11. `vehicle_wheel_data`
Records vehicle counts and parking/transport statistics.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `date` | `DATE` | Yes | — | Date of count (Indexed) |
| `satsang_ghar_id` | `UUID` | Yes | — | FK to `satsang_ghars.id` (ON DELETE SET NULL) (Indexed) |
| `count_value` | `INTEGER` | Yes | — | Numeric count of vehicles |
| `vehicle_type` | `VARCHAR(100)` | Yes | — | Classification (e.g., `2-wheeler`, `4-wheeler`, `bus`) (Indexed) |
| `raw_value` | `VARCHAR(255)` | Yes | — | Raw recorded text |
| `description` | `TEXT` | Yes | — | Additional notes |
| `source_reference_id` | `UUID` | Yes | — | FK to `source_references.id` (ON DELETE SET NULL) (Indexed) |
| `status` | `VARCHAR(50)` | No | `'active'` | Record status (Indexed) |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

### 12. `reports`
Stores metadata and registration for generated or ingested summary reports.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | No | `uuid.uuid4` | Primary Key |
| `name` | `VARCHAR(255)` | No | — | Title of report (Indexed) |
| `report_type` | `VARCHAR(100)` | No | — | Type (e.g., `monthly`, `sk_report`, `sr_report`, `vehicle_report`) (Indexed) |
| `reporting_period_start` | `DATE` | Yes | — | Start of period (Indexed) |
| `reporting_period_end` | `DATE` | Yes | — | End of period (Indexed) |
| `status` | `VARCHAR(50)` | No | `'draft'` | Lifecycle status (`draft`, `final`, `archived`) (Indexed) |
| `created_by` | `VARCHAR(255)` | Yes | — | User or system identifier |
| `created_at` | `TIMESTAMPTZ` | No | `now()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | No | `now()` | Last modification timestamp |

---

## Design Decisions & Boundary Enforcement

1. **UUID Primary Keys**:
   All 12 tables use native PostgreSQL `UUID` primary keys (`uuid.uuid4`) to support distributed creation, prevent predictable sequence enumeration, and simplify offline data preparation.

2. **Decoupled MajorCenter and SatsangGhar**:
   No foreign key relationship was imposed between `MajorCenter` and `SatsangGhar`. Because organizational hierarchy rules have not been formalized, premature relational constraints are avoided.

3. **Reusable Provenance Model (`SourceReference`)**:
   Extraction outputs from unstructured PDFs and structured Excel sheets have different coordinate models. By making all coordinate fields (`page_number`, `sheet_name`, `row_number`, `cell_or_range`, `source_text`) nullable, a single provenance schema supports all document types.

4. **Preservation of Raw Values**:
   `attendances` and `vehicle_wheel_data` maintain both a parsed integer (`count_value`) and a raw string (`raw_value`). This ensures data is not lost when non-standard text (e.g. ranges or approximations) appears in office files.

5. **No Speculative Business Rules**:
   - Role codes are not limited to hardcoded enums.
   - Entry fields (person, role, ghar, date) are nullable to allow incomplete historical files to be captured faithfully.
   - No mock or sample business records exist in the database.
