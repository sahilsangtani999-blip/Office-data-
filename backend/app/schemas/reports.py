"""
Pydantic schemas for Reports Generation & Data Export.
Phase 3.1 — RSSB Office Data Platform.
"""

from datetime import date as dt_date, datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

ReportType = Literal[
    "monthly",
    "attendance_summary",
    "duty_summary",
    "vehicle_report",
]

ReportStatus = Literal[
    "draft",
    "final",
    "archived",
]


class ReportCreateRequest(BaseModel):
    """Payload for requesting the generation of an official office report."""
    name: Optional[str] = Field(
        None,
        description="Optional human-readable title. If omitted, generated automatically from type and period.",
        examples=["Monthly Report - October 2026"],
    )
    report_type: ReportType = Field(
        default="monthly",
        description="Type of report to generate.",
    )
    satsang_ghar: Optional[str] = Field(
        None,
        description="Optional filter scoping the report to a specific Satsang Ghar location.",
        examples=["Sukhliya"],
    )
    reporting_period_start: Optional[dt_date] = Field(
        None,
        description="Explicit start date for the report period (YYYY-MM-DD).",
    )
    reporting_period_end: Optional[dt_date] = Field(
        None,
        description="Explicit end date for the report period (YYYY-MM-DD).",
    )
    start_date: Optional[dt_date] = Field(
        None,
        description="Explicit start date for the report period (YYYY-MM-DD).",
    )
    end_date: Optional[dt_date] = Field(
        None,
        description="Explicit end date for the report period (YYYY-MM-DD).",
    )
    year: Optional[int] = Field(
        None,
        description="Calendar year (e.g. 2026). Used with month when exact dates are not supplied.",
        examples=[2026],
    )
    month: Optional[int] = Field(
        None,
        ge=1,
        le=12,
        description="Month number (1-12). Used with year when exact dates are not supplied.",
        examples=[10],
    )
    formats: Optional[List[str]] = Field(
        default_factory=lambda: ["xlsx", "csv"],
        description="Export formats to compile.",
    )


class ReportItemResponse(BaseModel):
    """Summary representation of a registered report."""
    id: str
    name: str
    report_type: str
    reporting_period_start: Optional[dt_date] = None
    reporting_period_end: Optional[dt_date] = None
    status: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    export_formats: List[str] = Field(default_factory=lambda: ["xlsx", "csv"])

    model_config = ConfigDict(from_attributes=True)


class ReportDetailResponse(BaseModel):
    """Detailed report representation with summary KPIs and data tables."""
    id: str
    name: str
    report_type: str
    reporting_period_start: Optional[dt_date] = None
    reporting_period_end: Optional[dt_date] = None
    status: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    summary_metrics: Dict[str, Any]
    summary_kpis: Optional[Dict[str, Any]] = None
    data: Dict[str, Any]
    export_files: Dict[str, str]

    model_config = ConfigDict(from_attributes=True)


class ReportListResponse(BaseModel):
    """Response containing a list of reports."""
    reports: List[ReportItemResponse]
    total: int
