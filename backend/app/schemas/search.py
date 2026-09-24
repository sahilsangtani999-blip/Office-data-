"""
Pydantic schemas for Natural-Language Search & Query Planning.
Phase 2.2 — RSSB Office Data Platform.
"""

from datetime import date as dt_date
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


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


class QueryPlan(BaseModel):
    """
    Structured query plan produced by a QueryPlanner.
    Decoupled from execution; can be generated deterministically or by a future AI planner.
    """
    raw_question: str
    intent: SearchIntent = "find"
    record_type: Optional[RecordType] = None
    numeric_operation: Optional[NumericOperation] = None
    satsang_ghar: Optional[str] = None
    person: Optional[str] = None
    role: Optional[str] = None
    date: Optional[dt_date] = None
    date_start: Optional[dt_date] = None
    date_end: Optional[dt_date] = None
    month: Optional[int] = Field(None, ge=1, le=12)
    year: Optional[int] = None
    vehicle_type: Optional[str] = None
    requested_fields: List[str] = Field(default_factory=list)
    source_requirement: bool = False
    comparison_target: Optional[Dict[str, Any]] = None
    filters: Dict[str, Any] = Field(default_factory=dict)


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
