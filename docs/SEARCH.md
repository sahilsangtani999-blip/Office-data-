# Natural-Language Search Foundation (Phase 2.2)

## Overview

The Natural-Language Search Foundation provides a deterministic, secure, and auditable search engine over verified office data in the RSSB Office Data Platform.

### Key Principles

1. **Deterministic Foundation**: Built using rule-based parsing and parameterized relational database queries. No external AI APIs, API keys, or cloud LLM dependencies are used in this phase.
2. **Never Calculate from Language Models**: All numerical results (count, sum, average, min, max) are computed strictly from database records retrieved via PostgreSQL.
3. **No Guessing / Strict Ambiguity Handling**: If a query is ambiguous across time periods, locations, or people, the system returns a clarification request rather than making assumptions.
4. **End-to-End Provenance**: Every retrieved record and calculated answer is traceable back to its underlying `SourceReference` (document name, version, sheet, row, and page).
5. **Decoupled Architecture**: Query planning is decoupled from search execution via the `BaseQueryPlanner` interface, preparing for seamless integration with future AI query planners.

---

## Architecture

```
User Question
      │
      ▼
┌───────────────────────────────┐
│     BaseQueryPlanner          │
│  (DeterministicQueryPlanner)  │ ◄── Controlled Vocabulary & Aliases
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│         QueryPlan             │ ◄── Structured, Machine-Readable Plan
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│        SearchService          │ ◄── Permission Boundary (SearchContext)
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│         PostgreSQL            │ ◄── Parameterized ORM Queries (SQLAlchemy)
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│        SearchResult           │ ◄── Calculations, Provenance, & Answer
└───────────────────────────────┘
```

---

## Supported Search Intents

The platform supports 10 explicit search intents:

| Intent | Description | Example Query |
|---|---|---|
| **Find** | Locate specific entities or duty assignments | *"Find assignment at Sukhliya on 2026-09-06"* |
| **List** | Enumerate domain records for an entity or period | *"Show attendance for Sukhliya in September"* |
| **Count** | Count number of matching records or sessions | *"Count attendance records for Sukhliya"* |
| **Sum** | Sum recorded numerical quantities | *"What was the total attendance for Sukhliya in September?"* |
| **Average** | Calculate arithmetic mean from database records | *"What was the average attendance at Sukhliya in September?"* |
| **Filter** | Apply role, date, or location constraints | *"Filter assignments where role is SR"* |
| **Compare** | Compare metrics between two locations or periods | *"Compare attendance between Sukhliya and Bicholi"* |
| **Lookup** | Retrieve specialized items (e.g., VIDEO CD) | *"Lookup VIDEO CD"* |
| **Report** | Find metadata for registered office reports | *"Show monthly reports"* |
| **Source** | Explicitly request document provenance | *"What is the source for Sukhliya attendance?"* |

---

## Controlled Office Vocabulary & Aliases

The deterministic parser enforces controlled office vocabulary:

- **Roles & Aliases**:
  - `SK` ↔ `Satsang Karta`
  - `SR` ↔ `Satsang Reader`
  - `VIDEO CD` ↔ `Video CD`, `VCD`, `CD`
- **Location Concepts**:
  - `Satsang Ghar` (e.g., Sukhliya, Bicholi, Pithampur, Model Town, Karol Bagh, etc.)
  - `Major Center` (e.g., Indore)
- **Domain Record Types**:
  - `Attendance` (attendance counts, raw office figures)
  - `Assignment` (speaker duties, reader duties, video playback)
  - `Vehicle / Wheel` (2-wheeler, 4-wheeler counts)
  - `Report` (Monthly Report, SK Report, SR Report)
  - `Document` (Uploaded Excel workbooks, PDF rosters)

---

## Structured Query Plan

A user question is first parsed into a strongly typed `QueryPlan` (`app.schemas.search.QueryPlan`):

```json
{
  "raw_question": "What was the average attendance at Sukhliya in September?",
  "intent": "average",
  "record_type": "attendance",
  "numeric_operation": "average",
  "satsang_ghar": "Sukhliya",
  "person": null,
  "role": null,
  "date": null,
  "date_start": null,
  "date_end": null,
  "month": 9,
  "year": null,
  "vehicle_type": null,
  "requested_fields": [],
  "source_requirement": false,
  "comparison_target": null,
  "filters": {}
}
```

---

## Ambiguity Handling

The search engine never guesses. Ambiguity is resolved at two stages:

### 1. Planner-Level Ambiguity
- **Extreme Queries without Scope**:
  - Query: *"What was the highest attendance?"*
  - Result: `clarification_required = true`, Question: *"I found attendance data for multiple periods. Which period do you mean?"*
- **Vague Keywords**:
  - Single-word queries like *"attendance"* prompt the user to specify whether they wish to list, count, or calculate statistics for a given Satsang Ghar or date.

