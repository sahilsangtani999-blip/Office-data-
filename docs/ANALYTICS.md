# Multi-Document Analytics & Comparison (Phase 3.0)

## Overview

The Multi-Document Analytics & Comparison module enables cross-document aggregation, multi-dimensional entity comparison, variance and percentage delta analysis, and cross-file provenance tracking for the RSSB Office Data Platform.

It allows office administrators, reviewers, and authorized users to compare operational metrics across centers (locations) or across time intervals (periods) using verified, validated data ingested from Excel schedules and PDF office records.

---

## Architectural Principles

1. **Document Lifecycle & Data Quality**:
   - Only validated records (`is_valid = True`) contribute to comparative computations.
   - Superseded or rejected documents are excluded from production comparisons to prevent skewed statistics.
2. **Deterministic Computations**:
   - All metrics (sums, averages, counts, deltas, percentages) are calculated strictly via SQL aggregations and Python arithmetic.
   - Variance percentage formula:
     $$\Delta\% = \frac{\text{Value}_B - \text{Value}_A}{\text{Value}_A} \times 100$$
   - Edge case handling: If baseline $\text{Value}_A = 0$, percentage delta is defined as `+100.0%` (if $\text{Value}_B > 0$), `0.0%` (if $\text{Value}_B = 0$), or `-100.0%` (if $\text{Value}_B < 0$).
3. **Role-Based Access Control (RBAC)**:
   - Comparing and summarizing documents requires the `read` permission.
   - Users with center-restricted scopes are constrained to their authorized centers.
4. **Source Attribution & Provenance**:
   - Every comparative response references the contributing documents (`document_id`, `filename`, `centre`, `date_range`, `record_count`), providing transparent auditability.

---

## Supported Comparison Scenarios

### 1. Location-to-Location Comparison
Compares metrics between two centers (e.g., *Delhi* vs. *Mumbai*, *Bangalore* vs. *Chennai*) across a common or unbounded timeframe.
- **Query Planner Pattern**: `"compare attendance between Delhi and Mumbai"`
- **Target Extraction**: Primary target `Delhi`, secondary target `Mumbai`, dimension `location`.

### 2. Period-to-Period Comparison
Compares metrics across two temporal intervals (e.g., *2024* vs. *2025*, *January 2025* vs. *February 2025*) across all centers or within a specific center.
- **Query Planner Pattern**: `"compare 2024 vs 2025 attendance"`
- **Target Extraction**: Primary target `2024`, secondary target `2025`, dimension `period`.

---

## Comparative Metrics Catalog

| Domain | Metric Key | Label | Formula / Aggregate |
| :--- | :--- | :--- | :--- |
| **Attendance** | `total_attendance` | Total Attendance | $\sum(\text{attendees})$ |
| | `average_attendance` | Average Attendance | $\text{Total} / \text{Sessions}$ |
| | `session_count` | Total Sessions | $\text{COUNT}(\text{attendance\_records})$ |
| | `peak_attendance` | Peak Attendance | $\text{MAX}(\text{attendees})$ |
| **Sewadars** | `total_duty_assignments` | Total Duty Assignments | $\text{COUNT}(\text{sewadar\_records})$ |
| | `unique_sewadars` | Unique Sewadars | $\text{COUNT}(\text{DISTINCT } \text{name})$ |
| | `departments_covered` | Departments Covered | $\text{COUNT}(\text{DISTINCT } \text{department})$ |
| **Transport** | `total_vehicles` | Total Vehicles | $\text{COUNT}(\text{vehicle\_records})$ |
| | `total_passenger_capacity` | Total Passenger Capacity | $\sum(\text{capacity})$ |

---

## API Endpoints Reference

