"""
API Router for Multi-Document Analytics & Comparison.
Phase 3.0 — RSSB Office Data Platform.
"""

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.services.analytics_service import AnalyticsService

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
