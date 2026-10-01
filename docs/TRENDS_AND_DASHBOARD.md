# Phase 3.2: Visual Analytics, Trend Trajectories & Operational Insights

## Overview
Phase 3.2 expands the Radha Soami Satsang Beas (RSSB) Office Data Platform by introducing visual time-series analytics, multi-period trend trajectories, an executive overview dashboard, and rule-based operational anomaly detection. 

All analytics respect the document review lifecycle (only approved/active documents are queried) and role-based access control (RBAC).

---

## Architecture & Components

### 1. Trend Calculation Engine (`backend/app/services/trend_service.py`)
- **Metric Aggregations**: Supports `attendance`, `sewadars`, and `satsangs`.
- **Interval Bucketing**: Aggregates records by `month`, `quarter`, or `year` using standard date parsing and ordering.
- **Moving Average Smoothing**: Computes a 3-period moving average ($N \le 3$) to identify underlying trajectory patterns amidst weekly/monthly volatility.
- **Center Trajectories**: Filters metrics across all centers or focuses specifically on individual Satsang Ghars (e.g. `Sukhliya`, `Khandwa`, `Rajendra Nagar`).
- **Growth & Direction Analysis**: Calculates overall percentage change ($\Delta\%$) between baseline and final periods, classifying trajectories as `growing`, `declining`, or `stable`.

### 2. Executive Dashboard KPIs & Leaderboards
- **High-Level Aggregate KPIs**:
  - `total_attendance`: Sum of verified attendance across all centres.
  - `total_sewadars`: Sum of sewadars deployed across all services.
  - `total_satsangs`: Total count of recorded spiritual discourses and gatherings.
  - `active_centers`: Count of active centres with approved data.
  - `growth_rate_pct`: Aggregate attendance growth comparing recent periods.
- **Center Leaderboards & Rankings**:
  - Centres ranked by aggregate attendance, average attendance per event, total sewadars, and total satsang counts.

### 3. Operational Anomaly Detection
- Scans consecutive periods for significant deviations exceeding a configurable threshold (default: $\pm 25\%$).
- Categorizes anomalies by severity:
  - **Critical**: Negative deviation $\le -40\%$ (sharp unexpected drops in attendance or sewadars).
  - **Warning**: Deviations between $25\%$ and $40\%$ (either steep drops or sudden unexpected surges).
- Provides actionable explanatory notes indicating baseline vs observed values.

### 4. Search & Query Planner Integration
- **Intent Detection**: The query planner classifies inquiries containing terms like `"trend"`, `"trajectory"`, `"growth"`, `"moving average"`, `"dashboard"`, or `"executive summary"` into `trend` or `dashboard` search intents.
- **Rich Visual Search Cards**: Returns structured trend series and KPI summaries directly within `SearchResultCard` on the main page.

---

## API Endpoints

| Method | Endpoint | Description | Guard |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/trends` | Time-series data points, moving averages, and trajectory metrics | `require_permission("read")` |
| `GET` | `/api/v1/analytics/dashboard` | Executive KPIs, attendance totals, and centre performance rankings | `require_permission("read")` |
| `GET` | `/api/v1/analytics/anomalies` | Automated operational anomaly detection with configurable threshold | `require_permission("read")` |

### Query Parameters for `/trends`:
- `center` (optional `string`): Filter by specific centre/ghar name.
- `metric` (optional `string`): `attendance` (default), `sewadars`, or `satsangs`.
- `interval` (optional `string`): `month` (default), `quarter`, or `year`.

### Query Parameters for `/anomalies`:
- `threshold_pct` (optional `float`, default `25.0`): Percentage swing required to trigger an anomaly.

---

## Frontend Components

- **`DashboardModal.tsx`**: High-performance interactive modal featuring:
  - **Executive Overview Tab**: Stat KPI cards, attendance leaderboards, and key metrics.
  - **Trend Trajectories Tab**: Interactive SVG line chart with real-time center, metric, and interval selectors, plus moving average curve toggle.
  - **Operational Anomalies Tab**: Severity-badged anomaly feed detailing percentage drops/surges with contextual descriptions.
- **`SearchResultCard.tsx`**: Renders embedded trend charts and dashboard summaries when queried through the natural language search bar.
- **Responsive Pure SVG**: Zero external charting dependencies to guarantee zero bundle bloat and seamless theme integration.
