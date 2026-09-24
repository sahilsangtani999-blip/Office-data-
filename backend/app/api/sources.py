"""
API Endpoints for Source Verification and Provenance Preview.
Phase 2.3 — RSSB Office Data Platform.

Provides:
- GET /api/v1/sources/{source_id}
- GET /api/v1/sources/{source_id}/preview
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.search import SourceDetailResponse, SourcePreviewResponse
from app.services.source_service import get_source_detail, get_source_preview

router = APIRouter(prefix="/api/v1/sources", tags=["Source Verification"])


@router.get(
    "/{source_id}",
    response_model=SourceDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Source Reference Metadata",
    description="Retrieves verified provenance metadata for a SourceReference record by ID.",
)
def get_source(
    source_id: str,
    db: Session = Depends(get_db),
) -> SourceDetailResponse:
    """Retrieve metadata for a specific source reference."""
    try:
        source_uuid = uuid.UUID(source_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invalid source ID format '{source_id}'. Must be a valid UUID.",
        )

    try:
        return get_source_detail(db, source_uuid)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve source reference metadata.",
        )


@router.get(
    "/{source_id}/preview",
    response_model=SourcePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Source Verification Preview",
    description="Retrieves contextual preview data including extracted content, sheet/page details, surrounding rows, bounding box coordinates, and relevance explanations.",
)
def preview_source(
    source_id: str,
    db: Session = Depends(get_db),
) -> SourcePreviewResponse:
    """Retrieve verified preview context for a specific source reference."""
    try:
        source_uuid = uuid.UUID(source_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invalid source ID format '{source_id}'. Must be a valid UUID.",
        )

    try:
        return get_source_preview(db, source_uuid)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate source verification preview.",
        )
