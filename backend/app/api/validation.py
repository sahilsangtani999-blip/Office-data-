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

from app.core.dependencies import AuthenticatedUserContext, get_current_user, require_permission
from app.database import get_db
from app.models import Document
from app.services.validation_service import (
    ReviewerContext,
    ValidationIssue,
    ValidationResult,
    approve_document,
    enrich_issue,
    get_document_records,
    get_review_history,
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
    raw_value: Optional[str] = None
    extracted_value: Optional[Dict[str, Any]] = None
    record_details: Optional[Dict[str, Any]] = None
    document_name: Optional[str] = None


class ValidationResultSchema(BaseModel):
    document_id: str
    document_name: Optional[str] = None
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
    review_history: Optional[List[Dict[str, Any]]] = None


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
    user: AuthenticatedUserContext = Depends(get_current_user),
) -> ReviewerContext:
    """
    Dependency that resolves the reviewer context from the authenticated user (JWT)
    or header overrides. Verifies whether the caller is authorized to perform review actions.
    """
    is_authorized = user.is_authenticated and user.has_permission("review")
    return ReviewerContext(
        user_id=user.user_id,
        username=user.username,
        roles=user.roles,
        is_authorized=is_authorized,
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
    user: AuthenticatedUserContext = Depends(require_permission("review")),
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
    user: AuthenticatedUserContext = Depends(require_permission("read")),
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
        doc = db.query(Document).filter(Document.id == doc_uuid).first()
        doc_name = doc.original_filename if doc else None
        result = get_validation_result(db, doc_uuid, version_id=ver_uuid)
        res_dict = result.to_dict()
        res_dict["document_name"] = doc_name
        res_dict["issues"] = [enrich_issue(db, i, doc_name=doc_name) for i in result.issues]
        res_dict["review_history"] = get_review_history(db, doc_uuid)
        return res_dict
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
    user: AuthenticatedUserContext = Depends(require_permission("read")),
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
        doc = db.query(Document).filter(Document.id == doc_uuid).first()
        doc_name = doc.original_filename if doc else None
        issues = list_validation_issues(db, doc_uuid, version_id=ver_uuid, severity=severity)
        return [enrich_issue(db, i, doc_name=doc_name) for i in issues]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{document_id}/history",
    response_model=List[Dict[str, Any]],
    summary="Get document review history",
)
def fetch_review_history(
    document_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
):
    """Retrieve the full review audit trail for a document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id.",
        )
    return get_review_history(db, doc_uuid)


@router.get(
    "/{document_id}/records",
    response_model=List[Dict[str, Any]],
    summary="Get extracted entity records for a document",
)
def fetch_document_records(
    document_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedUserContext = Depends(require_permission("read")),
):
    """Retrieve all structured entity records (Attendance, Assignment, Vehicle) linked to this document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for document_id.",
        )
    try:
        return get_document_records(db, doc_uuid)
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
