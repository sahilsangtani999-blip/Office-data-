# AI Query Planner Architecture & Integration Guide
**Phase 2.4 — RSSB Office Data Platform**

> **IMPORTANT ARCHITECTURAL GUARANTEE:**  
> **The application does not require an external AI API to operate.**  
> The deterministic/local query planner (`LocalQueryPlanner`) remains the default and automatic fallback. The platform functions with complete fidelity in offline and air-gapped environments without any API keys or internet access.

---

## 1. Architectural Overview

The Query Planning layer converts natural language office inquiries into validated, structured specifications (`QueryPlan`) that the `SearchService` executes via parameterized PostgreSQL queries.

```
                              User Question
                                    │
                                    ▼
                         ┌───────────────────────┐
                         │   QueryPlanner ABC    │
                         └──────────┬────────────┘
                                    │
                  Is AI_PLANNER_ENABLED = true AND
                  AI provider available & valid?
                                   / \
                                  /   \
                             No  /     \  Yes
                                /       \
                               ▼         ▼
                     ┌─────────────┐   ┌───────────────────────────┐
                     │ Local Query │   │   OptionalAIQueryPlanner  │
                     │   Planner   │   └─────────────┬─────────────┘
                     └──────┬──────┘                 │
                            │             AI Provider Abstraction
                            │          (Only Question & Vocabulary)
                            │                        │
                            │                        ▼
                            │             ┌─────────────────────┐
                            │             │ Strict Pydantic     │
                            │             │ QueryPlan Validation│
                            │             └──────────┬──────────┘
                            │                        │
                            │            Validation failure /   
                            │            provider timeout /     
                            │            unsupported vocabulary 
                            │                        │
                            │◄───────────────────────┘ (Silent Fallback)
                            │
                            ▼
                     Structured & Validated
                          QueryPlan
                            │
                            ▼
                     ┌─────────────┐
                     │SearchService│ ──► PostgreSQL (Parameterized queries)
                     └──────┬──────┘
                            │
                            ▼
                     ┌─────────────┐
                     │ Calculation │ ──► Deterministic Math Engine
                     │   Engine    │     (e.g., (74+83+92+101)/4 = 87.5)
                     └─────────────┘
```

---

## 2. Query Planner Interface

All query planners implement the common abstract base class `QueryPlanner`:

```python
class QueryPlanner(ABC):
    @abstractmethod
    def plan(self, question: str) -> QueryPlanResult:
        """Parses a natural language question into a structured QueryPlanResult."""
        pass
```

The `SearchService` and API route depend solely on `QueryPlanner` via dependency injection, completely decoupling business logic from any concrete AI implementation:

```python
# In SearchService
def __init__(self, db: Session, planner: Optional[QueryPlanner] = None):
    self.db = db
    self.planner = planner or get_query_planner()
```

---

## 3. Local Planner (`LocalQueryPlanner`)

`LocalQueryPlanner` (alias for `DeterministicQueryPlanner`) is the system default. It requires zero network connectivity and zero external dependencies.

### Capabilities:
- Controlled vocabulary matching against official RSSB Satsang Ghars, Sewa roles (`SK`, `SR`, `VIDEO CD`), months, and report types.
- Rule-based intent classification (`find`, `list`, `count`, `sum`, `average`, `filter`, `compare`, `lookup`, `report`, `source`).
- Date parsing (ISO formats, single month/year filters, and full date ranges).
- Entity ambiguity detection (detects partial Satsang Ghar or Person matches and prompts for clarification).

### Example Inquiries:
- `"average attendance at Sukhliya in September"` &rarr; `intent='average'`, `record_type='attendance'`, `satsang_ghar='Sukhliya'`, `month=9`
- `"show attendance for Sukhliya"` &rarr; `intent='find'`, `record_type='attendance'`, `satsang_ghar='Sukhliya'`
- `"count attendance records"` &rarr; `intent='count'`, `record_type='attendance'`
- `"find assignment for Sukhliya"` &rarr; `intent='find'`, `record_type='assignment'`, `satsang_ghar='Sukhliya'`
- `"show SK assignments"` &rarr; `intent='find'`, `record_type='assignment'`, `role='SK'`