### 2. Database-Level Ambiguity
- **Multiple Matching Locations**:
  - If a user asks for *"Indore"* and the database contains both *"Indore East"* and *"Indore West"*, the system asks:
    *"I found multiple Satsang Ghars matching 'Indore': 'Indore East', 'Indore West'. Which one do you mean?"*
- **Multiple Matching People**:
  - If a user asks for *"Ram"* and the database contains *"Ram Kumar"*, *"Ram Kumar Verma"*, and *"Ram Kumar Sharma"*, the system asks for clarification.

---

## Numerical Calculations

Numerical answers are computed strictly from database records using standard Python arithmetic on verified integer values:

- **Count**: `len(records)`
- **Sum**: $\sum x_i$
- **Average**: $\frac{\sum x_i}{N}$ (rounded to 2 decimal places)
- **Minimum**: $\min(x_i)$
- **Maximum**: $\max(x_i)$

### Example:
For Sukhliya attendance records with values $[74, 83, 92, 101]$:
- Total sessions ($N$): $4$
- Sum: $74 + 83 + 92 + 101 = 350$
- Average: $\frac{350}{4} = 87.5$

The resulting `SearchCalculation` object contains the formula description, unit, and count of records involved.

---

## Source Provenance & Traceability

Every search result links directly to `SourceReference` records created during file ingestion.

Fields retained:
- `document_name`: Original filename (e.g., `search_test_data.xlsx`)
- `document_version`: Version number (e.g., `1`)
- `sheet_name`: Excel sheet title (e.g., `Sukhliya Attendance`)
- `page_number`: PDF page number (when imported from PDF)
- `row_number`: 1-based spreadsheet row
- `cell_or_range`: Specific coordinate or cell
- `source_text`: Preserved JSON representation of original raw row

---

## API Reference

### `POST /api/v1/query`

**Request Body**:
```json
{
  "question": "What was the average attendance at Sukhliya in September?"
}
```

**Response Body**:
```json
{
  "original_question": "What was the average attendance at Sukhliya in September?",
  "interpreted_query": {
    "intent": "average",
    "record_type": "attendance",
    "numeric_operation": "average",
    "satsang_ghar": "Sukhliya",
    "month": 9,
    "year": null
  },
  "status": "success",
  "answer": "The average attendance at Sukhliya in September was 87.5 across 4 recorded sessions.",
  "records": [
    {
      "id": "e7b0...",
      "date": "2026-09-06",
      "satsang_ghar": "Sukhliya",
      "attendance_count": 74,
      "raw_value": null,
      "source_reference": {
        "document_name": "search_test_data.xlsx",
        "document_version": 1,
        "sheet_name": "Sukhliya Attendance",
        "row_number": 2
      }
    }
  ],
  "total_records": 4,
  "calculation": {
    "operation": "average",
    "value": 87.5,
    "unit": "attendees",
    "records_counted": 4,
    "formula_description": "Sum of 350 across 4 sessions = 87.5"
  },
  "source_references": [
    {
      "document_id": "...",
      "document_name": "search_test_data.xlsx",
      "document_version": 1,
      "sheet_name": "Sukhliya Attendance",
      "row_number": 2
    }
  ],
  "clarification_required": false,
  "clarification_question": null,
  "warnings": []
}
```

---

## Frontend Integration

The search input in `frontend/app/page.tsx` connects to `POST /api/v1/query`:
- **States Handled**:
  - `Loading`: Responsive spinner and progress message.
  - `Successful Result`: Displays large stat hero (for numerical results), natural-language answer, supporting records count, and primary source.
  - `View Source`: Expandable drawer revealing document name, sheet, row, and raw row text.
  - `Supporting Records Table`: Expandable table showing each contributing record.
  - `Clarification Required`: Amber banner displaying the clarification question and guidance.
  - `No Results`: Friendly guidance with tips on valid parameters.
  - `Error`: Clear failure message.

---

## Current Limitations

1. Complex multi-clause grammatical queries (e.g. *"Show attendance for Sukhliya except on holidays unless Ram was speaking"*) require future semantic query planning.
2. Compound conjunction queries across 3+ unrelated tables in a single sentence are deferred to the AI Query Planner.
3. Spelling corrections are limited to case-insensitive partial substring matching rather than phonetic/edit-distance matching.

---

## Future AI Query Planner Integration

The `SearchService` expects a `QueryPlanResult` conforming to the `QueryPlan` schema.
In future phases, an AI Query Planner can implement the `BaseQueryPlanner` interface:

```python
class AIQueryPlanner(BaseQueryPlanner):
    def __init__(self, model_client):
        self.client = model_client

    def plan(self, question: str) -> QueryPlanResult:
        # 1. Call Gemini / Claude with structured output schema (QueryPlan)
        # 2. Return QueryPlanResult(plan=structured_plan)
        pass
```

Because `SearchService` operates exclusively on the verified `QueryPlan` and executes parameterized database queries, swapping or chaining planners introduces zero risk of SQL injection or AI calculation hallucinations.
