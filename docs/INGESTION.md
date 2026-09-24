# Data Ingestion Pipeline (Excel & PDF)

## Overview

The Data Ingestion subsystem in the RSSB Office Data Platform provides a unified, auditable, and resilient ingestion pipeline for office documents:
1. **Excel Workbooks** (`.xlsx`, `.xlsm`) via `openpyxl`
2. **PDF Documents** (`.pdf`) via `pdfplumber` and `PyMuPDF` (`fitz`)

Both pipelines feed into the same 12-table PostgreSQL schema, enforcing strict provenance tracking, SHA-256 duplicate detection, and "Needs Review" flagging without guessing unconfirmed business schemas.

---

## Unified Upload API

### Endpoint: `POST /api/v1/documents/upload`

Uploads and processes either an Excel workbook or a PDF document through a single unified endpoint.

#### Request
- **Content-Type**: `multipart/form-data`
- **Form Fields**:
  - `file`: Binary file (`.xlsx`, `.xlsm`, `.pdf`)
  - `data_source_name` *(optional)*: String (defaults to `"Manual Upload"`)

#### Routing Behavior
- Files ending in `.xlsx` or `.xlsm` are routed to `ingest_excel_file`.
- Files ending in `.pdf` are routed to `ingest_pdf_file`.
- All other extensions (`.csv`, `.txt`, `.doc`, etc.) are rejected with `HTTP 400 Bad Request`.

---

## PDF Ingestion Pipeline

### 1. Supported PDF Types
- **Text-based PDFs**: Multi-paragraph office notices, circulars, or letters. Full text is extracted per page and stored in `source_references` for future source preview and citation.
- **Tabular PDFs**: Documents containing grid tables (e.g. attendance sheets, assignment rosters, vehicle reports).
- **Multi-page PDFs**: Documents spanning any number of pages; page numbers are strictly preserved.

### 2. PDF Processing Libraries
- **`pdfplumber`**: Primary engine for precise layout and table extraction:
  - `page.find_tables()` identifies table structures.
  - `table.bbox` provides exact bounding box coordinates `(x0, top, x1, bottom)`.
  - `table.extract()` parses tabular cells into row and column arrays.
- **`PyMuPDF` (`fitz`)**: Fast PDF document handling, metadata extraction, and multi-page stream support.

### 3. SHA-256 Hashing & Duplicate Protection
- Before processing pages, the engine computes a 64-character SHA-256 checksum over the raw PDF file.
- The checksum is matched against `document_versions.content_hash`.
- If a match is found:
  - Ingestion immediately halts.
  - No duplicate `DocumentVersion` is created.
  - No duplicate structured records or source references are created.
  - The API returns `duplicate_status: "duplicate"` with the existing `document_id` and `version_id`.

### 4. Page-Level Text Extraction & Source Preview
For every page in the PDF:
- The raw text is extracted via `page.extract_text()`.
- A page-level `SourceReference` is saved:
  - `page_number`: 1-based page index
  - `row_number`: `None`
  - `cell_or_range`: `None`
  - `source_text`: Full extracted text of the page
- This enables downstream source preview and verbatim citation without re-parsing the PDF.

### 5. Table Extraction & Real Bounding Box Coordinates
- Tables on each page are detected using `page.find_tables()`.
- Bounding box coordinates are formatted as:
  ```
  bbox:[x0,top,x1,bottom]
  ```
  (e.g., `bbox:[50.0,80.0,550.0,180.0]`) and stored directly in `source_references.cell_or_range`.
- **Zero Schema Change**: Real bounding box coordinates are safely stored without modifying the existing PostgreSQL schema.
- **No Fabricated Coordinates**: Coordinates come directly from `pdfplumber`'s layout engine.

### 6. Controlled Concept Mapping & "Needs Review"
- Tables are mapped against recognized column patterns (Attendance, Assignment, Vehicle).
- For recognized tables:
  - Structured entities (`Attendance`, `Assignment`, `VehicleWheelData`) are created.
  - Each entity references its row-level `SourceReference`.
  - Raw strings are preserved in `raw_value` alongside parsed numeric/date values.
