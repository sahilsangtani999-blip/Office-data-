# Data Validation & Review Subsystem

## Overview

The Data Validation & Review subsystem in the RSSB Office Data Platform classifies every imported document and individual office data record according to data quality and review lifecycle states.

The subsystem operates strictly within the 12-table foundation created in Phase 1.1 with **zero database schema modifications**. All validation findings, audit trails, and review actions are persisted directly into existing PostgreSQL tables (`documents`, `document_versions`, `source_references`, `attendances`, `assignments`, `vehicle_wheel_data`, and `reports`).

---

## 1. Controlled Lifecycle States

### Document & Version Statuses

Documents transition through a formal lifecycle:

| Status | Description |
|---|---|
| `imported` | Initial state upon file upload before validation is executed. |
| `validated` | Automated structural and concept checks completed with zero errors or blocking warnings. |
| `pending_review` | Contains ambiguous columns, approximate counts, unmapped terminology, or logical duplicates requiring human verification. |
| `approved` | Formally approved by an authorized reviewer for official office use. |
| `rejected` | Formally rejected by an authorized reviewer (e.g. corrupt file, wrong upload, unsupported structure). |
| `needs_correction` | Contains structural failures, unparseable values, or missing mandatory fields requiring resubmission. |
| `active` | Operational state for approved documents. |
| `superseded` | Replaced by a newer version of the same document. |
| `archived` | Historical record retained for audit provenance but no longer active. |

### Individual Record Statuses

Individual records extracted from documents (`attendances`, `assignments`, `vehicle_wheel_data`) are classified into:

| Status | Description |
|---|---|
| `valid` | Fully parsed and conforms to known concept schema. |
| `needs_review` | Contains approximate values (e.g. `"approx 320"`), unrecognized columns, unmapped terminology, or logical duplicates. |
| `invalid` | Contains fatal parsing failures (e.g. missing dates, non-numeric strings, missing provenance linkage). |
| `active` | Active operational record. |

---

## 2. Issue Severities and Types

Issues discovered during validation are categorized by severity:

| Severity | Impact | Document State Result |
|---|---|---|
| `INFO` | Informational notes (e.g., extra unmapped columns preserved as review metadata, empty pages). | Does not block `validated` status. |
| `WARNING` | Ambiguities or potential discrepancies (e.g., approximate counts, unmapped terminology, logical duplicates). | Sets document status to `pending_review`. |
| `ERROR` | Data integrity or structural failures (e.g., missing mandatory dates, non-numeric values, missing provenance). | Sets document status to `needs_correction`. |

### Specific Issue Types

- **Structural**:
  - `FILE_UNREADABLE`: Storage file is missing or unreadable on disk.
  - `HASH_MISMATCH`: File bytes SHA-256 differs from recorded `DocumentVersion.content_hash`.
  - `MISSING_PROVENANCE`: Record has missing `source_reference_id` or `SourceReference` has missing `document_version_id`.
  - `DUPLICATE_DOCUMENT`: Content hash identical to existing document version.
- **Excel Specific**:
  - `EMPTY_SHEET`: Sheet has no readable data rows.
  - `MISSING_HEADERS`: Sheet lacks a recognizable header row.
  - `AMBIGUOUS_COLUMNS`: Column headers cannot be reliably mapped to known concepts.
  - `UNKNOWN_COLUMNS`: Extra columns present. Preserved in `source_text` and reported as `INFO` review information (never rejected).
  - `MISSING_DATE`: Date column is empty or null on a row.
  - `INVALID_DATE`: Date value cannot be parsed.
  - `MISSING_SATSANG_GHAR`: Satsang Ghar reference missing or null.
  - `INVALID_NUMERIC_VALUE`: Count value is invalid or non-numeric.
  - `EMPTY_ROW`: Blank row detected within data range.
  - `DUPLICATE_RECORD`: Logical duplicate detected within sheet.
- **PDF Specific**:
  - `PDF_UNREADABLE`: PDF cannot be opened or parsed.
  - `EMPTY_PAGE`: Page has no readable text content and no tables.
  - `TABLE_EXTRACTION_ISSUE`: Malformed table or uneven column grids.
  - `AMBIGUOUS_STRUCTURED_CONTENT`: Extracted table headers do not match known concept schema.
  - `UNSUPPORTED_MAPPING`: Uncertain field mapping.
