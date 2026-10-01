"""
Pydantic schemas for Visual Analytics, Trends & Executive Dashboard.
Phase 3.2 — RSSB Office Data Platform.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class TrendDataPoint(BaseModel):
    """A single time-series observation in a trend trajectory."""
    period_label: str = Field(..., description="Human-readable period label (e.g. 'September 2026' or '2026-09-06')")
    date_key: Optional[str] = Field(default=None, description="ISO date key (YYYY-MM-DD or YYYY-MM)")
    value: float = Field(..., description="Observed primary metric value")
    moving_average: Optional[float] = Field(default=None, description="3-period simple moving average")
    percentage_change: Optional[float] = Field(default=None, description="Period-over-period percentage variance")
    record_count: int = Field(default=1, description="Number of supporting records")


class TrendAnalysisResponse(BaseModel):
    """Full trend trajectory analysis across time."""
    metric: str = Field(..., description="Metric analyzed: 'attendance', 'vehicle_wheel', 'assignment'")
    target_entity: Optional[str] = Field(default=None, description="Satsang Ghar name or 'All Satsang Ghars'")
    interval: str = Field(default="month", description="'month' or 'day'")
    data_points: List[TrendDataPoint] = Field(default_factory=list)
    overall_direction: Literal["growth", "decline", "stable", "neutral"] = Field(
        default="neutral", description="Overall trajectory vector"
    )
    growth_rate_overall: Optional[float] = Field(
        default=None, description="Total net growth from earliest to latest period"
    )
    peak_period: Optional[str] = Field(default=None, description="Period with maximum value")
    peak_value: Optional[float] = Field(default=None, description="Maximum observed value")
    lowest_period: Optional[str] = Field(default=None, description="Period with minimum value")
    lowest_value: Optional[float] = Field(default=None, description="Minimum observed value")
    summary_text: str = Field(..., description="Executive narrative summarizing the trajectory")


class DashboardKPIs(BaseModel):
    """System-wide operational key performance indicators."""
    total_attendance: int
    average_session_attendance: float
    total_meetings: int
    active_centers_count: int
    total_duty_assignments: int
    unique_sevadars: int
    total_vehicles_recorded: int


class CenterRanking(BaseModel):
    """Performance summary for a Satsang Ghar location."""
    satsang_ghar: str
    total_attendance: int
    average_attendance: float
    sessions: int


class ExecutiveDashboardResponse(BaseModel):
    """Executive operational dashboard aggregation."""
    summary_kpis: DashboardKPIs
    center_rankings: List[CenterRanking] = Field(default_factory=list)
    vehicle_breakdown: Dict[str, int] = Field(default_factory=dict)
    role_breakdown: Dict[str, int] = Field(default_factory=dict)
    monthly_trend: List[TrendDataPoint] = Field(default_factory=list)


class OperationalAnomaly(BaseModel):
    """Statistical anomaly or cross-document operational conflict."""
    anomaly_type: Literal["attendance_spike", "attendance_drop", "schedule_conflict", "vehicle_load_imbalance"]
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    title: str
    description: str
    date: Optional[str] = None
    entity: Optional[str] = None
    metric_value: Optional[float] = None
    baseline_value: Optional[float] = None
    source_reference: Optional[Dict[str, Any]] = None
