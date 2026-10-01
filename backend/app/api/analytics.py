"""
API Router for Multi-Document Analytics & Comparison.
Phase 3.0 — RSSB Office Data Platform.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import AuthenticatedUserContext, require_permission
from app.database import get_db
from app.schemas.analytics import (
    AnalyticsDimensionsResponse,
    ComparisonRequest,
    ComparisonResultResponse,
    MultiDocSummaryRequest,
    MultiDocSummaryResponse,
)
from app.schemas.trends import (
    ExecutiveDashboardResponse,
    OperationalAnomaly,
    TrendAnalysisResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.trend_service import TrendService

router = APIRouter(prefix="", tags=["Analytics & Comparison"])


@router.post(
    "/compare",
    response_model=ComparisonResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare Metrics Across Locations or Time Periods",
    description="Calculates deterministic side-by-side comparisons, absolute deltas, percentage changes, and multi-document provenance.",
)
def compare_analytics(
    payload: ComparisonRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
) -> ComparisonResultResponse:
    """Execute location-to-location or period-to-period comparative analytics."""
    service = AnalyticsService(db=db)
    try:
        return service.compare(payload)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Comparative analysis failed: {exc}",
        )


@router.post(
    "/multi-document-summary",
    response_model=MultiDocSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Multi-Document Aggregation Summary",
    description="Aggregates metrics and records across multiple documents and date ranges.",
)
def get_multi_document_summary(
    payload: MultiDocSummaryRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
) -> MultiDocSummaryResponse:
    """Aggregate records across multiple documents and return summary KPIs."""
    service = AnalyticsService(db=db)
    try:
        return service.get_multi_document_summary(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Multi-document summary failed: {exc}",
        )


@router.get(
    "/dimensions",
    response_model=AnalyticsDimensionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Analytics Dimensions and Available Options",
    description="Returns available comparison dimensions, metric domains, known centers, and months for UI selectors.",
)
def get_dimensions(
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
) -> AnalyticsDimensionsResponse:
    """Retrieve metadata for comparison dimensions and selector options."""
    service = AnalyticsService(db=db)
    return service.get_dimensions()


# =============================================================================
# Phase 3.2 — Visual Analytics, Trends & Executive Dashboard
# =============================================================================

@router.get(
    "/trends",
    response_model=TrendAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute Longitudinal Trend Trajectories",
    description="Returns time-series data points, 3-period rolling moving averages, period-over-period variance, and narrative trajectory summary.",
)
def get_trends(
    center: Optional[str] = Query(None, description="Target Satsang Ghar name or null for global aggregate"),
    metric: str = Query("attendance", description="Metric domain: 'attendance', 'vehicle_wheel', 'assignment'"),
    start_date: Optional[date] = Query(None, description="Start date for analysis"),
    end_date: Optional[date] = Query(None, description="End date for analysis"),
    interval: str = Query("month", description="Aggregation interval: 'month' or 'day'"),
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
) -> TrendAnalysisResponse:
    """Retrieve time-series trend trajectory for attendance, vehicles, or assignments."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date cannot be after end_date.",
        )
    service = TrendService(db=db)
    try:
        return service.get_trends(
            center=center,
            metric=metric,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Trend calculation failed: {exc}",
        )


@router.get(
    "/dashboard",
    response_model=ExecutiveDashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Executive Operational Dashboard KPIs",
    description="Returns global operational metrics, center rankings, vehicle breakdown, sewa role distribution, and monthly trend trajectory.",
)
def get_executive_dashboard(
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
) -> ExecutiveDashboardResponse:
    """Retrieve system-wide operational dashboard KPIs."""
    service = TrendService(db=db)
    try:
        return service.get_executive_dashboard()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dashboard aggregation failed: {exc}",
        )


@router.get(
    "/anomalies",
    response_model=List[OperationalAnomaly],
    status_code=status.HTTP_200_OK,
    summary="Detect Operational Anomalies and Conflicts",
    description="Identifies statistical attendance swings and cross-document scheduling overlaps.",
)
def get_operational_anomalies(
    threshold: float = Query(35.0, description="Percentage deviation threshold from center mean"),
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
) -> List[OperationalAnomaly]:
    """Retrieve detected operational anomalies and scheduling overlaps."""
    service = TrendService(db=db)
    try:
        return service.get_operational_anomalies(threshold_pct=threshold)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Anomaly detection failed: {exc}",
        )