- **Vocabulary & Terminology**:
  - `UNKNOWN_TERMINOLOGY`: Role codes or duty titles outside approved vocabulary (e.g. not matching `SK`, `SR`, `VIDEO CD`, `VCD`).

---

## 3. Duplicate Handling

The platform distinguishes between two types of duplicates:

1. **Duplicate Document**:
   - Evaluated by 64-character SHA-256 content hash of the raw file.
   - Halts processing immediately; no duplicate `DocumentVersion` or duplicate entity records are created.
   - Returns `duplicate_status: "duplicate"` alongside existing document and version IDs.

2. **Duplicate Record**:
   - Evaluated by logical key within imported data:
     - `Attendance`: `(date, satsang_ghar_id, count_value)`
     - `Assignment`: `(date, satsang_ghar_id, person_id, role_id)`
     - `VehicleWheelData`: `(date, satsang_ghar_id, vehicle_type)`
   - **No Silent Deletion**: Duplicate records are **never silently deleted**.
   - Both records are retained in PostgreSQL with distinct row-level `SourceReference` provenance.
   - Flagged with `WARNING: DUPLICATE_RECORD` and marked as `needs_review` for human verification.

---

## 4. "Needs Review" Behavior

The platform never guesses unconfirmed data. The following conditions safely trigger `Needs Review`:
- Approximate or qualified counts (e.g. `"approx 320"`, `"50+"`).
- Unrecognized or ambiguous sheet/table column headers.
- Unmapped role or duty terminology (outside approved vocabulary).
- Logical duplicate records within the same document.
- Missing optional data fields.

---

## 5. Review & Approval Workflow

### Permission Preparation
All review actions require a `ReviewerContext`. In development/test mode, default authorized contexts are provided (`dev-test-user`). In future production phases, JWT/RBAC middleware will populate this context from authenticated tokens. Unauthorized requests raise `HTTP 403 Forbidden`.

### Available Review Actions

- **Approve**:
  Transitions document and versions to `approved`. Logs review audit entry with reviewer ID, username, notes, and timestamp in `SourceReference` and updates `Report.status`.
- **Reject**:
  Transitions document and versions to `rejected`. Requires a mandatory `reason` string and logs rejection audit in `SourceReference`.
- **Needs Correction**:
  Transitions document and versions to `needs_correction`. Requires mandatory `instructions` string detailing corrective actions.

---

## 6. API Endpoints

All validation and review endpoints are mounted under `/api/v1/documents`:

| Method | Path | Summary | Description |
|---|---|---|---|
| `POST` | `/api/v1/documents/{document_id}/validate` | Trigger Validation | Runs full validation suite on document and persists report and issues. |
| `GET` | `/api/v1/documents/{document_id}/validation` | Get Validation Report | Retrieves structured summary (status, record counts, issues count). |
| `GET` | `/api/v1/documents/{document_id}/issues` | List Issues | Lists issues, optionally filtered by `?severity=ERROR\|WARNING\|INFO`. |
| `POST` | `/api/v1/documents/{document_id}/approve` | Approve Document | Approves document with optional notes. |
| `POST` | `/api/v1/documents/{document_id}/reject` | Reject Document | Rejects document with mandatory reason. |
| `POST` | `/api/v1/documents/{document_id}/needs-correction` | Needs Correction | Flags document for corrections with mandatory instructions. |

---

## 7. Known Limitations & Intentionally Unresolved RSSB Rules

To preserve architectural integrity and avoid speculative business logic, the following rules are intentionally NOT enforced:
1. **Major Center → Satsang Ghar Hierarchy**: No parent-child constraint is enforced between Major Centers and Satsang Ghars.
2. **Person Multi-Role Restrictions**: No constraint limits how many roles a person can hold.
3. **Official Attendance Limits**: No upper or lower bounds are assumed for attendance or vehicle counts.
4. **Naming / Spelling Variations**: Satsang Ghar and Person names are stored as written without fuzzy unification or guessing.
5. **Role Vocabulary**: Only known role codes (`SK`, `SR`, `VIDEO CD`, `VCD`, `READER`, `KARTA`, `SPEAKER`) are approved. Any other terminology is flagged as `UNKNOWN_TERMINOLOGY` (`Needs Review`).
