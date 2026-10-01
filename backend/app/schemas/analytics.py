"""
Pydantic schemas for Multi-Document Analytics & Comparison.
Phase 3.0 — RSSB Office Data Platform.
"""

from datetime import date
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search import SourceReferenceInfo

ComparisonDimension = Literal["location", "period"]
ComparisonMetric = Literal["attendance", "vehicle_wheel", "assignment"]


class ComparisonRequest(BaseModel):
    """Request payload for comparative analytics."""
    model_config = ConfigDict(extra="forbid")

    dimension: ComparisonDimension = Field(
        ...,
        description="Dimension to compare: 'location' (between centers) or 'period' (between date spans)",
    )
    metric: ComparisonMetric = Field(
        default="attendance",
        description="Metric domain: 'attendance', 'vehicle_wheel', or 'assignment'",
    )
    sub_metric: Optional[str] = Field(
        default=None,
        description="Optional filter, e.g. 'average'/'total' for attendance, '2_wheeler'/'4_wheeler' for vehicles, or role code 'SK'/'SR' for assignments",
    )

    # Location comparison parameters (Dimension: 'location')
    entity_a: Optional[str] = Field(
        default=None,
        description="Name of first Satsang Ghar for location comparison",
    )
    entity_b: Optional[str] = Field(
        default=None,
        description="Name of second Satsang Ghar for location comparison",
    )
    shared_period_start: Optional[date] = Field(
        default=None,
        description="Start date for shared operational period in location comparison",
    )
    shared_period_end: Optional[date] = Field(
        default=None,
        description="End date for shared operational period in location comparison",
    )

    # Period comparison parameters (Dimension: 'period')
    satsang_ghar: Optional[str] = Field(
        default=None,
        description="Target Satsang Ghar for period comparison (or null for all centers)",
    )
    period_a_start: Optional[date] = Field(
        default=None,
        description="Start date of first period (Period A / Baseline)",
    )
    period_a_end: Optional[date] = Field(
        default=None,
        description="End date of first period (Period A / Baseline)",
    )
    period_b_start: Optional[date] = Field(
        default=None,
        description="Start date of second period (Period B / Comparison)",
    )
    period_b_end: Optional[date] = Field(
        default=None,
        description="End date of second period (Period B / Comparison)",
    )


class EntityMetricSummary(BaseModel):
    """Calculated summary for one side of a comparison."""
    label: str = Field(..., description="Human-readable label for entity/period")
    primary_value: float = Field(..., description="Primary aggregated metric (e.g. average or total)")
    secondary_value: Optional[float] = Field(default=None, description="Secondary metric (e.g. total attendance when primary is avg)")
    record_count: int = Field(..., description="Number of supporting verified records")
    document_count: int = Field(..., description="Number of distinct source documents")
    document_names: List[str] = Field(default_factory=list, description="Original filenames of contributing documents")
    breakdown_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed record breakdown items (e.g. daily figures or role counts)",
    )


class ComparisonResultResponse(BaseModel):
    """Comprehensive structured comparison result."""
    metric: str = Field(..., description="Metric domain analyzed")
    dimension: str = Field(..., description="'location' or 'period'")
    unit: str = Field(..., description="Unit of measurement (e.g. 'attendees/session', 'vehicles', 'assignments')")
    entity_a: EntityMetricSummary
    entity_b: EntityMetricSummary
    delta: float = Field(..., description="Absolute change (Entity B - Entity A)")
    percentage_change: Optional[float] = Field(
        default=None,
        description="Percentage change: ((B - A) / A) * 100. None if baseline A is 0.",
    )
    summary_sentence: str = Field(..., description="Clear human-readable summary of the comparison")
    breakdown_text: str = Field(..., description="Formula and calculation breakdown")
    source_references: List[SourceReferenceInfo] = Field(
        default_factory=list,
        description="Traceable source references across all contributing documents",
    )
    warnings: List[str] = Field(default_factory=list, description="Audit or data warnings")


class MultiDocSummaryRequest(BaseModel):
    """Request payload for multi-document aggregation summary."""
    model_config = ConfigDict(extra="forbid")

    date_start: Optional[date] = None
    date_end: Optional[date] = None
    document_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional list of document UUIDs to aggregate across",
    )


class MultiDocSummaryResponse(BaseModel):
    """High-level summary across multiple uploaded documents."""
    total_documents: int
    total_attendance: int
    average_attendance: float
    total_assignments: int
    total_vehicles: int
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    per_document_breakdown: List[Dict[str, Any]] = Field(default_factory=list)


class AnalyticsDimensionsResponse(BaseModel):
    """Available dimensions and metadata for frontend selectors."""
    dimensions: List[Dict[str, str]]
    metrics: List[Dict[str, str]]
    known_satsang_ghars: List[str]
    available_months: List[Dict[str, Any]]
