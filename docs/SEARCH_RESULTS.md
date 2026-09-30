# Phase 2.3 — Search Results & Source Verification

## 1. Overview & Objectives

Phase 2.3 enhances the search foundation of the **RSSB Office Data Platform** by making query answers **understandable, verifiable, and traceable**. Rather than delivering opaque numbers or raw database rows, every search result presents:

1. **Question and Answer**: A clear, natural-language explanation grounded in data.
2. **Calculation Breakdown**: Full arithmetic visibility (e.g., `(74 + 83 + 92 + 101) / 4 = 87.5`) whenever aggregations are performed.
3. **Curated Supporting Records**: Clean, human-readable records without leaking raw database models or internal schemas.
4. **End-to-End Provenance**: Granular source references tracing back to original Excel files (workbook, sheet, row, cell/range) and PDF documents (file, page, bounding box coordinates).
5. **Interactive Source Preview**: An intuitive, non-technical verification viewer allowing office staff to inspect original rows and surrounding workbook context or PDF excerpts directly.
6. **Robust Result States**: Explicit, nontechnical handling for **Success**, **No results**, **Clarification required**, **Needs Review**, and **Error**.

---

## 2. Search Result Structure

The search endpoint (`POST /api/v1/query`) returns a strictly typed `SearchResult` payload:

```json
{
  "original_question": "What was the average attendance at Sukhliya in September?",
  "interpreted_query": {
    "intent": "average",
    "numeric_operation": "average",
    "record_type": "attendance",
    "satsang_ghar": "Sukhliya",
    "month": 9
  },
  "status": "success",
  "answer": "The average attendance at Sukhliya in September was 87.5 across 4 recorded sessions.",
  "total_records": 4,
  "calculation": {
    "operation": "average",
    "value": 87.5,
    "unit": null,
    "records_counted": 4,
    "formula_description": "Calculated average across 4 records.",
    "breakdown": "(74 + 83 + 92 + 101) / 4 = 87.5"
  },
  "records": [
    {
      "id": "c1f7a24e-...",
      "date": "2026-09-06",
      "satsang_ghar": "Sukhliya",
      "attendance_count": 74,
      "description": null,
      "status": "verified",
      "source_reference_id": "9d3e...",
      "source_reference": {
        "id": "9d3e...",
        "document_id": "1b0a...",
        "document_name": "search_test_data.xlsx",
        "document_version": 1,
        "document_type": "excel",
        "page_number": null,
        "sheet_name": "Sukhliya Attendance",
        "row_number": 2,
        "cell_or_range": null,
        "bbox": null,
        "source_text": "{\"Date\": \"2026-09-06\", \"Satsang Ghar\": \"Sukhliya\", \"Attendance\": 74}"
      }
    }
  ],
  "source_references": [
    {
      "id": "9d3e...",
      "document_id": "1b0a...",
      "document_name": "search_test_data.xlsx",
      "document_version": 1,
      "document_type": "excel",
      "page_number": null,
      "sheet_name": "Sukhliya Attendance",
      "row_number": 2,
      "cell_or_range": null,
      "bbox": null,
      "source_text": "{\"Date\": \"2026-09-06\", ...}"
    }
  ],
  "clarification_required": false,
  "clarification_question": null,
  "warnings": []
}
```

---

## 3. Result States

Every query resolves into one of five well-defined states:

| Status | Trigger Condition | User Experience & UI Representation |
| :--- | :--- | :--- |
| **`success`** | Query planned, executed, and all supporting records are verified. | Displays green `Verified Result` badge, hero metric (if numerical), natural-language answer, supporting records table, and "View Source" actions. |
| **`needs_review`** | Query succeeded, but one or more contributing records have `status == "needs_review"` (e.g. OCR ambiguity, missing secondary columns, unapproved revisions). | Displays amber `Needs Review` badge with an explicit warning banner: *"Some or all matching records are flagged as Needs Review by office verification."* Records remain accessible for inspection. |
| **`no_results`** | Query refers to an unknown Satsang Ghar, person, date, or period with zero matching data. | Displays neutral `No Results` badge with a clear, nontechnical message explaining what was missing (e.g. *"No attendance records found for Sukhliya in 2020"*). Suggests checking spelling or dates. |
| **`clarification_required`** | Query is semantically ambiguous (e.g., partial name matching multiple people or Satsang Ghars, or ambiguous period like "highest attendance" without a timeframe). | Displays warm `Clarification Needed` banner prompting the user with a specific question (e.g., *"I found attendance data for multiple periods. Which period do you mean?"*). |
| **`error`** | Malformed request or unexpected database error. | Displays red `Error` badge with a friendly notification: *"An error occurred while retrieving search results."* Internal tracebacks are safely withheld. |

---

## 4. Supporting Records Visibility

When users expand **"View Supporting Records"**, the UI renders only relevant domain fields:

