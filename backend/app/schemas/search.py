"""
Pydantic schemas for Natural-Language Search & Query Planning.
Phase 2.2 — RSSB Office Data Platform.
"""

from datetime import date as dt_date
from typing import Any, Dict, List, Literal, Optional, Union
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Supported search intents
SearchIntent = Literal[
    "find",
    "list",
    "count",
    "sum",
    "average",
    "filter",
    "compare",
    "lookup",
    "report",
    "source",
    "trend",
    "dashboard",
]

# Supported numeric operations
NumericOperation = Literal[
    "count",
    "sum",
    "average",
    "min",
    "max",
]

# Supported record types
RecordType = Literal[
    "attendance",
    "assignment",
    "vehicle_wheel",
    "report",
    "document",
    "person",
    "satsang_ghar",
    "role",
    "video_cd",
]


class QueryRequest(BaseModel):
    """Incoming query request payload."""
    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language query asked by the user.",
        examples=["What was the average attendance at Sukhliya in September?"],
    )
    section_id: Optional[str] = Field(
        None,
        description="Optional active section / data source ID to scope the search to.",
    )


# SQL rejection pattern for security against code injection in QueryPlan
_SQL_INJECTION_PATTERN = re.compile(
    r"\b(SELECT|DROP|INSERT|UPDATE|DELETE|ALTER|TRUNCATE|EXEC|EXECUTE|UNION|CREATE|GRANT|REVOKE)\b|[;]|--|/\*",
    re.IGNORECASE,
)


class QueryPlan(BaseModel):
    """
    Structured, strictly validated query plan produced by a QueryPlanner.
    Decoupled from execution; can be generated deterministically or by an optional AI planner.
    Strictly forbids arbitrary SQL, executable code, and unknown extra fields.
    """
    model_config = ConfigDict(extra="forbid")

    raw_question: str
    intent: SearchIntent = "find"
    record_type: Optional[RecordType] = None
    numeric_operation: Optional[NumericOperation] = None
    calculation: Optional[str] = None
    satsang_ghar: Optional[str] = None
    person: Optional[str] = None
    role: Optional[str] = None
    date: Optional[dt_date] = None
    date_start: Optional[dt_date] = None
    date_end: Optional[dt_date] = None
    date_range: Optional[List[dt_date]] = None
    month: Optional[int] = Field(None, ge=1, le=12)
    year: Optional[int] = None
    vehicle_type: Optional[str] = None
    requested_fields: List[str] = Field(default_factory=list)
    source_requirement: bool = False
    source_required: bool = False
    comparison_target: Optional[Dict[str, Any]] = None
    filters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("satsang_ghar", "person", "role", "vehicle_type", mode="before")
    @classmethod
    def validate_safe_text(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and isinstance(v, str):
            if _SQL_INJECTION_PATTERN.search(v):
                raise ValueError(
                    f"SQL keywords or executable code are strictly forbidden in QueryPlan entities: '{v}'"
                )
        return v

    @model_validator(mode="after")
    def sync_aliases(self) -> "QueryPlan":
        # Sync source_required and source_requirement
        if self.source_required and not self.source_requirement:
            self.source_requirement = True
        elif self.source_requirement and not self.source_required:
            self.source_required = True

        # Sync calculation and numeric_operation
        if self.calculation and not self.numeric_operation:
            calc_lower = self.calculation.lower().strip()
            if calc_lower in ("count", "sum", "average", "min", "max"):
                self.numeric_operation = calc_lower  # type: ignore[assignment]
        elif self.numeric_operation and not self.calculation:
            self.calculation = str(self.numeric_operation)

        # Sync date_range and date_start/date_end
        if self.date_range and len(self.date_range) == 2:
            if not self.date_start:
                self.date_start = self.date_range[0]
            if not self.date_end:
                self.date_end = self.date_range[1]
        elif self.date_start and self.date_end and not self.date_range:
            self.date_range = [self.date_start, self.date_end]

        return self


class QueryPlanResult(BaseModel):
    """Result of parsing and planning a query."""
    plan: Optional[QueryPlan] = None
    is_ambiguous: bool = False
    clarification_question: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class SearchCalculation(BaseModel):
    """Traceable numerical calculation performed on database records."""
    operation: str
    value: Optional[Union[float, int]] = None
    unit: Optional[str] = None
    records_counted: int = 0
    formula_description: Optional[str] = None
    breakdown: Optional[str] = None


class SourceReferenceInfo(BaseModel):
    """Source provenance tracking back to physical imported document."""
    id: Optional[str] = None
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    document_version: Optional[int] = None
    document_type: Optional[str] = None
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    cell_or_range: Optional[str] = None
    bbox: Optional[List[float]] = None
    source_text: Optional[str] = None


class SearchResult(BaseModel):
    """
    Standard machine-readable search result model.
    Contains both human answer and complete supporting records/provenance.
    """
    original_question: str
    interpreted_query: Dict[str, Any]
    status: Literal["success", "no_results", "clarification_required", "needs_review", "error"]
    answer: str
    records: List[Dict[str, Any]] = Field(default_factory=list)
    total_records: int = 0
    calculation: Optional[SearchCalculation] = None
    source_references: List[SourceReferenceInfo] = Field(default_factory=list)
    clarification_required: bool = False
    clarification_question: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    section_id: Optional[str] = None
    section_name: Optional[str] = None


class SourceDetailResponse(BaseModel):
    """Detailed metadata for a single SourceReference record."""
    id: str
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    document_version: Optional[int] = None
    document_type: Optional[str] = None
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    cell_or_range: Optional[str] = None
    bbox: Optional[List[float]] = None
    source_text: Optional[str] = None
    created_at: Optional[str] = None
    section_id: Optional[str] = None
    section_name: Optional[str] = None


class SourcePreviewResponse(BaseModel):
    """Rich, verified context preview for a source record."""
    id: Optional[str] = None
    source_id: str
    document_id: Optional[str] = None
    document_name: str
    document_version: Optional[int] = None
    document_type: str
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    cell_or_range: Optional[str] = None
    bbox: Optional[List[float]] = None
    parsed_content: Optional[Dict[str, Any]] = None
    raw_content: Optional[str] = None
    surrounding_rows: Optional[List[Dict[str, Any]]] = None
    page_text_excerpt: Optional[str] = None
    relevance_explanation: str
    associated_records: List[Dict[str, Any]] = Field(default_factory=list)
    section_id: Optional[str] = None
    section_name: Optional[str] = None


# =============================================================================
# Section / DataSource Models for Search Isolation
# =============================================================================

class SectionDocumentInfo(BaseModel):
    """Document attached to a section."""
    id: str
    filename: str
    document_type: Optional[str] = None
    created_at: Optional[str] = None


class SectionInfo(BaseModel):
    """Structured representation of an upload session / section."""
    id: str
    name: str
    source_type: str = "upload_section"
    status: str = "active"  # "active" or "historical"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    documents: List[SectionDocumentInfo] = Field(default_factory=list)
    records_count: int = 0


class SectionListResponse(BaseModel):
    """List of all sections with active section identified."""
    sections: List[SectionInfo] = Field(default_factory=list)
    active_section: Optional[SectionInfo] = None


class CreateSectionRequest(BaseModel):
    """Request payload to explicitly create a new section."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the new section (e.g., 'October 2026 Attendance')",
    )