---

## 4. Optional AI Planner (`OptionalAIQueryPlanner`)

`OptionalAIQueryPlanner` wraps an AI provider adapter as an optional language-understanding enhancement.

### AI Provider Abstraction (`AIQueryPlannerProvider`):
```python
class AIQueryPlannerProvider(ABC):
    @abstractmethod
    def plan_query(
        self,
        question: str,
        vocabulary: Dict[str, Any],
        allowed_intents: List[str],
        plan_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Translates a user question into a candidate query plan dictionary."""
        pass
```

### Provided Adapters:
1. **`MockAIQueryPlannerProvider`**: Deterministic in-memory provider for testing without external networks or keys.
2. **`ExternalAIQueryPlannerProvider`**: HTTP-based adapter compatible with REST LLM endpoints.

---

## 5. QueryPlan Schema & Strict Validation

The `QueryPlan` schema enforces strict boundaries on AI output:

```python
class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Rejects unknown/injected fields

    raw_question: str
    intent: SearchIntent
    record_type: RecordType = "attendance"
    numeric_operation: Optional[NumericOperation] = None
    calculation: Optional[str] = None
    satsang_ghar: Optional[str] = None
    person: Optional[str] = None
    role: Optional[str] = None
    date: Optional[dt_date] = None
    date_start: Optional[dt_date] = None
    date_end: Optional[dt_date] = None
    date_range: Optional[List[dt_date]] = None
    month: Optional[int] = Field(default=None, ge=1, le=12)
    year: Optional[int] = Field(default=None, ge=2000, le=2099)
    vehicle_type: Optional[str] = None
    requested_fields: List[str] = Field(default_factory=list)
    source_required: bool = False
    source_requirement: bool = False
    comparison_target: Optional[Dict[str, Any]] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
```

### Security & Sanitization Protections:
- `extra="forbid"`: Prevents arbitrary code, prompt injection fields, or SQL clauses (`"raw_sql"`, `"query"`, `"code"`).
- `@field_validator`: Evaluates all text fields against `_SQL_INJECTION_PATTERN` (`SELECT`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `UNION`, `--`, `/*`, `;`). If any SQL keywords are detected, validation fails immediately, triggering fallback.
- **Vocabulary Verification**: If AI returns an unrecognized Satsang Ghar (e.g., `"Atlantis Main Hall"`), the planner refuses to guess and triggers ambiguity clarification.

---

## 6. Fallback Behavior & Error Handling

The application guarantees that the user **never sees raw AI errors**. Silent fallback to `LocalQueryPlanner` occurs under any of the following conditions:

| Scenario | Trigger | Behavior |
| :--- | :--- | :--- |
| **Disabled Mode** | `AI_PLANNER_ENABLED=false` | Local planner invoked directly. Provider never instantiated or called. |
| **Missing Key** | `AI_API_KEY=None` or empty | Automatic fallback to local planner. |
| **Provider Error** | Network timeout, 5xx status, quota | Logged as warning; transparent fallback to local planner. |
| **Malformed Output** | Non-dict response or broken JSON | Validation fails; falls back to local planner. |
| **Extra Fields** | Hallucinated parameters or injection | Pydantic `extra="forbid"` fails; falls back to local planner. |
| **SQL Injection** | SQL keywords in entity fields | Regex validation raises error; falls back to local planner. |
| **Unsupported Vocabulary**| Hallucinated location / entity | Returns `is_ambiguous=True` with a clarification request. Never executes unverified entities. |

---

## 7. Security Boundaries & Data Safety

The AI planning adapter operates under strict zero-trust data safety constraints:

1. **No Sensitive Office Data Leakage**:
   - The provider receives **only**:
     - User question string
     - Approved entity names (known Satsang Ghars, role aliases, months)
     - Allowed intents list
     - Pydantic JSON schema
   - The provider **never** receives:
     - Database connection strings or credentials
     - Database rows, records, or table dumps
     - File system paths or raw imported documents
     - Internal user lists or passwords

2. **No Arbitrary Code or SQL Execution**:
   - The AI planner outputs structured metadata only.
   - The application does not construct raw SQL from AI text. All queries remain strictly parameterized SQLAlchemy statements generated by `SearchService`.