- **Date**: Formatted as `YYYY-MM-DD` or localized date.
- **Satsang Ghar**: Name of the verified center (e.g., *Sukhliya*, *Model Town*).
- **Value / Count**: Numerical metric (attendance headcount or vehicle count).
- **Person & Role**: Full person name and formal role code (e.g., *Ram Kumar Verma (SK)*).
- **Status**: Visual indicator (`Verified` or `Needs Review`).
- **Source Action**: Direct **"View Source"** button linked to that record's `source_reference_id`.

No raw database IDs, SQLAlchemy internal objects, or backend schema internals are exposed.

---

## 5. Provenance & Verification

The platform maintains immutable links between extracted data and source files:

### Excel Provenance
- **Document Name**: e.g., `search_test_data.xlsx`
- **Document Version**: Version sequence number (e.g., `v1`)
- **Document Type**: `excel`
- **Sheet Name**: Exact tab in workbook (e.g., `Sukhliya Attendance`)
- **Row Number**: 1-based physical row in spreadsheet (e.g., `Row 2`)
- **Cell/Range**: Cell range where available (e.g., `A2:C2`)
- **No Invented Provenance**: Fields that do not exist in the source are kept `null`.

### PDF Provenance
- **Document Name**: e.g., `table_attendance.pdf`
- **Document Version**: Version sequence number (e.g., `v1`)
- **Document Type**: `pdf`
- **Page Number**: 1-based page index (e.g., `Page 1`)
- **Bounding Box (`bbox`)**: Exact physical region coordinates `[x0, y0, x1, y1]` (e.g., `[50.0, 80.0, 550.0, 180.0]`)
- **Source Text**: Verbatim text excerpt extracted from table or paragraph region.

---

## 6. Source APIs & Security

### Endpoints

1. **`GET /api/v1/sources/{source_id}`**
   - Retrieves safe metadata for a specific `SourceReference`.
   - Returns document name, document type, sheet/page, row, bbox, and raw source text snippet.

2. **`GET /api/v1/sources/{source_id}/preview`**
   - Retrieves verified contextual preview data:
     - `relevance_explanation`: Explains why this source is relevant (e.g., *"This source record directly provided the following domain entity in the office platform: Attendance count 74 for Sukhliya on 2026-09-06."*).
     - `surrounding_rows` (Excel): Returns adjacent rows (target row - 2 to target row + 2) with the target row flagged.
     - `page_text_excerpt` (PDF): Returns page-level text context.
     - `bbox` (PDF): Bounding box coordinates for region highlighting.
     - `associated_records`: List of platform entities linked to this source.

### Security Guarantees
- **No Arbitrary Filesystem Access**: Clients cannot pass filenames or paths to the API. Lookups are restricted to valid UUIDs checked against the `source_references` table.
- **UUID Validation**: Malformed identifiers or path traversal attempts (e.g. `../../etc/passwd`) are rejected with `404 Not Found` or `422 Unprocessable Entity`.
- **Read-Only**: Previews read from stored data and original files in read-only mode (`openpyxl.load_workbook(..., read_only=True)`), preventing any file modification.

---

## 7. Frontend Source Preview Experience

Clicking **"View Source"** from either the main result card or any supporting record row opens the **Source Verification Preview Modal**:

- **Header**: Clean title with file name and a **"Back to Results"** button.
- **Why It Is Relevant**: Highlighted callout explaining exactly which attendance session or assignment was extracted from this location.
- **Metadata Summary**: High-level badge grid (Document Type, Sheet/Page, Row, Coordinates).
- **Excel View**: Renders the spreadsheet context with surrounding rows, distinctly highlighting the **[TARGET]** row in gold.
- **PDF View**: Displays the physical page number, coordinates callout (`x0: 50.0, y0: 80.0, x1: 550.0, y1: 180.0`), and verbatim extracted page text.
- **Back to Results**: Returns the user seamlessly to the search results without resetting query state.

---

## 8. Complete Search Flow

```
   Dashboard
       ↓
 Ask Question  (e.g., "What was the average attendance at Sukhliya in September?")
       ↓
  POST /query  (Deterministic Query Planner)
       ↓
    Answer     (87.5) + Calculation Breakdown: (74 + 83 + 92 + 101) / 4 = 87.5
       ↓
Supporting Records (4 verified attendance records)
       ↓
  View Source  (Click "View Source" on Row 2)
       ↓
Source Preview (GET /api/v1/sources/{source_id}/preview)
       ↓
Verify & Audit (Inspect surrounding rows, sheet name, or PDF bounding box)
       ↓
Back to Results
```

---

## 9. Known Limitations (Phase 2.3)

1. **Deterministic Query Planner**: Currently uses rule-based parsing with controlled vocabulary for Satsang Ghars, months, and roles. Natural language inquiries with complex phrasing or colloquialisms may trigger clarification states until AI query planning is introduced in Phase 3.
2. **Scanned Images**: PDFs without embedded text layers (pure scans) require an OCR pre-processing step before bounding boxes and text extracts can be verified.
3. **Multi-Workbook Joins**: Cross-file joins that span separate workbooks without common primary keys are evaluated sequentially rather than via relational joins.