- For ambiguous tables (unknown column names, missing essential fields, non-standard layouts):
  - The system **does not guess**.
  - Ambiguous rows or tables are flagged with `status: "Needs Review"`.
  - Details are appended to `review_items` with page number, row number, and reason.

---

## Excel Ingestion Pipeline

### 1. Supported File Formats
- **`.xlsx`**: Supported natively via `openpyxl`.
- **`.xlsm`**: Supported safely via read-only mode (`openpyxl.load_workbook(data_only=True, read_only=True)`). VBA macros are never executed.

### 2. SHA-256 Hashing & Duplicate Protection
- Calculates SHA-256 over raw workbook bytes.
- Halts immediately if `content_hash` already exists in `document_versions`.

### 3. Concept Mapping & Provenance
- Columns classified into Attendance, Assignment, or Vehicle.
- Row-level `SourceReference` records `sheet_name`, `row_number`, and `source_text` (JSON row dump).
- Unrecognized or ambiguous sheets are flagged as "Needs Review".

---

## Ingestion Report Structure

Both Excel and PDF ingestion return structured JSON reports:

### PDF Ingestion Response (`HTTP 200 OK`)
```json
{
  "document_id": "c76afe22-a4fe-4d58-a766-2b007a60e891",
  "version_id": "1b3a7aba-b32b-4225-b3e4-fbb9231eb9c0",
  "filename": "table_attendance.pdf",
  "content_hash": "735ecebca4cf4715dfc366ff57fcce11fa08da352277dca7140e6c51e06e7ee6",
  "page_count": 1,
  "pages_processed": 1,
  "tables_detected": 1,
  "structured_records_created": 3,
  "records_needing_review": 0,
  "review_items": [],
  "errors": [],
  "duplicate_status": "new"
}
```

### PDF Duplicate File Response (`HTTP 200 OK`)
```json
{
  "document_id": "c76afe22-a4fe-4d58-a766-2b007a60e891",
  "version_id": "1b3a7aba-b32b-4225-b3e4-fbb9231eb9c0",
  "filename": "table_attendance.pdf",
  "content_hash": "735ecebca4cf4715dfc366ff57fcce11fa08da352277dca7140e6c51e06e7ee6",
  "page_count": 0,
  "pages_processed": 0,
  "tables_detected": 0,
  "structured_records_created": 0,
  "records_needing_review": 0,
  "review_items": [],
  "errors": [],
  "duplicate_status": "duplicate"
}
```

---

## Test Fixtures & Automated Tests

All test fixtures are strictly synthetic and located in `backend/tests/fixtures/`:

| Fixture Name | Type | Description |
|---|---|---|
| `simple_text.pdf` | PDF | Single-page notice testing text extraction to `SourceReference`. |
| `multi_page_text.pdf` | PDF | 3-page document testing multi-page iteration and provenance. |
| `table_attendance.pdf` | PDF | Tabular PDF with attendance data testing table detection & bbox. |
| `ambiguous_table.pdf` | PDF | Tabular PDF with unknown columns testing "Needs Review". |
| `empty_minimal.pdf` | PDF | Minimal blank PDF testing edge cases and zero tables. |
| `valid_attendance.xlsx` | Excel | Standard attendance schedule. |
| `valid_assignment.xlsx` | Excel | Duty assignment schedule. |
| `multi_sheet_office.xlsx` | Excel | Multi-sheet workbook with Attendance and Vehicles. |
| `ambiguous_columns.xlsx` | Excel | Unrecognized columns testing "Needs Review". |
| `empty_sheet.xlsx` | Excel | Blank workbook testing zero rows. |
| `unsupported_sample.txt` | Text | Unsupported extension testing HTTP 400 rejection. |

### Running the Full Test Suite
```bash
cd backend
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```
Total tests: **28 / 28 passing** (`test_models.py`, `test_excel_ingestion.py`, `test_pdf_ingestion.py`).