---

## 8. Numerical Integrity

**The AI never calculates final answers.**

### Workflow Example:
1. User asks: *"What was the average attendance at Sukhliya in September?"*
2. AI Planner outputs:
   ```json
   {
     "intent": "average",
     "record_type": "attendance",
     "numeric_operation": "average",
     "satsang_ghar": "Sukhliya",
     "month": 9
   }
   ```
3. `SearchService` executes parameterized SQL against PostgreSQL:
   ```sql
   SELECT count_value FROM attendances WHERE satsang_ghar_id = :id AND EXTRACT(month FROM date) = 9;
   ```
4. PostgreSQL returns records: `[74, 83, 92, 101]`.
5. Backend calculation engine computes:
   - Sum: `350`
   - Count: `4`
   - Average: `350 / 4 = 87.5`
   - Breakdown: `"(74 + 83 + 92 + 101) / 4 = 87.5"`
6. User receives `87.5`, verified by database provenance and source documents.

---

## 9. Configuration

Default configuration in `backend/app/config.py` and `.env.example`:

```bash
# =============================================================================
# Phase 2.4 Optional AI Query Planner Configuration
# =============================================================================
# The application functions completely without AI.
# AI is disabled by default.
AI_PLANNER_ENABLED=false

# Provider type: "mock" (default for offline test), "gemini", "openai", "external"
AI_PROVIDER=mock

# External AI API Key (leave empty when running without AI)
# AI_API_KEY=

# Model name for external provider
AI_MODEL=gemini-1.5-flash

# Network timeout for external calls (seconds)
AI_TIMEOUT_SECONDS=5.0
```

---

## 10. Testing

Phase 2.4 introduces a dedicated test suite in `backend/tests/test_ai_query_planner.py` with 12 tests using `MockAIQueryPlannerProvider` for reproducible offline verification:

1. `test_1_local_planner`: Verifies deterministic parsing of average, list, count, assignment, and role queries.
2. `test_2_ai_planner_interface`: Verifies common `QueryPlanner` ABC adherence across local and AI planners.
3. `test_3_valid_ai_query_plan`: Verifies valid mock response passes strict Pydantic validation.
4. `test_4_invalid_ai_query_plan_triggers_fallback`: Tests rejection of extra fields and SQL injections with safe fallback.
5. `test_5_ai_disabled_mode`: Verifies provider is never touched when `AI_PLANNER_ENABLED=false`.
6. `test_6_missing_api_key_falls_back`: Verifies missing API key gracefully falls back.
7. `test_7_ai_provider_failure_falls_back`: Simulates provider timeout/exception with graceful fallback.
8. `test_8_ai_fallback_in_search_service`: End-to-end integration showing `SearchService` returns valid DB records on AI failure.
9. `test_9_unsupported_vocabulary_not_executed`: Tests refusal to guess hallucinated Satsang Ghars.
10. `test_10_ambiguous_question_returns_clarification`: Tests deterministic clarification handling.
11. `test_11_numerical_answer_still_calculated_by_database`: Proves 87.5 is computed from DB records (74, 83, 92, 101).
12. `test_12_data_safety_no_leakage`: Confirms no DB dumps, rows, or secrets are sent to the provider.

### Running Backend Tests:
```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```
Result: **93/93 tests passing** (12 Model, 18 Excel, 28 PDF, 7 Validation, 16 Search Foundation, 12 AI Query Planner).

---

## 11. Future Provider Integration

To integrate a new provider (e.g. Google Gemini, Ollama, Anthropic):
1. Subclass `AIQueryPlannerProvider`:
   ```python
   class GeminiAIQueryPlannerProvider(AIQueryPlannerProvider):
       def plan_query(self, question, vocabulary, allowed_intents, plan_schema):
           # Call Gemini API with structured JSON output mode enforcing plan_schema
           ...
   ```
2. Register the provider in `get_ai_provider()` in `backend/app/services/query_planner.py`.
3. Set `AI_PLANNER_ENABLED=true` and `AI_API_KEY=<key>` in the environment.
4. If the provider fails, the platform automatically falls back to `LocalQueryPlanner`.
