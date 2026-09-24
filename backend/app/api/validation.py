"""
API Endpoints for Data Validation and Review in RSSB Office Data Platform.

Endpoints:
- POST /api/v1/documents/{document_id}/validate
- GET  /api/v1/documents/{document_id}/validation
- GET  /api/v1/documents/{document_id}/issues
- POST /api/v1/documents/{document_id}/approve
- POST /api/v1/documents/{document_id}/reject
- POST /api/v1/documents/{document_id}/needs-correction
"""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.validation_service import (
    ReviewerContext,
    ValidationIssue,
    ValidationResult,
    approve_document,
    get_validation_result,
    list_validation_issues,
    mark_needs_correction,
    reject_document,
    validate_document,
)

router = APIRouter(prefix="/api/v1/documents", tags=["Validation & Review"])


# =============================================================================
# Request & Response Schemas
# =============================================================================

class ValidationIssueSchema(BaseModel):
    issue_type: str
    severity: str
    message: str
    record_type: Optional[str] = None
    record_id: Optional[str] = None
    source_reference_id: Optional[str] = None
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    cell_or_range: Optional[str] = None


class ValidationResultSchema(BaseModel):
    document_id: str
    version_id: Optional[str] = None
    validation_status: str
    total_records_examined: int
    valid_count: int
    needs_review_count: int
    invalid_count: int
    warnings_count: int
    errors_count: int
    validation_timestamp: str
    issues: List[ValidationIssueSchema]


class ApprovalRequestSchema(BaseModel):
    notes: Optional[str] = Field(default=None, description="Optional reviewer notes")


class RejectionRequestSchema(BaseModel):
    reason: str = Field(..., description="Mandatory reason for rejecting document")


class NeedsCorrectionRequestSchema(BaseModel):
    instructions: str = Field(..., description="Mandatory instructions for required corrections")


class ReviewActionResponseSchema(BaseModel):
    document_id: str
    status: str
    action: str
    reviewer: str
    notes: Optional[str] = None
    reason: Optional[str] = None
    instructions: Optional[str] = None


# =============================================================================
# Permission Preparation Dependency
# =============================================================================

def get_current_reviewer(
    x_user_id: Optional[str] = Header(default="dev-test-user"),
    x_user_name: Optional[str] = Header(default="Developer / Test Reviewer"),
    x_authorized: Optional[str] = Header(default="true"),
) -> ReviewerContext:
    """
    Dependency preparing for future RBAC / JWT authorization.
    In dev/test, uses header overrides or defaults to authorized reviewer.
    """
    is_auth = str(x_authorized).lower() in ("true", "1", "yes")
    return ReviewerContext(
        user_id=x_user_id or "dev-test-user",
        username=x_user_name or "Developer / Test Reviewer",
        roles=["reviewer", "admin"],
        is_authorized=is_auth,
    )


# =============================================================================
# Validation Endpoints
# =============================================================================

@router.post(
    "/{document_id}/validate",
    response_model=ValidationResultSchema,
    summary="Trigger document validation",
)
def trigger_validation(
    document_id: str,
    version_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Run comprehensive validation checks on a document and persist the results."""
    try:
        doc_uuid = uuid.UUID(document_id)
        ver_uuid = uuid.UUID(version_id) if version_id else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id or version_id.",
        )

    try:
        result = validate_document(db, doc_uuid, version_id=ver_uuid, auto_commit=True)
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{document_id}/validation",
    response_model=ValidationResultSchema,
    summary="Get document validation report",
)
def fetch_validation(
    document_id: str,
    version_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Retrieve the latest validation result report for a document."""
    try:
        doc_uuid = uuid.UUID(document_id)
        ver_uuid = uuid.UUID(version_id) if version_id else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id or version_id.",
        )

    try:
        result = get_validation_result(db, doc_uuid, version_id=ver_uuid)
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{document_id}/issues",
    response_model=List[ValidationIssueSchema],
    summary="List document validation issues",
)
def fetch_issues(
    document_id: str,
    severity: Optional[str] = Query(default=None, description="Filter by INFO, WARNING, or ERROR"),
    version_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """List validation issues detected on a document, optionally filtered by severity."""
    try:
        doc_uuid = uuid.UUID(document_id)
        ver_uuid = uuid.UUID(version_id) if version_id else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id or version_id.",
        )

    try:
        issues = list_validation_issues(db, doc_uuid, version_id=ver_uuid, severity=severity)
        return [i.to_dict() for i in issues]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# Review & Approval Endpoints
# =============================================================================

@router.post(
    "/{document_id}/approve",
    response_model=ReviewActionResponseSchema,
    summary="Approve document",
)
def approve(
    document_id: str,
    payload: Optional[ApprovalRequestSchema] = None,
    reviewer: ReviewerContext = Depends(get_current_reviewer),
    db: Session = Depends(get_db),
):
    """Mark document as approved by an authorized reviewer."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id.",
        )

    notes = payload.notes if payload else None

    try:
        return approve_document(db, doc_uuid, reviewer=reviewer, notes=notes, auto_commit=True)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{document_id}/reject",
    response_model=ReviewActionResponseSchema,
    summary="Reject document",
)
def reject(
    document_id: str,
    payload: RejectionRequestSchema,
    reviewer: ReviewerContext = Depends(get_current_reviewer),
    db: Session = Depends(get_db),
):
    """Mark document as rejected by an authorized reviewer."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id.",
        )

    try:
        return reject_document(db, doc_uuid, reviewer=reviewer, reason=payload.reason, auto_commit=True)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{document_id}/needs-correction",
    response_model=ReviewActionResponseSchema,
    summary="Mark document as Needs Correction",
)
def mark_correction(
    document_id: str,
    payload: NeedsCorrectionRequestSchema,
    reviewer: ReviewerContext = Depends(get_current_reviewer),
    db: Session = Depends(get_db),
):
    """Flag document as requiring corrections before official acceptance."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id.",
        )

    try:
        return mark_needs_correction(
            db, doc_uuid, reviewer=reviewer, instructions=payload.instructions, auto_commit=True
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