### 1. Execute Comparison
- **Route**: `POST /api/v1/analytics/compare`
- **Permission**: `read` (`viewer`, `uploader`, `reviewer`, `admin`)
- **Request Body**:
```json
{
  "metric_domain": "all",
  "comparison_dimension": "location",
  "entity_a_id": "Delhi",
  "entity_b_id": "Mumbai",
  "date_range_a_start": "2024-01-01",
  "date_range_a_end": "2024-12-31",
  "date_range_b_start": "2024-01-01",
  "date_range_b_end": "2024-12-31",
  "center_filter": null
}
```
- **Response Structure**:
```json
{
  "comparison_dimension": "location",
  "metric_domain": "all",
  "entity_a": {
    "entity_id": "Delhi",
    "entity_label": "Delhi",
    "document_count": 4,
    "metrics": {
      "total_attendance": 12500,
      "average_attendance": 3125.0,
      "session_count": 4,
      "peak_attendance": 4200,
      "total_duty_assignments": 45,
      "unique_sewadars": 38,
      "departments_covered": 6,
      "total_vehicles": 18,
      "total_passenger_capacity": 720
    }
  },
  "entity_b": {
    "entity_id": "Mumbai",
    "entity_label": "Mumbai",
    "document_count": 3,
    "metrics": {
      "total_attendance": 8900,
      "average_attendance": 2966.7,
      "session_count": 3,
      "peak_attendance": 3400,
      "total_duty_assignments": 30,
      "unique_sewadars": 28,
      "departments_covered": 5,
      "total_vehicles": 12,
      "total_passenger_capacity": 480
    }
  },
  "deltas": {
    "total_attendance": {
      "entity_a_value": 12500,
      "entity_b_value": 8900,
      "absolute_delta": -3600,
      "percentage_delta": -28.8,
      "direction": "decrease"
    }
  },
  "summary_text": "Comparison between Delhi and Mumbai across 7 documents shows...",
  "contributing_documents": [
    {
      "document_id": "doc-uuid-1",
      "filename": "Delhi_Attendance_Q1.xlsx",
      "centre": "Delhi",
      "date_range": "2024-01-01 to 2024-03-31",
      "record_count": 52
    }
  ]
}
```

### 2. Multi-Document Summary
- **Route**: `POST /api/v1/analytics/multi-document-summary`
- **Permission**: `read`
- **Request Body**:
```json
{
  "document_ids": ["doc-uuid-1", "doc-uuid-2"],
  "center_filter": "Delhi"
}
```
- **Response Structure**:
```json
{
  "total_documents": 2,
  "centers_covered": ["Delhi"],
  "date_range_start": "2024-01-01",
  "date_range_end": "2024-06-30",
  "total_attendance": 6500,
  "total_sewadar_shifts": 40,
  "total_vehicles": 14,
  "summary_statement": "Aggregated summary of 2 documents covering Delhi..."
}
```

### 3. Available Analytics Dimensions
- **Route**: `GET /api/v1/analytics/dimensions`
- **Permission**: `read`
- **Response Structure**:
```json
{
  "centers": ["Bangalore", "Delhi", "Mumbai"],
  "periods": ["2023", "2024", "2025"],
  "metric_domains": ["all", "attendance", "sewadars", "vehicles"]
}
```

---

## Natural Language Search Integration

The Query Planner automatically classifies comparative intents:
1. When user inputs: `"compare attendance between Delhi and Mumbai"`:
   - `intent`: `compare`
   - `target`: `Delhi`
   - `comparison_target`: `Mumbai`
   - `domain`: `attendance`
   - `dimension`: `location`
2. Search Service delegates execution to `AnalyticsService.compare_entities`:
   - Returns a structured `compare` hero card with comparative stats for both entities.
   - Highlights variance percentage and absolute differences.
   - Renders a comparison table with side-by-side metrics and delta direction badges.
   - Displays contributing document provenance.

---

## Frontend Components

1. **`AnalyticsModal.tsx`**:
   - Dedicated full modal workspace for multi-document analytics.
   - Tab 1: **Entity Comparison** (Side-by-side entity selection, metric domains, interactive delta badges, comparison tables).
   - Tab 2: **Multi-Document Summary** (Filter by center, aggregate multi-file stats, provenance listing).
2. **`SearchResultCard.tsx`**:
   - Supports `operation: "compare"`.
   - Side-by-side entity stat cards with primary metrics.
   - Structured comparison table with delta and percentage tags.
3. **`page.tsx`**:
   - Multi-Doc Analytics & Comparison launcher button in action bar.
