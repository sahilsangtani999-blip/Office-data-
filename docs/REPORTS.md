# Phase 3.1 — Reports Generation & Data Export Engine

## Overview

Phase 3.1 introduces an institutional, deterministic report compilation and export engine for the RSSB Office Data Platform. It enables authorized office staff to aggregate verified records across attendance, duty rosters, and vehicle logs into professional multi-sheet Excel workbooks (`.xlsx`) and standard CSV files (`.csv`), complete with KPI summaries and natural-language search discoverability.

---

## Architectural Principles

1. **Zero Database Migrations Required**:
   - Leverages the existing PostgreSQL `reports` table (Table 12 in `backend/app/models.py`), including attributes `id`, `name`, `report_type`, `reporting_period_start`, `reporting_period_end`, `status`, `created_by`, `created_at`, and `updated_at`.
2. **Local, Self-Contained File Generation**:
   - Compiles `.xlsx` files using `openpyxl` styled with RSSB brand aesthetic (primary maroon header `#941B1B`, white bold text, thin light gray borders, auto-adjusted column dimensions).
   - Generates clean, RFC 4180-compliant `.csv` files.
   - Saves generated files to `data/exports/` with sanitized filenames (`<safe_name>_<uuid4_prefix>.<ext>`).
3. **Strict RBAC Enforcement**:
   - Permission `generate_reports` assigned to `admin` and `reviewer` roles.
   - Standard `read` permission required to list, inspect, and download reports.
   - Deletion restricted strictly to `admin`.
4. **Natural Language Search Integration**:
   - Queries mentioning "report", "monthly report", "summary report", etc., are intercepted by `SearchService`, returning registered report records with direct download URLs in supporting records.

---

## Supported Report Types

| Report Type | Identifier | Included Data | Excel Sheets |
| :--- | :--- | :--- | :--- |
| **Monthly Summary** | `monthly` | Combined Attendance, Duty Rosters, and Vehicles for a selected month or period | 1. Executive Summary<br>2. Attendance Breakdown<br>3. Duty Assignments<br>4. Vehicles Logged |
| **Attendance Summary** | `attendance_summary` | Centre-wise dates, male/female/children counts, total attendance, and calculated averages | 1. Summary & Average KPIs<br>2. Daily Attendance Records |
| **Duty Roster Summary** | `duty_summary` | Departmental sewadar assignments, shifts, dates, and duties | 1. Department Breakdown<br>2. Detailed Duty Rosters |
| **Vehicle Log Summary** | `vehicle_report` | Transportation movements, vehicle types, license plates, and driver logs | 1. Vehicle Movement Roster |

---

## REST API Specification

### 1. Generate Report
- **Endpoint**: `POST /api/v1/reports/generate`
- **Permissions**: Requires `generate_reports` (`admin`, `reviewer`)
- **Request Body**:
  ```json
  {
    "report_type": "monthly",
    "name": "Indore Centre - September 2026",
    "reporting_period_start": "2026-09-01",
    "reporting_period_end": "2026-09-30",
    "formats": ["xlsx", "csv"]
  }
  ```
- **Response**: `200 OK` (`ReportDetailResponse` with calculated KPIs, file paths, and download URLs).

### 2. List Reports
- **Endpoint**: `GET /api/v1/reports`
- **Permissions**: Requires `read` (`admin`, `reviewer`, `uploader`, `viewer`)
- **Query Parameters**:
  - `skip` (int, default: 0)
  - `limit` (int, default: 50)
  - `report_type` (optional filter)
- **Response**: `200 OK` (`ReportListResponse` containing array of `ReportItemResponse`).

### 3. Get Report Details
- **Endpoint**: `GET /api/v1/reports/{id}`
- **Permissions**: Requires `read`
- **Response**: `200 OK` (`ReportDetailResponse` with KPIs and metadata).

### 4. Download Report File
- **Endpoint**: `GET /api/v1/reports/{id}/download?format=xlsx|csv`
- **Permissions**: Requires `read` (authenticated Bearer token)
- **Response**: `200 OK` (binary `FileResponse` with `Content-Disposition: attachment; filename="..."`).

### 5. Delete Report
- **Endpoint**: `DELETE /api/v1/reports/{id}`
- **Permissions**: Requires `admin`
- **Response**: `200 OK` (`{"message": "Report ... deleted successfully"}`).

---

## Frontend Integration

1. **Office Reports & Exports Action**:
   - Prominently located in the primary action bar of the main dashboard (`app/page.tsx`).
2. **`ReportsModal`**:
   - **Tab 1: Generate Report**:
     - Allows selecting report type, optional custom title, date range presets, and export formats (`.xlsx`, `.csv`).
     - Live compilation state with loading indicator.
     - Interactive success card displaying calculated KPI metrics (Total Attendance, Avg / Session, Duty Rosters, Vehicles) and direct download buttons.
     - Role-aware notice when accessed by `uploader` or `viewer` accounts.
   - **Tab 2: Report Archive**:
     - Lists all historical reports with status badge, type, period, creator, and direct download links (`XLSX`, `CSV`).
3. **Search Results Integration**:
   - Enhanced `SearchResultCard` detects report-type records and presents report name, type, date span, creator, and export action links.

---

## Automated Test Coverage

Suite: `backend/tests/test_reports.py` (7 comprehensive integration tests):
1. `test_1_generate_monthly_report_service`: Generates monthly report, verifies database persistence, KPI calculations, and Excel/CSV files in `data/exports/`.
2. `test_2_generate_attendance_summary_report`: Generates attendance-specific report, validates attendance KPI summation.
3. `test_3_generate_duty_and_vehicle_reports`: Generates and validates duty and vehicle specific reports.
4. `test_4_api_generate_report_rbac`: Validates RBAC enforcement (`admin` and `reviewer` can generate; `uploader` and `viewer` receive `403 Forbidden`).
5. `test_5_api_download_report_files`: Verifies authenticated download endpoints for `.xlsx` and `.csv` files.
6. `test_6_api_delete_report_admin_only`: Confirms only `admin` can delete reports (`reviewer` receives `403 Forbidden`).
7. `test_7_search_reports_query`: Verifies natural language query "show monthly reports" retrieves report records via `SearchService`.

**Full backend test suite**: All 124 tests pass cleanly.
**Frontend build**: Next.js Turbopack production build succeeds with 0 errors.
